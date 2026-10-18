"""Build a separate C11-compatible Windows embedded Runtime from audited legacy bytes.

Run with an installed Windows CPython 3.12. Install *offline* from a reviewed
wheelhouse into Lib/c11-overlay, before legacy packages on python312._pth.
The original historical ZIP and source Runtime directory are NEVER modified.
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
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_payload import (
    PayloadError, audit_runtime, read_manifest, stage_runtime, sha256_file,
    safe_path, verified_input,
)
from scripts.check_embedded_runtime_compatibility import check
from scripts.portable_input_preflight import knowledge_checks

LEGACY_PTH = "Lib\\site-packages"
OVERLAY_PTH = "Lib\\c11-overlay"
IMPORTS = ("anyio", "certifi", "click", "h11", "httpcore", "httpx", "idna",
           "psutil", "pymupdf", "sqlalchemy", "starlette", "typing_extensions", "uvicorn")
SMOKE = (
    "import importlib,json,sys;"
    "mods=" + repr(IMPORTS) + ";"
    "loaded={name:importlib.import_module(name).__file__ for name in mods};"
    "assert sys.version_info[:2]==(3,12);"
    "print(json.dumps({'python':sys.version.split()[0],'imports':loaded}))"
)


def validate_wheelhouse(directory: Path) -> dict[str, str]:
    if directory.is_symlink() or not directory.is_dir():
        raise PayloadError("wheelhouse missing or symlinked")
    manifest = directory / "WHEELHOUSE.sha256"
    if manifest.is_symlink() or not manifest.is_file():
        raise PayloadError("audited Windows wheelhouse SHA manifest missing")
    expected = read_manifest(manifest)
    if not expected or any(not name.endswith(".whl") or "/" in name for name in expected):
        raise PayloadError("wheelhouse must list exact wheel basenames")
    present = {p.name for p in directory.iterdir() if p.is_file() and p.suffix == ".whl"}
    if present != set(expected):
        raise PayloadError("wheelhouse contains missing or unlisted wheels")
    for name, digest in expected.items():
        verified_input(directory, name, digest)
    return expected


def configure_isolated_path(runtime: Path) -> None:
    pth = runtime / "python312._pth"
    if pth.is_symlink() or not pth.is_file():
        raise PayloadError("embedded Python312._pth required")
    original = pth.read_text(encoding="utf-8-sig")
    lines = original.splitlines()
    if any(line.strip().lower().replace("/", "\\") == OVERLAY_PTH.lower() for line in lines):
        raise PayloadError("input Runtime already has a C11 overlay")
    indexes = [i for i, line in enumerate(lines)
               if line.strip().lower().replace("/", "\\") == LEGACY_PTH.lower()]
    if len(indexes) != 1:
        raise PayloadError("legacy Python site-packages entry must occur exactly once")
    lines.insert(indexes[0], OVERLAY_PTH)
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _new_manifest(root: Path) -> None:
    runtime = root / "runtime"
    entries: list[str] = []
    for file in sorted(runtime.rglob("*")):
        if file.is_symlink():
            raise PayloadError("output Runtime symlink")
        if file.is_file():
            relative = file.relative_to(runtime).as_posix()
            safe_path(relative)
            entries.append(f"{sha256_file(file)}  {relative}")
    path = root / "PRODUCTION_RUNTIME.sha256"
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    audit_runtime(runtime, path)


def upgrade(
    old: Path, wheelhouse: Path, destination: Path, requirements: Path,
    *,
    run_embedded_smoke: bool = True,
) -> dict:
    if sys.version_info[:2] != (3, 12) or os.name != "nt":
        raise PayloadError("Runtime upgrade requires Windows CPython 3.12 host")
    if destination.exists() and (destination.is_symlink() or not destination.is_dir() or any(destination.iterdir())):
        raise PayloadError("output directory must be empty")
    expected_wheels = validate_wheelhouse(wheelhouse)
    runtime = old / "runtime"
    audit_runtime(runtime, old / "PRODUCTION_RUNTIME.sha256")
    kchecks = knowledge_checks(old / "knowledge" / "active", old / "PRODUCTION_KNOWLEDGE.sha256")
    if len(kchecks) != 6 or any(checkrow["status"] != "PASS" for checkrow in kchecks):
        raise PayloadError("five inherited Knowledge DBs failed SHA/SQLite checks")

    # Stage into a disposable directory; publish only after every gate passes.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="srw-c11-runtime-rebuild-", dir=destination.parent) as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        stage_runtime(runtime, old / "PRODUCTION_RUNTIME.sha256", stage / "runtime")
        target_runtime = stage / "runtime"
        configure_isolated_path(target_runtime)
        overlay = target_runtime / "Lib" / "c11-overlay"
        overlay.mkdir(parents=True)
        install = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "--no-input", "--no-index",
            "--find-links", str(wheelhouse), "--no-compile",
            "--target", str(overlay), "-r", str(requirements),
        ]
        result = subprocess.run(install, capture_output=True, text=True, timeout=600, check=False)
        if result.returncode:
            raise PayloadError("offline Windows wheel installation failed: " + result.stderr[-1200:])
        metadata = check(target_runtime, requirements)
        if metadata["status"] != "PINNED_METADATA_MATCH" or not metadata["c11_overlay_on_path"]:
            raise PayloadError("offline C11 overlay did not satisfy pinned requirements")
        smoke = None
        if run_embedded_smoke:
            python = target_runtime / "python.exe"
            proc = subprocess.run([str(python), "-I", "-c", SMOKE],
                                  cwd=target_runtime, capture_output=True, text=True,
                                  timeout=100, check=False)
            if proc.returncode:
                raise PayloadError("actual embedded Python import smoke failed: " + proc.stderr[-1000:])
            try:
                smoke = json.loads(proc.stdout.strip())
            except (ValueError, UnicodeError):
                raise PayloadError("embedded Python smoke output invalid")
            # Imports must resolve inside the staged runtime, not global Python.
            for path in smoke["imports"].values():
                if not Path(path).resolve().is_relative_to(target_runtime.resolve()):
                    raise PayloadError("embedded Python imported outside isolated runtime")
        for name in ("PRODUCTION_KNOWLEDGE.sha256",):
            shutil.copyfile(old / name, stage / name)
        for file in (old / "knowledge" / "active").rglob("knowledge.db"):
            target = stage / "knowledge" / "active" / file.parent.name / "knowledge.db"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        _new_manifest(stage)
        result_truth = {
            "schema": "srw.c11-runtime-overlay-build.v1",
            "status": "C11_RUNTIME_SMOKE_PASS" if smoke else "METADATA_ONLY",
            "legacy_runtime_manifest_sha256": sha256_file(old / "PRODUCTION_RUNTIME.sha256"),
            "requirements_sha256": sha256_file(requirements),
            "wheelhouse_sha256": sha256_file(wheelhouse / "WHEELHOUSE.sha256"),
            "wheel_count": len(expected_wheels),
            "source_runtime_unmodified": True,
            "pinned_dependencies": metadata["pinned_dependencies"],
            "dependency_matches": metadata["matched"],
            "embedded_python_smoke": bool(smoke),
            "gui_accepted": False,
            "provider_live_tested": False,
        }
        (stage / "RUNTIME_UPGRADE_AUDIT.json").write_text(
            json.dumps(result_truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        stage.rename(destination)
    return result_truth


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--legacy-inputs", type=Path, required=True)
    p.add_argument("--wheelhouse", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--requirements", type=Path, default=Path(__file__).resolve().parents[1] / "requirements-ci.txt")
    args = p.parse_args()
    try:
        print(json.dumps(upgrade(args.legacy_inputs, args.wheelhouse, args.output, args.requirements),
                         ensure_ascii=False, indent=2))
        return 0
    except (PayloadError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
