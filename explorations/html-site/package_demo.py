#!/usr/bin/env python3
"""Build a reproducible *source* demo package, never a Windows EXE release.

The bundle includes only the C11 backend runtime source, HTML frontend assets,
fixture creation code, pinned test requirements and the isolated E1 experiment.
It NEVER includes actual local SQLite/knowledge contents or user data.

Usage:
  python explorations/html-site/package_demo.py --output dist/srw-e1-demo
  python explorations/html-site/package_demo.py --verify dist/srw-e1-demo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COPY_DIRS = (
    "backend/srw",
    "frontend/dist",
    "explorations/html-site",
)
COPY_FILES = (
    "browser_acceptance/serve.py",
    "convergence_tests/knowledge_fixture.py",
    "requirements-ci.txt",
    "VERSION",
)
FORBIDDEN_DIRS = {
    ".git", ".venv", ".e1-demo-venv", "__pycache__", ".pytest_cache",
    "data", "blobs", "backups", "node_modules", "logs",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".log"}
EXCLUDE_FILE_NAMES = {"instance.json", "pending_restore.json", ".env"}
MAX_FILE_BYTES = 24 * 1024 * 1024
MAX_BUNDLE_BYTES = 100 * 1024 * 1024

START_HERE = r"""@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "SRW_E1_PACKAGE_ROOT=%~dp0"
if not exist "explorations\html-site\run_e1_demo_windows.cmd" (
    echo Demo package is incomplete. Extract the entire ZIP before running.
    pause
    exit /b 2
)
call "explorations\html-site\run_e1_demo_windows.cmd" %*
exit /b %ERRORLEVEL%
"""

START_E2 = r"""@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "SRW_E1_PACKAGE_ROOT=%~dp0"
if not exist "explorations\html-site\run_e2_demo.py" (
    echo E2 synthetic experiment is missing. Re-extract the full artifact ZIP.
    pause
    exit /b 2
)
echo E2 can modify ONLY disposable synthetic Action Plans.
echo E2 does NOT connect to any existing SRW EXE or real user database.
call "explorations\html-site\run_e1_demo_windows.cmd" --e2 %*
exit /b %ERRORLEVEL%
"""

START_E3 = r"""@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "SRW_E1_PACKAGE_ROOT=%~dp0"
if not exist "explorations\html-site\run_e3_demo.py" (
    echo E3 disposable transactional experiment is missing.
    pause
    exit /b 2
)
echo E3 launches ONE temporary C11 Core with SQLite atomic CAS.
echo It NEVER attaches to a real EXE or an existing data directory.
call "explorations\html-site\run_e1_demo_windows.cmd" --e3 %*
exit /b %ERRORLEVEL%
"""

START_E4 = r"""@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "SRW_E1_PACKAGE_ROOT=%~dp0"
if not exist "explorations\html-site\run_e4_demo.py" (
    echo E4 shared-Core laboratory is missing. Re-extract the full ZIP.
    pause
    exit /b 2
)
echo E4 launches ONE disposable C11 Core and TWO browser carrier surfaces.
echo The desktop surrogate is NOT a real Windows EXE.
call "explorations\html-site\run_e1_demo_windows.cmd" --e4 %*
exit /b %ERRORLEVEL%
"""

START_README = """# SRW HTML E1–E4: real C11 source demo (NOT a Windows EXE)

This E1–E4 source package is assembled in GitHub Actions from the isolated
HTML exploration branch. It contains a real C11 backend + browser frontend
and synthetic sample generators, but NO real user data and NO embedded Python.

## Run on Windows

1. Extract the complete downloaded ZIP into a new directory.
2. Install Python 3.12 if needed (from a source you trust).
3. Double-click START_HERE.cmd at the top level.
4. First launch installs pinned dependencies to
   explorations/html-site/.e1-demo-venv.
5. The browser opens LIVE · web · GET-only. Use the sample project/candidates.
6. Press Ctrl+C in the command window to stop and delete the TEMPORARY
   SQLite/Knowledge sample workspace.

## Optional: E2 two-client write experiment

Double-click START_E2.cmd. This launches another disposable C11 backend and
opens a Web UI that allows a narrowly scoped Action Plan PATCH for synthetic
candidate IDs created by that demo. Open E2 in two separate browser tabs and
test ETag / If-Match conflict handling (412 on stale writes).

E2 does not change production records and is NOT production-grade transactional
concurrency protection; the official SRW Core still needs its own atomic CAS.

## Optional: E3 atomic SQLite transaction laboratory

