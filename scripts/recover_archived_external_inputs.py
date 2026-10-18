"""Recover pinned legacy Windows Python + five Knowledge DBs (no code execution).

This is a byte recovery operation, NOT C11 compatibility or GUI acceptance.
The historical ZIP bytes must match docs/history/LEGACY_ARCHIVES.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "history" / "LEGACY_ARCHIVES.json"
DATABASES = ("taxonomy", "job_info", "competency", "market_reference", "reference")
TABLES = ("alias_fts", "profile_fts", "competency_fts", "beijing_core_field", "reference_entity_fts")
ALLOWED_PUBLIC_CERT = "Lib/site-packages/certifi/cacert.pem"
R2_PREFIX = "SRW_v0.8.12-R2_Truth_Closure_Source/knowledge/active/"
PRIVATE = {"data", "backups", "uploads", "workspace", "candidates", "private", "secrets", "logs"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_path(name: str) -> None:
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute() or p.as_posix() != name or any(
        part in ("", "..", ".") or part.endswith((".", " "))
        for part in p.parts
    ):
        raise ValueError("unsafe ZIP member path")


def inventory(zipped: zipfile.ZipFile) -> None:
    seen: set[str] = set()
    for info in zipped.infolist():
        relative = info.filename.rstrip("/")
        check_path(relative)
        if relative.casefold() in seen:
            raise ValueError("duplicate ZIP member")
        seen.add(relative.casefold())
        if info.flag_bits & 1 or ((info.external_attr >> 16) & 0o170000) == 0o120000:
            raise ValueError("encrypted or symlinked ZIP input")


def copy_verified(zipped: zipfile.ZipFile, source: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with zipped.open(source) as src, target.open("xb") as dest:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            dest.write(chunk)
            digest.update(chunk)
    if sha256(target) != digest.hexdigest():
        raise ValueError("recovered file digest changed")
    return digest.hexdigest()


def matches_archive(path: Path, archive_id: str, catalog: dict) -> None:
    entries = [x for x in catalog["archives"] if x["archive_id"] == archive_id]
    if len(entries) != 1 or not path.is_file() or path.is_symlink():
        raise ValueError("source archive not found in pinned history")
    if path.stat().st_size != entries[0]["bytes"] or sha256(path) != entries[0]["sha256"]:
        raise ValueError("historical ZIP SHA-256 or byte count mismatch")


def recover(runtime_archive: Path, knowledge_archive: Path, target: Path,
            catalog: Path = CATALOG) -> dict:
    catalog_data = json.loads(catalog.read_text(encoding="utf-8"))
    if catalog_data.get("schema") != "srw.legacy-archive-catalog.v1":
        raise ValueError("unreviewed recovery catalog")
    matches_archive(runtime_archive, "legacy-alpha10-web-portable", catalog_data)
    matches_archive(knowledge_archive, "legacy-0812-r2-source", catalog_data)
    if target.exists() and any(target.iterdir()):
        raise ValueError("target recovery directory must be empty")
    target.mkdir(parents=True, exist_ok=True)
    runtime_hashes = []
    knowledge_hashes = []
    db_status = []
    with zipfile.ZipFile(runtime_archive) as runtime_zip, zipfile.ZipFile(knowledge_archive) as db_zip:
        inventory(runtime_zip)
        inventory(db_zip)
        runtime_members = [x.filename for x in runtime_zip.infolist()
                           if x.filename.startswith("runtime/") and not x.is_dir()]
        if not runtime_members or "runtime/python.exe" not in runtime_members:
            raise ValueError("missing embedded Windows Python")
        for member in sorted(runtime_members):
            rel = member[len("runtime/"):]
            check_path(rel)
            path_parts = rel.split("/")
            leaf = path_parts[-1].lower()
            if (any(x.lower() in PRIVATE for x in path_parts) or
                leaf in {"secrets.json", "credentials.json", "provider_secrets.json", ".env"} or
                (leaf.endswith((".pem", ".key", ".p12", ".pfx", ".db", ".sqlite"))
                 and rel != ALLOWED_PUBLIC_CERT)):
                raise ValueError("private or unexpected Runtime file")
            digest = copy_verified(runtime_zip, member, target / "runtime" / rel)
            runtime_hashes.append(f"{digest}  {rel}")
        for name, table in zip(DATABASES, TABLES):
            rel = f"{name}/knowledge.db"
            src = R2_PREFIX + rel
            digest = copy_verified(db_zip, src, target / "knowledge" / "active" / rel)
            db_file = target / "knowledge" / "active" / rel
            with closing(sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Knowledge database integrity check failed")
                if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() is None:
                    raise ValueError("required Knowledge search table missing")
            knowledge_hashes.append(f"{digest}  {rel}")
            db_status.append({"name": name, "sha256": digest, "bytes": db_file.stat().st_size,
                              "sqlite_integrity": "ok"})
    (target / "PRODUCTION_RUNTIME.sha256").write_text("\n".join(runtime_hashes) + "\n", encoding="utf-8")
    (target / "PRODUCTION_KNOWLEDGE.sha256").write_text("\n".join(knowledge_hashes) + "\n", encoding="utf-8")
    report = {
        "schema": "srw.legacy-input-recovery.v1",
        "runtime_files_recovered": len(runtime_hashes),
        "knowledge_databases": db_status,
        "input_runtime_zip_sha256": sha256(runtime_archive),
        "input_knowledge_zip_sha256": sha256(knowledge_archive),
        "recovery": "PASS",
        "c11_python_dependencies_verified": False,
        "independent_origin_provenance_verified": False,
        "windows_host_verified": False,
        "windows_gui_accepted": False,
    }
    (target / "RECOVERY_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime-zip", required=True, type=Path)
    p.add_argument("--knowledge-zip", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(recover(args.runtime_zip, args.knowledge_zip, args.output),
                         indent=2, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        print(json.dumps({"recovery": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
