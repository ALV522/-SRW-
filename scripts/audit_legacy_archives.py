"""Read-only admission audit for historical ZIPs; never extracts or executes files.

Checks ZIP container structure, cross-platform path safety, duplicate members,
symlinks/encryption, and exact bytes against a reviewed archive catalog.
Content classifications are metadata warnings, NOT a privacy clearance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


class ArchiveAuditError(ValueError):
    pass


def _safe_member(raw: str) -> str:
    if not raw or "\x00" in raw or "\\" in raw or ":" in raw or raw.startswith("/"):
        raise ArchiveAuditError("unsafe archive member path")
    name = raw[:-1] if raw.endswith("/") else raw
    p = PurePosixPath(name)
    reserved = {"con", "aux", "prn", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
    if not name or p.as_posix() != name or any(
        part in ("", ".", "..") or part.endswith((".", " ")) or
        part.casefold().split(".")[0] in reserved
        for part in p.parts
    ):
        raise ArchiveAuditError("unsafe archive member path")
    return name


def inspect_archive(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ArchiveAuditError("archive missing or is a symlink")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(part)

    seen: set[str] = set()
    count = 0
    expanded = 0
    nested = 0
    databases = 0
    executables = 0
    potential_private_paths = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                name = _safe_member(item.filename)
                fold = name.casefold()
                if fold in seen:
                    raise ArchiveAuditError("duplicate or case-colliding ZIP member")
                seen.add(fold)
                if ((item.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
                    raise ArchiveAuditError("ZIP contains a symbolic link")
                if item.flag_bits & 0x1:
                    raise ArchiveAuditError("encrypted ZIP member")
                if item.is_dir():
                    continue
                count += 1
                expanded += item.file_size
                leaf = name.rsplit("/", 1)[-1].lower()
                directories = [part.lower() for part in name.split("/")[:-1]]
                if leaf.endswith((".db", ".sqlite", ".sqlite3")):
                    databases += 1
                if leaf.endswith((".exe", ".dll", ".pyd", ".so", ".dylib")):
                    executables += 1
                if leaf.endswith((".zip", ".7z", ".rar")):
                    nested += 1
                if leaf in (".env", ".env.local", "secrets.json", "credentials.json", "provider_secrets.json") or (
                    set(directories) & {"data", "workspace", "uploads", "backups", "candidates", "private", "secrets"}
                ):
                    potential_private_paths += 1
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveAuditError("invalid or unreadable ZIP") from exc

    return {
        "sha256": sha.hexdigest(), "bytes": path.stat().st_size,
        "members": count, "expanded_bytes": expanded,
        "nested_archives": nested, "database_files": databases,
        "executable_files": executables, "potential_private_paths": potential_private_paths,
        "security_classification": "UNREVIEWED_CONTENT",
        "safe_to_publish": False,
    }


def audit_catalog(catalog: Path, directory: Path) -> dict:
    document = json.loads(catalog.read_text(encoding="utf-8"))
    if document.get("schema") != "srw.legacy-archive-catalog.v1":
        raise ArchiveAuditError("unsupported catalog format")
    results = []
    for entry in document.get("archives", []):
        filename = entry["filename"]
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise ArchiveAuditError("catalog filename must be a basename")
        actual = inspect_archive(directory / filename)
        if actual["sha256"] != entry["sha256"] or actual["bytes"] != entry["bytes"]:
            raise ArchiveAuditError("archive catalog checksum or size mismatch: " + entry["archive_id"])
        results.append({"archive_id": entry["archive_id"], "status": "HASH_VERIFIED",
                        "safe_to_publish": False, "inspection": actual})
    if len(results) != 4:
        raise ArchiveAuditError("expected four original historical packages")
    return {"status": "HASH_VERIFIED_NOT_PUBLICATION_APPROVED", "archives": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit historical ZIP bytes without extraction")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit_catalog(args.catalog, args.directory), ensure_ascii=False, indent=2))
        return 0
    except (ArchiveAuditError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
