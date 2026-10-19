"""Deterministic source+WPF Host Windows Native CANDIDATE upgrade kit.

This artifact needs the separately supplied exact d8d032d prepared ZIP.
It contains NO Python Runtime, real Knowledge database, user data or credentials.
It is NOT an installer/EXE release, and a successful build is NOT GUI acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_native_from_source_host import _verify_host, verified_git_sha
from scripts.native_payload import PayloadError, read_manifest, safe_path, sha256_file
from scripts.check_source_integrity import validate

TRUTH_NAME = "SOURCE_KIT_PROVENANCE.json"
STATUS = "SOURCE_AND_HOST_ONLY_UNVERIFIED_GUI"

CMD = r"""@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
if not exist "%~1" (
    echo [BLOCKED] Exact d8d032d prepared ZIP not found.
    exit /b 2
)
where py >nul 2>nul
if errorlevel 1 (
    echo [BLOCKED] Python 3.12 launcher not found. Install Python 3.12.
    exit /b 2
)
py -3.12 "%~dp0scripts\rebuild_native_from_prepared.py" --source "%~dp0" --host "%~dp0windows-host" --base-zip "%~1" --out "%~2"
if errorlevel 1 (
    echo [BLOCKED] Assembly failed. Previous prepared ZIP and existing data were not overwritten.
    exit /b 2
)
echo [CANDIDATE] New UNVERIFIED_GUI ZIP created. Independent Windows GUI acceptance is required.
exit /b 0
:usage
echo.
echo SRW C11 Windows Native candidate assembler (NOT an installed application)
echo.
echo Usage:
echo   BUILD_C11_CANDIDATE.cmd "D:\SRW\prepared-d8d032d.zip" "D:\SRW\new-C11-UNVERIFIED_GUI.zip"
echo.
echo The input must be the EXACT pinned d8d032d prepared Native ZIP.
echo The output cannot already exist. No real user database is opened or migrated.
exit /b 2
"""

README = """# SRW C11 Native upgrade kit (source + WPF Host, NOT a portable release)

This kit contains the complete SHA-256 verified C11 source and an unsigned,
**same-commit** source-built Windows WPF Host. It does not contain Python Runtime,
Knowledge databases or any user data.

To build a NEW candidate on a Windows x64 machine:

1. Download this matching-commit kit ZIP from the successful GitHub Actions job,
   then extract it into a NEW folder. Do not overwrite your existing SRW.
2. Use the immutable historical, verified
   SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip
   (SHA-256 27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb).
   **Do not substitute** a v0.8.8 Web package or a user workspace.
3. With system Python 3.12 installed, open CMD in the extracted kit and run:
   BUILD_C11_CANDIDATE.cmd "D:\\SRW\\prepared-d8d032d.zip" "D:\\SRW\\SRW_C11_new_UNVERIFIED_GUI.zip"
4. The utility verifies the exact old ZIP hash, Runtime + five Knowledge
   manifests and SQLite integrity, current dependency compatibility, source
   hashes, rebuilt Host git SHA and SHA, and all final ZIP members.\n   On Windows it independently executes extracted embedded Python -I -B\n   and checks 13 imports from this Runtime before writing a candidate.\n   The old ZIP does NOT contain RUNTIME_UPGRADE_AUDIT.json.
5. Unzip the resulting CANDIDATE into a NEW folder. Run separate static,
   embedded-Python, backend and WPF/WebView2 acceptance. Do not use it against
   your existing v0.8.x data or claim RC/GA until these passes are recorded.

If the inputs do not match exactly, assembly fails with BLOCKED and leaves
the existing prepared ZIP, knowledge, runtime, old application and data intact.

Note: this kit and the produced candidate are not code-signed. GitHub source
hashes and artifact provenance are integrity/audit evidence, not signatures.
"""


def package(
    root: Path, host: Path, out: Path, sha: str, *,
    enforce_git: bool = True,
) -> dict:
    root = root.resolve(strict=True)
    host = host.resolve(strict=True)
    out = out.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PayloadError("full 40-character Git commit SHA required")
    if enforce_git and verified_git_sha(root) != sha:
        raise PayloadError("source checkout does not match workflow commit")
    if out.exists() or out.is_symlink() or out.is_relative_to(root):
        raise PayloadError("kit ZIP must be new and outside source checkout")
    errors = validate(root)
    if errors:
        raise PayloadError("source manifest failed: " + "; ".join(errors[:3]))
    host_truth = _verify_host(host, sha)
    names = read_manifest(root / "SOURCE_MANIFEST.sha256")
    payload = {}
    for relative, digest in names.items():
        path = root.joinpath(*safe_path(relative))
        if path.is_symlink() or not path.is_file():
            raise PayloadError("source input missing or symlinked")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise PayloadError("source SHA manifest mismatch")
        payload[relative] = content
    payload["SOURCE_MANIFEST.sha256"] = (
        root / "SOURCE_MANIFEST.sha256"
    ).read_bytes()
    for file in sorted(host.rglob("*")):
        if file.is_symlink():
            raise PayloadError("symlink in source-built Host candidate")
        if file.is_file():
            rel = file.relative_to(host).as_posix()
            safe_path(rel)
            payload["windows-host/" + rel] = file.read_bytes()
    if {"BUILD_C11_CANDIDATE.cmd", "SOURCE_KIT_PROVENANCE.json"} & set(payload):
        raise PayloadError("upgrade kit file name already reserved")
    payload["BUILD_C11_CANDIDATE.cmd"] = CMD.replace("\n", "\r\n").encode("utf-8")
    payload["SOURCE_KIT_README.md"] = README.encode("utf-8")
    payload[TRUTH_NAME] = (json.dumps({
        "schema": "srw.native-upgrade-source-kit.v1",
        "status": STATUS,
        "git_sha": sha,
        "source_manifest_sha256": hashlib.sha256(
            payload["SOURCE_MANIFEST.sha256"]
        ).hexdigest(),
        "host_sha256": host_truth["host_sha256"],
        "runtime_included": False,
        "knowledge_included": False,
        "gui_accepted": False,
    }, indent=2, sort_keys=True) + "\n").encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".partial")
    if tmp.exists():
        raise PayloadError("unclaimed partial ZIP already exists")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(tmp) as archive:
            if set(archive.namelist()) != set(payload):
                raise PayloadError("upgrade kit ZIP member allowlist mismatch")
            for name, value in payload.items():
                if hashlib.sha256(archive.read(name)).digest() != hashlib.sha256(value).digest():
                    raise PayloadError("upgrade kit member hash mismatch")
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "status": STATUS,
        "sha": sha,
        "host_sha256": host_truth["host_sha256"],
        "zip_sha256": sha256_file(out),
        "source_files": len(names),
        "archive_members": len(payload),
        "runtime_included": False,
        "knowledge_included": False,
        "gui_accepted": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    try:
        result = package(args.root, args.host, args.out, args.commit)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except (PayloadError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