Double-click START_E3.cmd. Like E2 it creates a **brand-new temporary**
real C11 backend and synthetic data, but it installs a synthetic-only
Starlette Action Plan route that performs the ETag check, business change,
business audit event and revision update in **one SQLite transaction**.
E3 is an experimental Core route: no change to official production schema
or API is made. This proves the transactional approach, but legacy writers
bypassing E3 are not protected, and real user workspaces remain unsupported.

## Optional: E4 independent Core lifecycle, two browser carrier surfaces

Double-click START_E4.cmd. One disposable C11 Core is started under an
independent owner, and two browser endpoints both attach to the same Core.
Closing one UI tab does NOT terminate the backend. The E4 smoke test
programmatically detaches either carrier and verifies the other can still
read and write synthetic records, then reattaches to the same Core.

The 'desktop' UI is explicitly a browser/WebView2 **surrogate**. E4 is NOT
a real WPF/Windows EXE integration test.

This is a local E1–E4 source demo, NOT a C11 Native EXE, NOT a production runtime
and NOT a replacement for an existing 0.8.x Portable installation.

If the batch script reports a missing repository root, the source package was
extracted incompletely or the script was copied away from its folders.
Keep START_HERE.cmd, backend/, frontend/, browser_acceptance/,
convergence_tests/ and explorations/ in the same extracted directory.

Run 'python explorations/html-site/package_demo.py --verify .' to check
the SHA256 manifest if you have Python available.
"""


def _eligible(source: Path, relative: Path) -> bool:
    if source.is_symlink():
        raise ValueError(f"Package refuses symlink: {relative}")
    if any(part in FORBIDDEN_DIRS for part in relative.parts):
        return False
    if source.is_dir():
        return True
    if source.name in EXCLUDE_FILE_NAMES or source.suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Unexpected oversized source asset: {relative}")
    return True


def build(destination: Path) -> None:
    destination = destination.expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents and destination == ROOT / "explorations" / "html-site":
        raise ValueError("Refusing to package over the source repository")
    if destination.exists():
        if any(destination.iterdir()):
            raise ValueError("Output directory must not already contain files")
    else:
        destination.mkdir(parents=True)
    size_total = 0
    count = 0
    for item in COPY_DIRS + COPY_FILES:
        src = ROOT / item
        if not src.exists():
            raise FileNotFoundError(f"Required source component missing: {src}")
        sources = src.rglob("*") if src.is_dir() else [src]
        for source in sources:
            rel = source.relative_to(ROOT)
            if not _eligible(source, rel):
                continue
            if source.is_dir():
                (destination / rel).mkdir(parents=True, exist_ok=True)
                continue
            size_total += source.stat().st_size
            if size_total > MAX_BUNDLE_BYTES:
                raise ValueError("Unexpected demo package size; aborting")
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            count += 1

    (destination / "START_HERE.cmd").write_text(START_HERE, encoding="utf-8", newline="\r\n")
    (destination / "START_E2.cmd").write_text(START_E2, encoding="utf-8", newline="\r\n")
    (destination / "START_E3.cmd").write_text(START_E3, encoding="utf-8", newline="\r\n")
    (destination / "START_E4.cmd").write_text(START_E4, encoding="utf-8", newline="\r\n")
    (destination / "PACKAGE_README.md").write_text(START_README, encoding="utf-8")
    inventory = {}
    for file in sorted(destination.rglob("*")):
        if file.is_file():
            relative = file.relative_to(destination).as_posix()
            inventory[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
    (destination / "PACKAGE_MANIFEST.sha256.json").write_text(
        json.dumps({"format": "srw-e1-source-demo-v1", "files": inventory},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    verify(destination)
    print(f"PASS: {count} source files copied ({size_total} bytes)", flush=True)
    print(f"Demo package: {destination}", flush=True)


def verify(destination: Path) -> None:
    destination = destination.expanduser().resolve()
    manifest = destination / "PACKAGE_MANIFEST.sha256.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("format") != "srw-e1-source-demo-v1":
        raise ValueError("Unexpected manifest format")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Manifest is empty")
    seen = set()
    for relative, expected in files.items():
        src = destination / relative
        if not src.is_file() or src.is_symlink() or src.resolve() != destination.joinpath(relative).resolve():
            raise ValueError(f"Missing/invalid source file: {relative}")
        if hashlib.sha256(src.read_bytes()).hexdigest() != expected:
            raise ValueError(f"SHA256 mismatch: {relative}")
        seen.add(relative)
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*") if path.is_file()
        and path.name != "PACKAGE_MANIFEST.sha256.json"
    }
    if actual != seen:
        raise ValueError(f"Unexpected/missing packaged files: {sorted(actual ^ seen)}")
    print(f"PASS: validated {len(files)} packaged files", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.output:
        build(args.output)
    else:
        verify(args.verify)


if __name__ == "__main__":
    main()
