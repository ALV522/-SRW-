from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from srw.runtime.db.schema import V1_SCHEMA_REVISION, create_v1_schema
from srw.runtime.db.session import create_v1_engine


class PortableMigrationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_number(revision: str) -> int:
    if not revision.startswith("v1_"):
        raise PortableMigrationError(f"unsupported source schema: {revision}")
    try:
        return int(revision.split("_", 1)[1])
    except ValueError as exc:
        raise PortableMigrationError(f"invalid source schema: {revision}") from exc


def validate_v1_database(path: str | Path) -> str:
    db = Path(path).resolve()
    if not db.is_file():
        raise PortableMigrationError(f"source database not found: {db}")
    if db.read_bytes()[:16] != b"SQLite format 3\x00":
        raise PortableMigrationError("source database is not valid SQLite")
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2.0)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()
            if not quick or str(quick[0]).lower() != "ok":
                raise PortableMigrationError("source database failed SQLite quick_check")
            row = conn.execute("SELECT schema_revision FROM v1_schema_meta LIMIT 1").fetchone()
            if not row:
                raise PortableMigrationError("source database has no SRW schema revision")
            revision = str(row[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise PortableMigrationError(f"source database validation failed: {exc}") from exc
    if _schema_number(revision) > _schema_number(V1_SCHEMA_REVISION):
        raise PortableMigrationError(
            f"source schema {revision} is newer than this Portable ({V1_SCHEMA_REVISION})"
        )
    return revision


def _consistent_snapshot(source_db: Path, destination_db: Path) -> None:
    destination_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True, timeout=5.0)
    dst = sqlite3.connect(str(destination_db))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def migrate_data_directory(source_data_dir: str | Path, target_data_dir: str | Path) -> dict:
    """Copy an older SRW v1 data directory into a fresh Portable data directory.

    The source is treated read-only. The destination must not already contain an
    SRW database; existing installations should use Backup/Restore instead.
    """
    source = Path(source_data_dir).expanduser().resolve()
    target = Path(target_data_dir).expanduser().resolve()
    if source == target:
        raise PortableMigrationError("source and target data directories must be different")
    source_db = source / "srw_v1.db"
    target_db = target / "srw_v1.db"
    if target_db.exists():
        raise PortableMigrationError("target data directory already contains srw_v1.db; use Backup/Restore instead")

    source_schema = validate_v1_database(source_db)
    source_hash_before = _sha256(source_db)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="srw-migrate-", dir=str(target.parent)) as tmp:
        stage = Path(tmp) / "data"
        stage.mkdir(parents=True, exist_ok=True)
        staged_db = stage / "srw_v1.db"
        _consistent_snapshot(source_db, staged_db)

        # Upgrade only the copied snapshot. The original database remains read-only.
        engine = create_v1_engine(f"sqlite+pysqlite:///{staged_db.as_posix()}")
        try:
            create_v1_schema(engine)
        finally:
            engine.dispose()
        target_schema = validate_v1_database(staged_db)
        if target_schema != V1_SCHEMA_REVISION:
            raise PortableMigrationError(
                f"migrated database revision mismatch: {target_schema} != {V1_SCHEMA_REVISION}"
            )

        source_blobs = source / "blobs"
        if source_blobs.is_dir():
            shutil.copytree(source_blobs, stage / "blobs")
        source_secrets = source / "provider_secrets.json"
        if source_secrets.is_file():
            shutil.copy2(source_secrets, stage / "provider_secrets.json")

        # Publish staged artifacts into the fresh target. DB replacement is atomic.
        target.mkdir(parents=True, exist_ok=True)
        os.replace(staged_db, target_db)
        staged_blobs = stage / "blobs"
        if staged_blobs.exists():
            os.replace(staged_blobs, target / "blobs")
        staged_secrets = stage / "provider_secrets.json"
        if staged_secrets.exists():
            os.replace(staged_secrets, target / "provider_secrets.json")

    source_hash_after = _sha256(source_db)
    if source_hash_after != source_hash_before:
        raise PortableMigrationError("source database changed during migration")

    return {
        "source_data_dir": str(source),
        "target_data_dir": str(target),
        "source_schema_revision": source_schema,
        "target_schema_revision": V1_SCHEMA_REVISION,
        "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "blobs_copied": (target / "blobs").is_dir(),
        "provider_settings_copied": (target / "provider_secrets.json").is_file(),
    }
