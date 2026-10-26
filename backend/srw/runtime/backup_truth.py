from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

BACKUP_MANIFEST_NAME = "SRW_BACKUP_MANIFEST.json"
BACKUP_MANIFEST_SCHEMA = "srw.backup-manifest.v1"
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 768 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class BackupTruthError(RuntimeError):
    pass


def sha256_path(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_number(revision: str) -> int:
    if not revision.startswith("v1_"):
        raise BackupTruthError(f"unsupported backup schema: {revision}")
    try:
        return int(revision.split("_", 1)[1])
    except ValueError as exc:
        raise BackupTruthError(f"invalid backup schema: {revision}") from exc


def _read_db_schema(path: Path) -> str:
    if not path.is_file():
        raise BackupTruthError("backup database is missing")
    with path.open("rb") as fh:
        if fh.read(16) != b"SQLite format 3\x00":
            raise BackupTruthError("backup database is not valid SQLite")
    try:
        conn = sqlite3.connect(str(path), timeout=2.0)
        try:
            qc = conn.execute("PRAGMA quick_check").fetchone()
            if not qc or str(qc[0]).lower() != "ok":
                raise BackupTruthError("backup database failed SQLite quick_check")
            row = conn.execute("SELECT schema_revision FROM v1_schema_meta LIMIT 1").fetchone()
            if not row:
                raise BackupTruthError("backup database has no SRW schema revision")
            return str(row[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise BackupTruthError(f"backup database validation failed: {exc}") from exc


def _archive_path_is_safe(name: str) -> bool:
    if not name or "\\" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and str(path) == name


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def _checked_infos(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise BackupTruthError("backup contains duplicate ZIP members")
    total = 0
    out: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        name = info.filename
        if not _archive_path_is_safe(name):
            raise BackupTruthError("backup contains an unsafe path")
        if name != BACKUP_MANIFEST_NAME and name != "data/srw_v1.db" and not name.startswith("data/blobs/"):
            raise BackupTruthError("backup contains an unexpected member")
        if _is_symlink(info):
            raise BackupTruthError("backup contains a symbolic-link member")
        if info.file_size > MAX_MEMBER_BYTES:
            raise BackupTruthError("backup member exceeds 768 MB limit")
        total += int(info.file_size)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise BackupTruthError("backup exceeds 1 GB uncompressed limit")
        if not info.is_dir():
            out[name] = info
    if "data/srw_v1.db" not in out:
        raise BackupTruthError("backup does not contain data/srw_v1.db")
    return out


def _hash_zip_member(archive: zipfile.ZipFile, name: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with archive.open(name, "r") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def _content_addressed_blob_digest(member: str) -> str | None:
    """Recognize modern SHA-256 Source paths without banning legacy names.

    Older SRW backup archives may contain arbitrary Blob filenames and must
    still be restorable. Only the modern two-level xx/<64 hex> namespace
    carries an enforceable filename-to-content integrity invariant.
    """
    prefix = "data/blobs/"
    if not member.startswith(prefix):
        return None
    segments = member[len(prefix):].split("/")
    if len(segments) != 2:
        return None
    shard, digest = segments
    hexdigits = frozenset("0123456789abcdef")
    if (len(shard) != 2 or len(digest) != 64
            or any(ch not in hexdigits for ch in shard + digest)):
        return None
    if digest[:2] != shard:
        raise BackupTruthError("backup content-addressed Source shard mismatch")
    return digest


def _blob_entries(blobs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not blobs_root.exists():
        return rows
    for path in sorted(blobs_root.rglob("*")):
        if path.is_symlink():
            raise BackupTruthError(f"backup blob is a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(blobs_root).as_posix()
        archive_path = f"data/blobs/{relative}"
        if not _archive_path_is_safe(archive_path):
            raise BackupTruthError(f"unsafe blob archive path: {archive_path}")
        actual_sha = sha256_path(path)
        named_sha = _content_addressed_blob_digest(archive_path)
        if named_sha is not None and actual_sha != named_sha:
            raise BackupTruthError("backup content-addressed Source hash mismatch")
        rows.append({
            "path": archive_path,
            "sha256": actual_sha,
            "size_bytes": path.stat().st_size,
        })
    return rows


def build_backup_manifest(database_snapshot: str | Path, blobs_root: str | Path) -> dict[str, Any]:
    db = Path(database_snapshot)
    blobs = _blob_entries(Path(blobs_root))
    return {
        "schema": BACKUP_MANIFEST_SCHEMA,
        "database": {
            "path": "data/srw_v1.db",
            "sha256": sha256_path(db),
            "size_bytes": db.stat().st_size,
        },
        "blobs": blobs,
        "blob_count": len(blobs),
    }


def write_backup_archive(
    destination: str | Path,
    database_snapshot: str | Path,
    blobs_root: str | Path,
) -> Path:
    dest = Path(destination)
    db = Path(database_snapshot)
    blob_root = Path(blobs_root)
    manifest = build_backup_manifest(db, blob_root)
    manifest_raw = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Build next to the destination: no partial archive is ever named *.zip.
    fd, staging_name = tempfile.mkstemp(
        prefix=".srw-staging-", suffix=".partial", dir=dest.parent,
    )
    os.close(fd)
    staging = Path(staging_name)
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(db, "data/srw_v1.db")
            for row in manifest["blobs"]:
                relative = str(row["path"])[len("data/blobs/"):]
                archive.write(blob_root / PurePosixPath(relative), row["path"])
            archive.writestr(BACKUP_MANIFEST_NAME, manifest_raw)

        # Compare archived bytes against the pre-write manifest, so mutated
        # Source input cannot yield an internally valid but incorrect backup.
        with zipfile.ZipFile(staging, "r") as written:
            for row in [manifest["database"], *manifest["blobs"]]:
                actual_sha, actual_size = _hash_zip_member(written, row["path"])
                if actual_sha != row["sha256"] or actual_size != row["size_bytes"]:
                    raise BackupTruthError("backup inputs changed during archive creation")
            if written.read(BACKUP_MANIFEST_NAME) != manifest_raw:
                raise BackupTruthError("backup manifest changed during archive creation")
        # Windows _commit() requires a writable descriptor for fsync.
        # The ZIP is closed; this handle changes no payload bytes.
        with staging.open("r+b") as handle:
            os.fsync(handle.fileno())

        # Atomic no-clobber publish on NTFS/POSIX. os.replace could silently
        # overwrite an existing valid backup on filename collision.
        # Unsupported hard-link filesystems fail closed without partial ZIPs.
        os.link(staging, dest)
        staging.unlink()
        if os.name != "nt":
            directory_fd = os.open(
                dest.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return dest
    finally:
        staging.unlink(missing_ok=True)


def validate_backup_archive(
    path: str | Path,
    *,
    expected_archive_sha256: str | None = None,
    expected_schema: str | None = None,
    max_schema: str | None = None,
) -> dict[str, Any]:
    backup = Path(path)
    if not backup.is_file():
        raise BackupTruthError("backup file not found")
    if backup.stat().st_size > MAX_COMPRESSED_BYTES:
        raise BackupTruthError("backup exceeds 512 MB compressed limit")
    archive_sha = sha256_path(backup)
    if expected_archive_sha256 and archive_sha != expected_archive_sha256:
        raise BackupTruthError("backup hash mismatch; restore aborted")

    try:
        with zipfile.ZipFile(backup, "r") as archive:
            infos = _checked_infos(archive)
            manifest_present = BACKUP_MANIFEST_NAME in infos
            manifest: dict[str, Any] | None = None
            if manifest_present:
                info = infos[BACKUP_MANIFEST_NAME]
                if info.file_size > MAX_MANIFEST_BYTES:
                    raise BackupTruthError("backup manifest exceeds 2 MB limit")
                try:
                    manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BackupTruthError("backup manifest is invalid JSON") from exc
                if not isinstance(manifest, dict) or manifest.get("schema") != BACKUP_MANIFEST_SCHEMA:
                    raise BackupTruthError("backup manifest schema is unsupported")
                db_row = manifest.get("database")
                blob_rows = manifest.get("blobs")
                if not isinstance(db_row, dict) or not isinstance(blob_rows, list):
                    raise BackupTruthError("backup manifest structure is invalid")
                if db_row.get("path") != "data/srw_v1.db":
                    raise BackupTruthError("backup manifest database path is invalid")
                declared: set[str] = {BACKUP_MANIFEST_NAME, "data/srw_v1.db"}
                rows = [db_row]
                for row in blob_rows:
                    if not isinstance(row, dict):
                        raise BackupTruthError("backup manifest blob entry is invalid")
                    member = str(row.get("path") or "")
                    if not member.startswith("data/blobs/") or not _archive_path_is_safe(member):
                        raise BackupTruthError("backup manifest blob path is invalid")
                    if member in declared:
                        raise BackupTruthError("backup manifest contains duplicate member declarations")
                    declared.add(member)
                    rows.append(row)
                if manifest.get("blob_count") != len(blob_rows):
                    raise BackupTruthError("backup manifest blob count does not match its entries")
                if declared != set(infos):
                    missing = sorted(declared - set(infos))
                    extra = sorted(set(infos) - declared)
                    raise BackupTruthError(
                        f"backup manifest/member mismatch: missing={missing[:3]} extra={extra[:3]}"
                    )
                for row in rows:
                    member = str(row.get("path") or "")
                    wanted_hash = str(row.get("sha256") or "")
                    wanted_size = row.get("size_bytes")
                    if len(wanted_hash) != 64 or not all(ch in "0123456789abcdef" for ch in wanted_hash):
                        raise BackupTruthError(f"backup manifest digest is invalid: {member}")
                    if not isinstance(wanted_size, int) or wanted_size < 0:
                        raise BackupTruthError(f"backup manifest size is invalid: {member}")
                    got_hash, got_size = _hash_zip_member(archive, member)
                    if got_hash != wanted_hash or got_size != wanted_size:
                        raise BackupTruthError(f"backup member digest mismatch: {member}")
                    # A forged/self-consistent manifest must not launder an
                    # incorrect immutable Source under a SHA-256 filename.
                    # Arbitrarily named historical Blob files stay accepted.
                    content_address = _content_addressed_blob_digest(member)
                    if content_address is not None and got_hash != content_address:
                        raise BackupTruthError("backup content-addressed Source hash mismatch")

            with tempfile.TemporaryDirectory(prefix="srw-backup-truth-") as directory:
                candidate = Path(directory) / "srw_v1.db"
                with archive.open("data/srw_v1.db", "r") as source, candidate.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                schema_revision = _read_db_schema(candidate)
    except zipfile.BadZipFile as exc:
        raise BackupTruthError(f"invalid backup zip: {exc}") from exc
    except OSError as exc:
        raise BackupTruthError(f"backup validation failed: {exc}") from exc

    if expected_schema and schema_revision != expected_schema:
        raise BackupTruthError(
            f"backup schema mismatch: {schema_revision} != {expected_schema}"
        )
    if max_schema and _schema_number(schema_revision) > _schema_number(max_schema):
        raise BackupTruthError(
            f"backup schema is newer than this Portable: {schema_revision}"
        )
    return {
        "archive_sha256": archive_sha,
        "schema_revision": schema_revision,
        "manifest_present": manifest_present,
        "integrity_level": "manifest_sha256" if manifest_present else "legacy_unmanifested",
        "blob_count": int((manifest or {}).get("blob_count", 0) or 0),
        "member_count": len(infos),
    }


def extract_validated_backup(
    path: str | Path,
    destination: str | Path,
    *,
    expected_archive_sha256: str | None = None,
    expected_schema: str | None = None,
    max_schema: str | None = None,
) -> dict[str, Any]:
    result = validate_backup_archive(
        path,
        expected_archive_sha256=expected_archive_sha256,
        expected_schema=expected_schema,
        max_schema=max_schema,
    )
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as archive:
        infos = _checked_infos(archive)
        for name, info in infos.items():
            if name == BACKUP_MANIFEST_NAME:
                continue
            target = (root / PurePosixPath(name)).resolve()
            if not target.is_relative_to(root):
                raise BackupTruthError("backup extraction escaped destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as out:
                shutil.copyfileobj(source, out, length=1024 * 1024)
    return result
