"""Read-only custody check for two offline copies of the fixed Native input.

This checks availability of the *pinned* predecessor and never certifies the
independence of disks/backups, licensing, authenticity of the original build,
reproducible reconstruction, Windows GUI or release readiness.

Never print or persist input paths, ZIP contents, credentials or private data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.rebuild_native_from_prepared import BASE_PREPARED_ZIP_SHA256

PINNED_BYTES = 101_617_623
PINNED_RUNTIME_FILES = 2332
PINNED_KNOWLEDGE_FILES = 5
SCHEMA = "srw.native-input-custody.v1"
MUST_INCLUDE = ("PRODUCTION_RUNTIME.sha256", "PRODUCTION_KNOWLEDGE.sha256")


class CustodyError(ValueError):
    """Fail-closed error type; never include private paths in the exception."""


def _hash_unchanged_regular_file(path: Path, expected_digest: str, expected_bytes: int) -> dict:
    # lstat prevents following symlink at path entry; fstat binds the handle to
    # the same regular file so a replacement at the path is detected afterward.
    if path.is_symlink():
        raise CustodyError("SYMLINK_INPUT_REJECTED")
    try:
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
            raise CustodyError("NOT_REGULAR_OR_BYTE_SIZE_MISMATCH")
        h = hashlib.sha256()
        with path.open("rb") as stream:
            fd_before = os.fstat(stream.fileno())
            if ((fd_before.st_dev, fd_before.st_ino) != (before.st_dev, before.st_ino)
                    or fd_before.st_size != expected_bytes):
                raise CustodyError("INPUT_CHANGED_DURING_OPEN")
            while block := stream.read(1024 * 1024):
                h.update(block)
            fd_after = os.fstat(stream.fileno())
        after = path.stat(follow_symlinks=False)
    except CustodyError:
        raise
    except (OSError, ValueError) as exc:
        raise CustodyError("INPUT_NOT_READABLE") from exc
    stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if (stable != (fd_after.st_dev, fd_after.st_ino, fd_after.st_size, fd_after.st_mtime_ns)
            or stable != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise CustodyError("INPUT_CHANGED_DURING_HASH")
    if h.hexdigest() != expected_digest:
        raise CustodyError("INPUT_SHA256_MISMATCH")
    return {"filesize_verified": expected_bytes, "sha256_verified": True}


def _check_zip_inventory(path: Path, *, runtime_count: int, knowledge_count: int) -> dict:
    """Only inspect fixed manifest member counts, never emit their contents."""
    try:
        with zipfile.ZipFile(path, "r") as z:
            if any(name not in z.namelist() for name in MUST_INCLUDE):
                raise CustodyError("REQUIRED_MANIFEST_MISSING")
            # These manifests are inside the exact hashed archive; a small
            # bounded read avoids a malformed ZIP member exhausting memory.
            counts = []
            for name in MUST_INCLUDE:
                info = z.getinfo(name)
                if info.file_size > 300_000:
                    raise CustodyError("MANIFEST_SIZE_UNEXPECTED")
                raw = z.read(name)
                lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
                counts.append(len(lines))
            if counts != [runtime_count, knowledge_count]:
                raise CustodyError("PINNED_INVENTORY_COUNT_MISMATCH")
    except CustodyError:
        raise
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        raise CustodyError("PINNED_ARCHIVE_UNREADABLE") from exc
    return {"runtime_files": counts[0], "knowledge_databases": counts[1]}


def audit_two_copies(
    primary: Path, mirror: Path, *,
    expected_digest: str = BASE_PREPARED_ZIP_SHA256,
    expected_bytes: int = PINNED_BYTES,
    runtime_count: int = PINNED_RUNTIME_FILES,
    knowledge_count: int = PINNED_KNOWLEDGE_FILES,
) -> dict:
    """No public release claim; custom expected parameters are for synthetic tests.

    CLI never accepts user-supplied expected hashes or counts; no downgrade.
    """
    a, b = Path(primary), Path(mirror)
    try:
        if a.is_symlink() or b.is_symlink():
            raise CustodyError("SYMLINK_INPUT_REJECTED")
        if a.samefile(b):
            raise CustodyError("SAME_FILE_NOT_TWO_COPIES")
    except CustodyError:
        raise
    except (OSError, ValueError) as exc:
        raise CustodyError("INPUT_NOT_READABLE") from exc
    first = _hash_unchanged_regular_file(a, expected_digest, expected_bytes)
    second = _hash_unchanged_regular_file(b, expected_digest, expected_bytes)
    counts = _check_zip_inventory(a, runtime_count=runtime_count, knowledge_count=knowledge_count)
    _check_zip_inventory(b, runtime_count=runtime_count, knowledge_count=knowledge_count)
    return {
        "schema": SCHEMA,
        "status": "PINNED_TWO_FILES_VERIFIED_FAILURE_DOMAIN_UNPROVEN",
        "pinned_archive_sha256": expected_digest,
        "copy_count_verified": 2,
        "copy_sizes_verified": [first["filesize_verified"], second["filesize_verified"]],
        "runtime_manifest_entries": counts["runtime_files"],
        "knowledge_manifest_entries": counts["knowledge_databases"],
        "different_physical_failure_domains_verified": False,
        "independent_upstream_rebuild_verified": False,
        "actual_windows_runtime_executed": False,
        "windows_gui_accepted": False,
        "release_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, type=Path, help="First existing offline original Prepared ZIP")
    parser.add_argument("--mirror", required=True, type=Path, help="Second existing copy; use different storage media")
    parser.add_argument("--evidence", required=True, type=Path, help="New JSON outside both ZIPs; no overwrite")
    args = parser.parse_args()
    try:
        evidence = args.evidence
        if evidence.is_symlink() or evidence.exists():
            raise CustodyError("EVIDENCE_ALREADY_EXISTS")
        if evidence.resolve() in (args.primary.resolve(), args.mirror.resolve()):
            raise CustodyError("EVIDENCE_OVERLAPS_INPUT")
        result = audit_two_copies(args.primary, args.mirror)
        # The verifier is read-only with respect to both source ZIPs. Only a
        # new evidence record is created, never in place of an older result.
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("x", encoding="utf-8") as fp:
            json.dump(result, fp, sort_keys=True, indent=2)
            fp.write("\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CustodyError, OSError) as exc:
        code = str(exc) if isinstance(exc, CustodyError) else "EVIDENCE_WRITE_FAILED"
        print(json.dumps({"schema": SCHEMA, "status": "BLOCKED", "reason_code": code,
                          "release_approved": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
