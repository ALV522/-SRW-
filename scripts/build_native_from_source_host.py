"""Assemble an UNVERIFIED Windows Native candidate using a rebuilt C11 WPF Host.

Alternative to inherited v0.8.8 carrier. Fail closed on any source, Runtime,
Knowledge, dependency, Host provenance or ZIP mismatch. Never execute the
embedded Python binary; Windows GUI acceptance is a separate manual gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_payload import (
    KNOWLEDGE, PROVENANCE, PayloadError, audit_runtime,
    audit_zip, read_manifest, sha256_file, verified_input, safe_path,
)
from scripts.portable_input_preflight import knowledge_checks
from scripts.check_embedded_runtime_compatibility import check


def verified_git_sha(root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0 or len(proc.stdout.strip()) != 40:
        raise PayloadError("exact Git source revision required")
    return proc.stdout.strip()


def _verify_host(host: Path, expected_sha: str) -> dict:
    if not host.is_dir() or host.is_symlink():
        raise PayloadError("source-built Windows Host directory missing")
    for file in host.rglob("*"):
        if file.is_symlink():
            raise PayloadError("symlinked Host payload")
        if file.is_file():
            relative = file.relative_to(host).as_posix()
            parts = [part.casefold() for part in relative.split("/")]
            leaf = parts[-1]
            if (any(p in {"data", "uploads", "backups", "workspace", "private", "secrets"} for p in parts)
                or leaf in {".env", "secrets.json", "credentials.json", "provider_secrets.json"}
                or leaf.endswith((".db", ".sqlite", ".key", ".pfx", ".pem"))):
                raise PayloadError("potentially private content in Windows Host input")
    metadata = host / "HOST_BUILD_CANDIDATE.json"
    if metadata.is_symlink() or not metadata.is_file():
        raise PayloadError("missing exact-source Windows Host candidate metadata")
    try:
        provenance = json.loads(metadata.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PayloadError("invalid rebuilt Host metadata") from exc
    actual = host / "SmartRecruitmentWorkbench.exe"
    if actual.is_symlink() or not actual.is_file():
        raise PayloadError("rebuilt WPF Host EXE missing")
    if (provenance.get("git_sha") != expected_sha or
        provenance.get("host_sha256") != sha256_file(actual) or
        provenance.get("status") != "COMPILED_ONLY_UNVERIFIED_GUI" or
        provenance.get("gui_accepted") is not False or
        provenance.get("runtime_included") is not False or
        provenance.get("knowledge_included") is not False):
        raise PayloadError("WPF Host source build identity/status mismatch")
    truth = host / "DOTNET_BUILD_TRUTH.json"
    if truth.is_symlink() or not truth.is_file():
        raise PayloadError("rebuilt Host must include digest-bound DOTNET_BUILD_TRUTH")
    try:
        obj = json.loads(truth.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PayloadError("invalid Host build truth") from exc
    if (obj.get("source_git_sha") != expected_sha or
        (obj.get("outputs") or {}).get("executable_sha256") != provenance["host_sha256"]):
        raise PayloadError("rebuilt Host digest binding failed")
    return provenance


def assemble(root: Path, inputs: Path, host: Path, out: Path, *,
             expected_git_sha: str | None = None,
             requirements: Path | None = None) -> dict:
    root = root.resolve(strict=True)
    inputs = inputs.resolve(strict=True)
    host = host.resolve(strict=True)
    requirements = requirements or (root / "requirements-ci.txt")
    source_manifest = root / "SOURCE_MANIFEST.sha256"
    expected_sha = expected_git_sha or verified_git_sha(root)
    host_identity = _verify_host(host, expected_sha)
    source = read_manifest(source_manifest)
    for name, digest in source.items():
        verified_input(root, name, digest)
    if not (root / "VERSION").is_file():
        raise PayloadError("C11 source VERSION is missing")
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    runtime_dir = inputs / "runtime"
    runtime_manifest = inputs / "PRODUCTION_RUNTIME.sha256"
    runtime_entries = read_manifest(runtime_manifest, runtime=True)
    audit_runtime(runtime_dir, runtime_manifest)

    dependency_result = check(runtime_dir, requirements)
    if dependency_result["status"] != "PINNED_METADATA_MATCH":
        raise PayloadError("recovered legacy Python is not compatible with current C11 pinned requirements")
    if dependency_result.get("c11_overlay_on_path"):
        report_path = inputs / "RUNTIME_UPGRADE_AUDIT.json"
        if report_path.is_symlink() or not report_path.is_file():
            raise PayloadError("C11 overlay requires an embedded Python smoke audit")
        try:
            upgrade_truth = json.loads(report_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError, UnicodeError) as exc:
            raise PayloadError("invalid C11 embedded Python smoke audit") from exc
        if (upgrade_truth.get("schema") != "srw.c11-runtime-overlay-build.v1" or
            upgrade_truth.get("status") != "C11_RUNTIME_SMOKE_PASS" or
            upgrade_truth.get("embedded_python_smoke") is not True or
            upgrade_truth.get("source_runtime_unmodified") is not True or
            upgrade_truth.get("requirements_sha256") != sha256_file(requirements)):
            raise PayloadError("embedded Python smoke audit or C11 dependency identity mismatch")
    knowledge_dir = inputs / "knowledge" / "active"
    knowledge_manifest = inputs / "PRODUCTION_KNOWLEDGE.sha256"
    checked = knowledge_checks(knowledge_dir, knowledge_manifest)
    if len(checked) != 6 or any(row["status"] != "PASS" for row in checked):
        raise PayloadError("five Knowledge hashes/SQLite checks did not pass")
    if out.exists():
        raise PayloadError("refusing to overwrite a previously created Windows ZIP")

    # No unreviewed source tree, local workspace, user backups or API secrets are copied.
    with tempfile.TemporaryDirectory(prefix="srw-native-source-host-") as td:
        stage = Path(td) / "stage"
        stage.mkdir()
        for rel, digest in source.items():
            origin = verified_input(root, rel, digest)
            target = stage.joinpath(*safe_path(rel))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
        shutil.copyfile(source_manifest, stage / "SOURCE_MANIFEST.sha256")
        for filename in ("PRODUCTION_RUNTIME.sha256", "PRODUCTION_KNOWLEDGE.sha256"):
            shutil.copyfile(inputs / filename, stage / filename)
        for rel, digest in runtime_entries.items():
            origin = verified_input(runtime_dir, rel, digest)
            dest = stage / "runtime" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, dest)
        for name in KNOWLEDGE:
            rel = f"{name}/knowledge.db"
            origin = knowledge_dir / rel
            dest = stage / "knowledge" / "active" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, dest)
        for origin in sorted(host.rglob("*")):
            if origin.is_symlink():
                raise PayloadError("symlinked Host input is forbidden")
            if origin.is_file():
                rel = origin.relative_to(host).as_posix()
                target = stage / "windows-host" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
        provenance = {
            "schema": "srw.native-source-built-host-provenance.v1",
            "artifact_status": "UNVERIFIED_GUI",
            "host_origin": "source_rebuild_not_legacy_carrier",
            "host_source_git_sha": expected_sha,
            "host_executable_sha256": host_identity["host_sha256"],
            "source_manifest_sha256": sha256_file(source_manifest),
            "runtime_manifest_sha256": sha256_file(runtime_manifest),
            "target_version": version,
            "c11_pinned_dependency_metadata": "MATCH",
            "independent_legacy_origin_provenance_verified": False,
            "windows_gui_accepted": False,
        }
        dest = stage / PROVENANCE
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        temp_zip = out.parent / (out.name + ".tmp")
        try:
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        zipped.write(path, path.relative_to(stage).as_posix())
            checked_zip = audit_zip(temp_zip, stage, host)
            os.replace(temp_zip, out)
        finally:
            temp_zip.unlink(missing_ok=True)
    return {
        "status": "CANDIDATE_UNVERIFIED_GUI",
        "zip_sha256": sha256_file(out),
        "member_count": checked_zip["files_verified"],
        "source_git_sha": expected_sha,
        "host_origin": "source_rebuild",
        "windows_gui_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(assemble(args.root, args.inputs, args.host, args.out),
                         indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__,
                          "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
