"""Static/embedded-backend acceptance of SOURCE_REBUILD C11 Native candidate.

Supports the source-built WPF Host provenance used since c8431ca7,
without modifying or re-signing the packaged files or asserting GUI pass.
The predecessor-only Prepared verifier retains its original stricter contract.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile

# Verification must never alter the audited extraction while importing local
# scripts. Otherwise our own __pycache__ files fail the exact member allowlist.
# Set this BEFORE importing any repository package, including scripts itself.
if __name__ == "__main__":
    sys.dont_write_bytecode = True
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_native_from_source_host import _verify_host
from scripts.check_embedded_runtime_compatibility import check
from scripts.native_payload import (
    KNOWLEDGE, PROVENANCE, PayloadError, _host_members, audit_runtime,
    audit_zip, read_manifest, sha256_file, verified_input,
)
from scripts.portable_input_preflight import knowledge_checks
from scripts.verify_prepared_native import smoke_windows

SCHEMA = "srw.native-source-built-host-provenance.v1"
ORIGIN = "source_rebuild_not_legacy_carrier"


def validate_rebuild_truth(provenance: dict, *, source_sha: str,
                           source_hash: str, runtime_hash: str,
                           host_hash: str, version: str) -> None:
    """Require explicit, matching provenance for source-built (not inherited) Host."""
    if not isinstance(provenance, dict):
        raise PayloadError("Native source rebuild provenance is not a JSON object")
    expected = {
        "schema": SCHEMA,
        "artifact_status": "UNVERIFIED_GUI",
        "host_origin": ORIGIN,
        "host_source_git_sha": source_sha,
        "host_executable_sha256": host_hash,
        "source_manifest_sha256": source_hash,
        "runtime_manifest_sha256": runtime_hash,
        "target_version": version,
        "c11_pinned_dependency_metadata": "MATCH",
        "independent_legacy_origin_provenance_verified": False,
        "windows_gui_accepted": False,
    }
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise PayloadError("Native source Host full Git SHA missing")
    for key, value in expected.items():
        if type(provenance.get(key)) is not type(value) or provenance.get(key) != value:
            raise PayloadError(f"source-rebuilt Native provenance field mismatch: {key}")


def inspect_rebuilt(root: Path, *, archive: Path | None = None,
                    expected_archive_sha256: str | None = None) -> dict:
    was_symlink = root.is_symlink()
    root = root.resolve(strict=True)
    if was_symlink or not root.is_dir() or root.is_symlink():
        raise PayloadError("rebuilt Native application root must be a directory, not a symlink")
    src_manifest = root / "SOURCE_MANIFEST.sha256"
    runtime_manifest = root / "PRODUCTION_RUNTIME.sha256"
    knowledge_manifest = root / "PRODUCTION_KNOWLEDGE.sha256"
    source = read_manifest(src_manifest)
    for name, digest in source.items():
        verified_input(root, name, digest)
    runtime = root / "runtime"
    runtime_inventory = read_manifest(runtime_manifest, runtime=True)
    audit_runtime(runtime, runtime_manifest)
    know = read_manifest(knowledge_manifest)
    if set(know) != {f"{name}/knowledge.db" for name in KNOWLEDGE}:
        raise PayloadError("Native Knowledge inventory must contain exactly the five production DBs")
    checks = knowledge_checks(root / "knowledge" / "active", knowledge_manifest)
    if len(checks) != 6 or any(x["status"] != "PASS" for x in checks):
        raise PayloadError("Native Knowledge database SHA/SQLite integrity check failed")
    dependency = check(runtime, root / "requirements-ci.txt")
    if dependency.get("status") != "PINNED_METADATA_MATCH" or dependency.get("c11_overlay_on_path") is not True:
        raise PayloadError("Native effective embedded Runtime is incompatible with pinned C11 dependencies")
    identity_path = root / PROVENANCE
    if identity_path.is_symlink() or not identity_path.is_file():
        raise PayloadError("source-built Host provenance missing")
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, OSError, ValueError) as exc:
        raise PayloadError("source-built Host provenance unreadable") from exc
    sha = identity.get("host_source_git_sha", "") if isinstance(identity, dict) else ""
    host = root / "windows-host"
    host_meta = _verify_host(host, sha)
    members = _host_members(host)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    validate_rebuild_truth(
        identity,
        source_sha=sha,
        source_hash=sha256_file(src_manifest),
        runtime_hash=sha256_file(runtime_manifest),
        host_hash=host_meta["host_sha256"],
        version=version,
    )
    expected_paths = (
        set(source) |
        {"SOURCE_MANIFEST.sha256", "PRODUCTION_RUNTIME.sha256",
         "PRODUCTION_KNOWLEDGE.sha256", PROVENANCE} |
        {"runtime/" + rel for rel in runtime_inventory} |
        {"knowledge/active/" + rel for rel in know} |
        set(members)
    )
    actual_paths = set()
    for p in root.rglob("*"):
        if p.is_symlink():
            raise PayloadError("symlink in source-rebuilt candidate")
        if p.is_file():
            actual_paths.add(p.relative_to(root).as_posix())
    if actual_paths != expected_paths:
        raise PayloadError(
            "candidate member allowlist mismatch: "
            f"unexpected={len(actual_paths - expected_paths)}, missing={len(expected_paths - actual_paths)}"
        )
    zip_sha = None
    if archive is not None:
        if archive.is_symlink():
            raise PayloadError("candidate ZIP must not be a symbolic link")
        archive = archive.resolve(strict=True)
        if expected_archive_sha256 is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", expected_archive_sha256):
                raise PayloadError("expected Native ZIP hash must be 64 lowercase hex characters")
            if sha256_file(archive) != expected_archive_sha256:
                raise PayloadError("independent full Native ZIP SHA-256 mismatch")
        z = audit_zip(archive, root, host)
        if z.get("status") != "PASS":
            raise PayloadError("Native ZIP member verification blocked")
        zip_sha = z["candidate_sha256"]
    elif expected_archive_sha256 is not None:
        raise PayloadError("expected ZIP SHA requires --zip")
    return {
        "status": "SOURCE_REBUILD_STATIC_PASS_GUI_NOT_YET_ACCEPTED",
        "source_git_sha": sha,
        "source_files": len(source),
        "runtime_files": len(runtime_inventory),
        "knowledge_databases": len(KNOWLEDGE),
        "host_files": len(members),
        "zip_sha256": zip_sha,
        "embedded_backend_smoke": "NOT_RUN",
        "wpf_webview2_gui_accepted": False,
        "source_host_identity_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="New extracted source-rebuilt C11 Native candidate")
    parser.add_argument("--zip", type=Path, help="Original candidate ZIP for strict full archive member verification")
    parser.add_argument("--expected-zip-sha256", help="External, previously recorded 64-character ZIP SHA-256")
    parser.add_argument("--backend-smoke", action="store_true", help="On Windows, run real embedded Python and disposable loopback Core")
    parser.add_argument("--evidence", type=Path, required=True, help="New JSON report outside immutable application root")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    try:
        app = args.root.resolve(strict=True)
        if evidence.is_relative_to(app):
            raise PayloadError("evidence must be outside immutable candidate application")
        if evidence.exists() or evidence.is_symlink():
            raise PayloadError("evidence already exists; never overwrite an acceptance record")
        if args.backend_smoke and os.name != "nt":
            raise PayloadError("embedded Windows backend smoke requires a Windows x64 host")
        result = inspect_rebuilt(
            app, archive=args.zip,
            expected_archive_sha256=args.expected_zip_sha256,
        )
        if args.backend_smoke:
            result["embedded_backend_smoke"] = smoke_windows(app)
            result["status"] = "SOURCE_REBUILD_BACKEND_SMOKE_PASS_GUI_NOT_YET_ACCEPTED"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("x", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (PayloadError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__,
                          "reason": str(exc), "gui_accepted": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
