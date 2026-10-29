"""Verify two readable copies of the pinned historical Native input.

Byte identity is not a source signature or a disaster-recovery acceptance.
Never execute, extract, upload, alter, or log the private archive contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.rebuild_native_from_prepared import BASE_PREPARED_ZIP_SHA256

PINNED_SIZE = 101_617_623
SCHEMA = "srw.native-external-custody-check.v1"


class CustodyError(ValueError):
    pass


def _regular_unlinked(path: Path) -> os.stat_result:
    if not path.is_absolute():
        raise CustodyError("archive path must be absolute")
    if not path.is_file() or path.is_symlink():
        raise CustodyError("archive absent, nonregular or linked")
    if any(parent.is_symlink() for parent in path.parents):
        raise CustodyError("archive parent directory linked")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise CustodyError("archive not a regular file")
    return st


def _file_identity(st: os.stat_result) -> tuple[int, int, int, int, int]:
    # Do not use atime: verification itself may legitimately update it.
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _digest(path: Path, *, expected_size: int, expected_digest: str) -> os.stat_result:
    before = _regular_unlinked(path)
    if before.st_size != expected_size:
        raise CustodyError("archive size mismatch")

    # Hash an open *file object*, not an unpinned pathname. A path may be
    # replaced between lstat/stat and open; checking only the path again after
    # the digest allows a swapped-in good file to authenticate the wrong ZIP.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    # A file can become a symlink or be locked by antivirus after the safe-path
    # check. Never leak an OSError with a user-private archive pathname to a
    # caller that uses this library outside the CLI's coarse JSON handler.
    try:
        fd = os.open(path, flags)
    except OSError:
        raise CustodyError("archive could not be opened for verification") from None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _file_identity(opened) != _file_identity(before):
            raise CustodyError("archive file identity changed before reading")
        h = hashlib.sha256()
        remaining = expected_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise CustodyError("archive truncated during verification")
            h.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise CustodyError("archive grew during verification")
        if _file_identity(os.fstat(fd)) != _file_identity(opened):
            raise CustodyError("archive changed while reading")
    finally:
        os.close(fd)

    after = _regular_unlinked(path)
    if _file_identity(before) != _file_identity(after):
        raise CustodyError("archive changed during verification")
    if h.hexdigest() != expected_digest:
        raise CustodyError("archive content digest mismatch")
    return after


def audit_custody(primary: Path, secondary: Path, *,
                  expected_size: int = PINNED_SIZE,
                  expected_digest: str = BASE_PREPARED_ZIP_SHA256) -> dict:
    """Test seam for synthetic fixtures; production CLI uses immutable pins."""
    if not isinstance(expected_size, int) or expected_size < 1 or (
        len(expected_digest) != 64 or
        any(c not in "0123456789abcdef" for c in expected_digest)
    ):
        raise CustodyError("invalid pinned identity")
    a = _regular_unlinked(primary)
    b = _regular_unlinked(secondary)
    if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino) or os.path.samefile(primary, secondary):
        raise CustodyError("both copies resolve to the same file")
    a = _digest(primary, expected_size=expected_size, expected_digest=expected_digest)
    b = _digest(secondary, expected_size=expected_size, expected_digest=expected_digest)
    return {
        "schema": SCHEMA,
        "status": "TWO_PINNED_COPIES_VERIFIED_RECOVERY_NOT_PROVEN",
        "copies_verified": 2,
        "archive_sha256": expected_digest,
        "archive_bytes": expected_size,
        "separate_file_objects_verified": True,
        "different_device_ids_observed": a.st_dev != b.st_dev,
        "independent_failure_domains_verified": False,
        "clean_room_rebuild_verified": False,
        "knowledge_redistribution_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = args.evidence
        if not evidence.is_absolute() or evidence.is_symlink() or evidence.exists():
            raise CustodyError("evidence output must be a new absolute regular-file path")
        if any(parent.is_symlink() for parent in evidence.parents):
            raise CustodyError("evidence parent linked")
        if evidence.resolve() in (args.primary.resolve(), args.secondary.resolve()):
            raise CustodyError("evidence cannot overwrite archive")
        result = audit_custody(args.primary, args.secondary)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("x", encoding="utf-8") as dest:
            json.dump(result, dest, sort_keys=True, indent=2)
            dest.write("\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CustodyError, OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "BLOCKED",
                          "reason_type": type(exc).__name__}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
