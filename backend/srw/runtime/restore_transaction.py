"""Crash-recoverable Portable restore transaction (P0 #130).

Only called BEFORE the Core DB opens, under the launcher workspace lock.
A durable, validated pre-restore ZIP is the undo authority; journal identity
prevents a second startup from inventing a new undo of partially restored data.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from srw.runtime.backup_truth import extract_validated_backup, validate_backup_archive

JOURNAL_NAME = ".srw-restore-journal.json"
NEW_DB = ".srw_v1.db.restore-new"
OLD_DB = ".srw_v1.db.restore-old"
NEW_BLOBS = ".blobs.restore-new"
OLD_BLOBS = ".blobs.restore-old"
OLD_WAL = ".srw_v1.db.restore-old-wal"
OLD_SHM = ".srw_v1.db.restore-old-shm"
OWNED = (NEW_DB, OLD_DB, NEW_BLOBS, OLD_BLOBS, OLD_WAL, OLD_SHM)
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _durable_json(path: Path, obj: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".srw-restore-journal-", suffix=".partial", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        # POSIX directory fsync is required to commit the renamed directory entry.
        # Windows NTFS journal durability cannot be inferred from POSIX fsync.
        if os.name != "nt":
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    finally:
        tmp.unlink(missing_ok=True)


def _safe_path(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("unsafe symlink in pending restore transaction")


def _safe_backup_name(name: str) -> str:
    if (not name or name.startswith(".") or name != Path(name).name
            or not name.lower().endswith(".zip") or "\\" in name or ":" in name):
        raise RuntimeError("invalid restore archive/snapshot name")
    return name


def _read_marker(marker: Path) -> dict:
    _safe_path(marker)
    obj = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("invalid pending restore marker")
    name = _safe_backup_name(str(obj.get("backup") or ""))
    digest = str(obj.get("sha256") or "")
    schema = str(obj.get("schema_revision") or "")
    if not SHA.fullmatch(digest) or not schema.startswith("v1_"):
        raise RuntimeError("invalid pending restore marker identity")
    return {"backup": name, "sha256": digest, "schema_revision": schema}


def _blob_inventory(root: Path) -> dict[str, str] | None:
    _safe_path(root)
    if not root.exists():
        return None
    if not root.is_dir():
        raise RuntimeError("restore Blob path is not a directory")
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        _safe_path(path)
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError("non-file entry in restore Blob tree")
        found[path.relative_to(root).as_posix()] = _digest(path)
    return found


def _assert_snapshot(data: Path, state: dict) -> None:
    undo = state.get("undo")
    if undo is None:
        if state.get("had_db") is not False:
            raise RuntimeError("restore journal has no required original DB snapshot")
        return
    name = _safe_backup_name(str(undo))
    saved = data / "backups" / name
    _safe_path(saved)
    if not saved.is_file() or not SHA.fullmatch(str(state.get("undo_sha256") or "")):
        raise RuntimeError("original pre-restore snapshot is missing or unpinned")
    if _digest(saved) != state["undo_sha256"]:
        raise RuntimeError("original pre-restore snapshot changed; manual recovery required")


def _validate_journal(data: Path, state: dict) -> dict:
    if not isinstance(state, dict) or state.get("schema") != "srw.restore-journal.v1":
        raise RuntimeError("unknown restore journal; preserve workspace and stop")
    for key in ("backup", "sha256", "schema_revision", "target_db_sha256"):
        if not isinstance(state.get(key), str):
            raise RuntimeError("incomplete restore journal")
    _safe_backup_name(state["backup"])
    if not SHA.fullmatch(state["sha256"]) or not SHA.fullmatch(state["target_db_sha256"]):
        raise RuntimeError("invalid restore journal checksums")
    if state.get("phase") not in ("PREPARED", "APPLYING", "COMMITTED"):
        raise RuntimeError("unknown restore journal phase")
    if type(state.get("had_db")) is not bool or type(state.get("had_blobs")) is not bool:
        raise RuntimeError("restore journal lacks original workspace identity")
    expected = state.get("target_blobs")
    if not isinstance(expected, dict) or len(expected) > 100000:
        raise RuntimeError("invalid restored Blob manifest")
    for name, digest in expected.items():
        if (not isinstance(name, str) or not name or name.startswith("/")
                or "\\" in name or ":" in name or ".." in Path(name).parts
                or not isinstance(digest, str) or not SHA.fullmatch(digest)):
            raise RuntimeError("unsafe restored Blob manifest entry")
    _assert_snapshot(data, state)
    return state


def _checkpoint_wal(db: Path) -> None:
    if not db.is_file():
        return
    connection = sqlite3.connect(str(db), timeout=4)
    try:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result and int(result[0]) != 0:
            raise RuntimeError("SQLite WAL is busy: restore must not discard committed changes")
    finally:
        connection.close()


def _check_committed(data: Path, db: Path, state: dict) -> None:
    if not db.is_file() or _digest(db) != state["target_db_sha256"]:
        raise RuntimeError("committed restore database differs from pinned transaction")
    current = _blob_inventory(data / "blobs")
    if current != state["target_blobs"]:
        raise RuntimeError("committed restore Blobs differ from pinned transaction")


def _finalize(data: Path, db: Path, marker: Path, journal: Path, state: dict) -> None:
    _check_committed(data, db, state)
    if marker.exists():
        current = _read_marker(marker)
        if current != {key: state[key] for key in ("backup", "sha256", "schema_revision")}:
            raise RuntimeError("new pending restore conflicts with committed transaction")
        marker.unlink()
    # Delete only the paths explicitly reserved by the durable journal, never
    # globally unclaimed old rollback materials.
    for name in (NEW_DB, OLD_DB, OLD_WAL, OLD_SHM):
        path = data / name
        _safe_path(path)
        path.unlink(missing_ok=True)
    for name in (NEW_BLOBS, OLD_BLOBS):
        path = data / name
        _safe_path(path)
        if path.exists():
            shutil.rmtree(path)
    journal.unlink()


def _publish(data: Path, db: Path, marker: Path, journal: Path, state: dict,
             staged_db: Path, staged_blobs: Path, read_schema) -> None:
    state["phase"] = "APPLYING"
    _durable_json(journal, state)
    old_db, new_db = data / OLD_DB, data / NEW_DB
    old_blobs, new_blobs = data / OLD_BLOBS, data / NEW_BLOBS
    live_blobs = data / "blobs"
    for name in OWNED:
        _safe_path(data / name)
    _safe_path(db)
    _safe_path(live_blobs)

    if new_db.exists():
        new_db.unlink()
    shutil.copy2(staged_db, new_db)
    if _digest(new_db) != state["target_db_sha256"]:
        raise RuntimeError("staged restore database changed")
    if new_blobs.exists():
        shutil.rmtree(new_blobs)
    if staged_blobs.is_dir():
        shutil.copytree(staged_blobs, new_blobs)
    else:
        new_blobs.mkdir()
    if _blob_inventory(new_blobs) != state["target_blobs"]:
        raise RuntimeError("staged restored Blobs changed")

    already_new_db = db.is_file() and _digest(db) == state["target_db_sha256"]
    if state["had_db"]:
        if old_db.exists():
            if not already_new_db and db.exists():
                raise RuntimeError("unknown DB occupies transaction's published path")
        else:
            if not db.is_file():
                raise RuntimeError("original DB missing before journal-owned rollback rename")
            # The requested archive may already equal the live DB exactly.
            # In that case no destructive rename or extra rollback file is needed.
            if not already_new_db:
                _checkpoint_wal(db)
                for suffix, old_name in (("-wal", OLD_WAL), ("-shm", OLD_SHM)):
                    live_sidecar = Path(str(db) + suffix)
                    _safe_path(live_sidecar)
                    if live_sidecar.exists():
                        os.replace(live_sidecar, data / old_name)
                os.replace(db, old_db)
    elif old_db.exists():
        raise RuntimeError("unexpected old DB in no-original-DB transaction")
    elif already_new_db:
        pass
    elif db.exists():
        raise RuntimeError("unrecognized DB in new-workspace restore")
    if not already_new_db:
        os.replace(new_db, db)
    if read_schema(db) != state["schema_revision"] or _digest(db) != state["target_db_sha256"]:
        raise RuntimeError("published restore DB is not pinned target")

    blobs_are_new = _blob_inventory(live_blobs) == state["target_blobs"]
    if state["had_blobs"]:
        if old_blobs.exists():
            if not blobs_are_new and live_blobs.exists():
                raise RuntimeError("unknown Blob content alongside journal-owned original")
        else:
            if not live_blobs.exists():
                raise RuntimeError("original Blob tree missing before ownership transfer")
            # DB-only restore is valid: unchanged Source Blob bytes must not
            # be misclassified as absent original material or deleted.
            if not blobs_are_new:
                os.replace(live_blobs, old_blobs)
    elif old_blobs.exists():
        raise RuntimeError("unexpected old Blobs in no-original-Blobs transaction")
    elif live_blobs.exists() and not blobs_are_new:
        raise RuntimeError("unrecognized Blob tree in new-workspace restore")
    if not blobs_are_new:
        os.replace(new_blobs, live_blobs)
    _check_committed(data, db, state)
    state["phase"] = "COMMITTED"
    _durable_json(journal, state)
    _finalize(data, db, marker, journal, state)


def apply_restore(data: Path, db: Path, max_schema: str, pre_restore_backup,
                  read_schema) -> str | None:
    """Resume an owned transaction or begin a single new restore transaction.

    A failure preserves the journal, original undo and any owned rollback data.
    The caller must not start Core/HTTP after an exception.
    """
    data = Path(data)
    db = Path(db)
    journal, marker = data / JOURNAL_NAME, data / "pending_restore.json"
    _safe_path(journal)
    if journal.exists():
        state = _validate_journal(data, json.loads(journal.read_text(encoding="utf-8")))
        if state["phase"] == "COMMITTED":
            _finalize(data, db, marker, journal, state)
            return state["backup"]
        if not marker.exists() or _read_marker(marker) != {
            key: state[key] for key in ("backup", "sha256", "schema_revision")
        }:
            raise RuntimeError("restore marker/journal changed during interrupted transaction")
    else:
        # A pre-journal stale rollback item belongs to an UNKNOWN transaction.
        # Never unlink it and then pretend the new restore owns its bytes.
        for name in OWNED:
            _safe_path(data / name)
            if (data / name).exists():
                raise RuntimeError(f"unclaimed restore rollback material: {name}; fail closed")
        if not marker.exists():
            return None
        plan = _read_marker(marker)
        state = {
            "schema": "srw.restore-journal.v1", "phase": "PREPARED",
            **plan, "had_db": db.exists(),
            "had_blobs": (data / "blobs").exists(),
        }
    backup = data / "backups" / state["backup"]
    _safe_path(backup)
    if not backup.is_file() or _digest(backup) != state["sha256"]:
        raise RuntimeError("restore source bytes changed; fail closed")
    if not state["schema_revision"] or not max_schema.startswith("v1_"):
        raise RuntimeError("restore schema revision missing")
    # A full re-extraction on restart makes forward recovery idempotent and
    # avoids trusting partial temporary files from the killed process.
    with tempfile.TemporaryDirectory(prefix="srw-restore-", dir=data) as td:
        extracted = Path(td)
        extract_validated_backup(
            backup, extracted, expected_archive_sha256=state["sha256"],
            expected_schema=state["schema_revision"], max_schema=max_schema,
        )
        staged_db = extracted / "data" / "srw_v1.db"
        staged_blobs = extracted / "data" / "blobs"
        if read_schema(staged_db) != state["schema_revision"]:
            raise RuntimeError("restore DB schema differs from scheduled restore")
        expected_db = _digest(staged_db)
        expected_blobs = _blob_inventory(staged_blobs) or {}
        if journal.exists():
            if (state["target_db_sha256"] != expected_db
                    or state["target_blobs"] != expected_blobs):
                raise RuntimeError("restore source differs from original journal target")
        else:
            # Legacy original snapshot naming is retained for operator history.
            # Another restore in the same timestamp must not overwrite it.
            if db.exists():
                import time
                candidate = data / "backups" / ("pre_restore-" + time.strftime("%Y%m%d-%H%M%S") + ".zip")
                if candidate.exists():
                    raise RuntimeError("pre-restore snapshot name already occupied; retry later")
            undo = pre_restore_backup()
            # The published undo must already be an actually restorable ZIP,
            # not merely an arbitrary file with a plausible SHA-256 digest.
            if undo is not None:
                _safe_path(undo)
                undo_digest = validate_backup_archive(
                    undo, max_schema=max_schema,
                )["archive_sha256"]
            else:
                undo_digest = None
            state.update({
                "undo": undo.name if undo is not None else None,
                "undo_sha256": undo_digest,
                "target_db_sha256": expected_db,
                "target_blobs": expected_blobs,
            })
            _durable_json(journal, state)
        _validate_journal(data, state)
        _publish(data, db, marker, journal, state, staged_db, staged_blobs, read_schema)
    return state["backup"]
