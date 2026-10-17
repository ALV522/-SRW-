"""Fail-closed inventory of separately supplied Portable assembly inputs.

This DOES NOT assemble a Portable/Native ZIP or certify Windows GUI behavior.
A supplied knowledge manifest must come from an independently audited release,
not from regenerating checksums of unknown or synthetic Knowledge DBs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

DB_TABLES = {
    "taxonomy": "alias_fts",
    "job_info": "profile_fts",
    "competency": "competency_fts",
    "market_reference": "beijing_core_field",
    "reference": "reference_entity_fts",
}
EXPECTED = {f"{name}/knowledge.db" for name in DB_TABLES}
DIGEST_LINE = re.compile(r"^([0-9a-fA-F]{64})  ([A-Za-z_]+/knowledge\.db)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def knowledge_checks(knowledge: Path, manifest: Path) -> list[dict]:
    if not manifest.is_file():
        return [{"name": "knowledge_manifest", "status": "BLOCKED", "reason": "External audited SHA-256 inventory missing"}]
    values = {}
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            match = DIGEST_LINE.fullmatch(line.strip())
            if not match or match[2] not in EXPECTED or match[2] in values:
                raise ValueError("invalid, duplicate or unexpected manifest entry")
            values[match[2]] = match[1].lower()
    except (OSError, UnicodeError, ValueError):
        return [{"name": "knowledge_manifest", "status": "BLOCKED", "reason": "Audited manifest is invalid or contains unexpected entries"}]
    if set(values) != EXPECTED:
        return [{"name": "knowledge_manifest", "status": "BLOCKED", "reason": "Expected exactly five Knowledge DB hashes"}]
    checks = [{"name": "knowledge_manifest", "status": "PASS", "reason": "Five external checksums parsed; provenance must be audited separately"}]
    for name, table in DB_TABLES.items():
        rel = f"{name}/knowledge.db"
        path = knowledge / name / "knowledge.db"
        if not path.is_file():
            checks.append({"name": rel, "status": "BLOCKED", "reason": "Knowledge DB missing"})
            continue
        if sha256_file(path) != values[rel]:
            checks.append({"name": rel, "status": "BLOCKED", "reason": "Audited Knowledge hash mismatch"})
            continue
        try:
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                integrity = db.execute("PRAGMA quick_check").fetchone()
                table_exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view')",
                    (table,),
                ).fetchone()
            if not integrity or integrity[0] != "ok" or not table_exists:
                raise ValueError("schema/quick_check failed")
        except (sqlite3.DatabaseError, OSError, ValueError):
            checks.append({"name": rel, "status": "BLOCKED", "reason": "SQLite integrity or required search table invalid"})
            continue
        checks.append({"name": rel, "status": "PASS", "reason": "Hash and SQLite read-only checks passed"})
    return checks


def audit(
    root: Path,
    *,
    carrier: Path | None = None,
    runtime: Path | None = None,
    knowledge: Path | None = None,
    knowledge_manifest: Path | None = None,
) -> dict:
    root = Path(root)
    carrier = Path(carrier) if carrier is not None else root / "SRW_v0.8.8_Windows_Portable.zip"
    runtime = Path(runtime) if runtime is not None else root / "runtime"
    knowledge = Path(knowledge) if knowledge is not None else root / "knowledge" / "active"
    knowledge_manifest = Path(knowledge_manifest) if knowledge_manifest is not None else root / "PRODUCTION_KNOWLEDGE.sha256"
    host_truth = json.loads((root / "WINDOWS_NATIVE_HOST_STATUS.json").read_text(encoding="utf-8"))
    required_hash = host_truth["binary_inheritance"]["required_sha256"].lower()
    checks = []
    if not carrier.is_file():
        checks.append({"name": "windows_carrier", "status": "BLOCKED", "reason": "Exact audited Windows carrier ZIP missing"})
    elif sha256_file(carrier) != required_hash:
        checks.append({"name": "windows_carrier", "status": "BLOCKED", "reason": "Carrier digest does not match release truth"})
    else:
        checks.append({"name": "windows_carrier", "status": "PASS", "reason": "Exact audited carrier digest matches"})

    if (runtime / "python.exe").is_file():
        checks.append({"name": "embedded_runtime", "status": "PASS", "reason": "Embedded Python entrypoint present; executable/runtime smoke still required"})
    else:
        checks.append({"name": "embedded_runtime", "status": "BLOCKED", "reason": "Embedded Python runtime missing"})
    checks.extend(knowledge_checks(knowledge, knowledge_manifest))
    ready = all(x["status"] == "PASS" for x in checks)
    return {
        "schema": "srw.portable-input-preflight.v1",
        "inputs_complete": ready,
        "portable_built": False,
        "windows_gui_accepted": False,
        "production_knowledge_provenance_verified": False,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--carrier", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--knowledge", type=Path)
    parser.add_argument("--knowledge-manifest", type=Path)
    args = parser.parse_args()
    result = audit(args.root, carrier=args.carrier, runtime=args.runtime,
                   knowledge=args.knowledge, knowledge_manifest=args.knowledge_manifest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["inputs_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
