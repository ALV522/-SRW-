"""Read-only, privacy-minimal Native ZIP size accounting.

Reports central-directory statistics and full archive SHA-256 without
extracting, executing, uploading or printing member names/private content.
Not a replacement for scripts.native_payload.audit_zip.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import json
import zipfile
from pathlib import Path

_GROUPS = ("runtime", "knowledge", "windows-host", "source", "governance", "other")
_SOURCE_DIRS = (
    "backend/", "frontend/", "scripts/", "desktop/", "docs/", "verification/",
    "convergence_tests/", "browser_acceptance/", ".github/",
)
_GOVERNANCE_FILES = {
    "SOURCE_MANIFEST.sha256", "SOURCE_RECOVERY_MANIFEST.sha256",
    "PRODUCTION_RUNTIME.sha256", "PRODUCTION_KNOWLEDGE.sha256",
}


def _group(name: str) -> str:
    if name.startswith("runtime/"):
        return "runtime"
    if name.startswith("knowledge/active/"):
        return "knowledge"
    if name.startswith("windows-host/"):
        return "windows-host"
    if name in _GOVERNANCE_FILES or name.endswith("PROVENANCE.json"):
        return "governance"
    if name.startswith(_SOURCE_DIRS):
        return "source"
    return "other"


def _identity(st) -> tuple[int, int, int, int]:
    """Identity + mutation indicators, shared by path and its opened handle."""
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _validate_member(info: zipfile.ZipInfo) -> None:
    """Reject misleading or nonportable labels before classifying ZIP members.

    This is a footprint *sanity check*, not an extraction or integrity audit.
    It never prints member names, even on malformed private ZIP input.
    """
    name = info.filename
    logical = name[:-1] if info.is_dir() else name
    if (not logical or logical.startswith("/") or "\\" in logical
            or ":" in logical
            or any(part in ("", ".", "..") for part in logical.split("/"))):
        raise ValueError("ZIP has noncanonical member path")
    if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
        raise ValueError("ZIP has symbolic-link member")


def profile_zip(archive: Path) -> dict:
    """Read directory and SHA from the SAME opened ZIP, without member reads.

    A historical two-open implementation could combine directory sizes from
    one inode with the SHA of a replacement file at the same path. Check
    pathname vs handle identity before and after to fail closed in that case.
    """
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("ZIP must be an existing regular file (not a symlink)")
    initial = archive.stat()
    groups = {name: {"files": 0, "uncompressed_bytes": 0, "compressed_bytes": 0}
              for name in _GROUPS}
    seen: set[str] = set()
    with archive.open("rb") as stream:
        pinned = os.fstat(stream.fileno())
        if _identity(initial) != _identity(pinned):
            raise ValueError("ZIP identity changed before reading")
        with zipfile.ZipFile(stream) as reader:
            for info in reader.infolist():
                _validate_member(info)
                if info.is_dir():
                    continue
                collision_key = info.filename.casefold()
                if collision_key in seen:
                    raise ValueError("ZIP has duplicate or case-colliding members")
                seen.add(collision_key)
                summary = groups[_group(info.filename)]
                summary["files"] += 1
                summary["uncompressed_bytes"] += info.file_size
                summary["compressed_bytes"] += info.compress_size
        stream.seek(0)
        digest = hashlib.sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
        if _identity(os.fstat(stream.fileno())) != _identity(pinned):
            raise ValueError("ZIP identity changed while reading")
    if archive.is_symlink() or _identity(archive.stat()) != _identity(pinned):
        raise ValueError("ZIP identity changed after reading")
    size = pinned.st_size
    compressed = sum(group["compressed_bytes"] for group in groups.values())
    return {
        "schema": "srw.native-zip-footprint.v1",
        "zip_sha256": digest.hexdigest(),
        "archive_bytes": size,
        "payload_compressed_bytes": compressed,
        "zip_container_overhead_bytes": size - compressed,
        "uncompressed_bytes": sum(group["uncompressed_bytes"] for group in groups.values()),
        "file_count": len(seen),
        "groups": groups,
        "integrity_verified": False,
        "payload_extracted": False,
    }


def compare(before: dict, after: dict) -> dict:
    fields = ("archive_bytes", "payload_compressed_bytes",
              "zip_container_overhead_bytes", "uncompressed_bytes", "file_count")
    return {
        "after_minus_before": {field: after[field] - before[field] for field in fields},
        "group_compressed_delta_bytes": {
            name: after["groups"][name]["compressed_bytes"] - before["groups"][name]["compressed_bytes"]
            for name in _GROUPS
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Native ZIP size accounting; no extraction or upload")
    parser.add_argument("--zip", type=Path, action="append", required=True,
                        help="One ZIP for a profile, or exactly two for before/after comparison")
    args = parser.parse_args(argv)
    if len(args.zip) not in (1, 2):
        parser.error("provide one or two --zip arguments")
    try:
        profiles = [profile_zip(path) for path in args.zip]
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        parser.error(f"archive profile failed: {type(exc).__name__}")
    report = {"archives": profiles}
    if len(profiles) == 2:
        report["comparison"] = compare(*profiles)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
