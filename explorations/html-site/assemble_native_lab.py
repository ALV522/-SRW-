"""Assemble experimental *source-backed* Windows WPF demo, never Portable.

Consumes the already compiled host-only output plus a reviewed, narrowly scoped
C11 source list. The executable is the existing unmodified C# WPF host compiled
with .NET 10.0.302. Python 3.12 and .NET 10 Desktop Runtime remain EXTERNAL
requirements; all Knowledge and candidate data are synthetic only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE_DIRS=("backend/srw","frontend/dist")
SOURCE_FILES=(
    "scripts/run_local.py","scripts/launch_alpha10.py",
    "convergence_tests/knowledge_fixture.py",
    "requirements-ci.txt","VERSION","BUILD_INFO.json",
    "explorations/html-site/serve_e1.py",
    "explorations/html-site/synthetic_workspace.py",
)
BLOCKED={"data","knowledge","runtime",".venv",".git","__pycache__",
         ".e1-demo-venv","node_modules","logs","backups"}
BLOCKED_SUFFIXES={".db",".sqlite",".sqlite3",".pyc",".pyo",".log"}
MAX_BYTES=80*1024*1024


def digest(path:Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output:Path,host_dir:Path) -> None:
    out=output.resolve()
    host=host_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Refusing to overwrite a nonempty Native Lab folder")
    out.mkdir(parents=True,exist_ok=True)
    app=out/"app"
    size_total=0
    for path in SOURCE_DIRS+SOURCE_FILES:
        src=ROOT/path
        if not src.exists():
            raise FileNotFoundError(f"Native Lab required source missing: {path}")
        iterator=src.rglob("*") if src.is_dir() else [src]
        for file in iterator:
            relative=file.relative_to(ROOT)
            if file.is_symlink():
                raise ValueError("Native Lab forbids symlink source")
            if any(part in BLOCKED for part in relative.parts):
                continue
            if file.is_dir():
                (app/relative).mkdir(parents=True,exist_ok=True)
                continue
            if file.suffix.lower() in BLOCKED_SUFFIXES:
                continue
            size_total+=file.stat().st_size
            if size_total>MAX_BYTES:
                raise ValueError("Source size limit exceeded")
            target=app/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,target)
    # Existing WPF host output remains separate and hash-attested.
    truth_file=host/"WPF_HOST_SOURCE_BUILD_TRUTH.json"
    if not truth_file.is_file():
        raise FileNotFoundError("Pinned host-only provenance missing")
    truth=json.loads(truth_file.read_text(encoding="utf-8-sig"))
    if truth.get("artifact_kind")!="HOST_BINARY_ONLY" or truth.get("native_gui_accepted") is not False:
        raise ValueError("Invalid or overstated host provenance")
    host_output=app/"windows-host"
    host_output.mkdir(parents=True,exist_ok=True)
    source_paths={entry["file"]:entry["sha256"] for entry in truth["outputs"]}
    if "SmartRecruitmentWorkbench.exe" not in source_paths:
        raise ValueError("Reviewed host compiler did not produce executable")
    for name,sha in source_paths.items():
        if "/" in name or "\\" in name or name.startswith(".") or ".." in name:
            raise ValueError("Unsafe host build output name")
        src=host/name
        if not src.is_file() or digest(src)!=sha:
            raise ValueError(f"Untrusted/missing compiled host binary: {name}")
        shutil.copyfile(src,host_output/name)
    shutil.copyfile(truth_file,host_output/truth_file.name)
    shutil.copyfile(HERE/"run_native_lab.py",out/"run_native_lab.py")
    starter=r"""@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 --version >nul 2>&1
    if not errorlevel 1 (
        py -3.12 run_native_lab.py %*
        exit /b %ERRORLEVEL%
    )
)
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(sys.version_info[:2] != (3,12))"
    if not errorlevel 1 (
        python run_native_lab.py %*
        exit /b %ERRORLEVEL%
    )
)
echo A locally installed Python 3.12 is required for this SOURCE Native Lab.
echo This is NOT an embedded-Python SRW Portable release.
pause
exit /b 3
"""
    (out/"START_NATIVE_LAB.cmd").write_text(starter,encoding="utf-8",newline="\r\n")
    readme="""# SRW C11 Windows WPF Native SOURCE Lab — NOT Portable

This experimental Windows app uses the existing C11 WPF/WebView2 host compiled
from locked C# source, and the actual C11 Python API from source.

- Windows x64, locally installed Python 3.12 and .NET 10 Desktop Runtime
  plus Microsoft Edge WebView2 Runtime are required.
- Double-click START_NATIVE_LAB.cmd to create a test-only Python virtual
  environment and start the WPF host using synthetic Knowledge and temporary
  SQLite data. Initial dependency installation needs internet.
- WPF and Web share one host-owned Core. A read-only E1 Web bridge is also
  checked during --smoke, without opening any real user records.
- The app never attaches existing SRW 0.8.x data, migration state or secrets.
- A successful host-source build does not establish all GUI functionality
  or release-grade packaging. This is a development preview only.

The test data is disposable; stop the WPF window normally.
"""
    (out/"NATIVE_LAB_README.md").write_text(readme,encoding="utf-8")
    inventory={}
    for p in out.rglob("*"):
        if p.is_file():
            inventory[p.relative_to(out).as_posix()]=digest(p)
    (out/"NATIVE_LAB_MANIFEST.sha256.json").write_text(
        json.dumps({"schema":"srw.native-source-lab.v1",
                    "kind":"SOURCE_AND_HOST_ONLY",
                    "portable":False,"gui_accepted":False,
                    "embedded_python":False,"production_knowledge":False,
                    "files":dict(sorted(inventory.items()))},
                   indent=2,ensure_ascii=False)+"\n",
        encoding="utf-8"
    )
    verify(out)
    print(f"Native WPF source lab staged: {len(inventory)} files (NO bundled Python or user data)",flush=True)


def verify(directory:Path):
    folder=directory.resolve()
    manifest=json.loads((folder/"NATIVE_LAB_MANIFEST.sha256.json").read_text(encoding="utf-8"))
    if manifest.get("portable") is not False or manifest.get("embedded_python") is not False:
        raise ValueError("Native Lab provenance mismatch")
    expected=manifest.get("files") or {}
    if not isinstance(expected,dict) or not expected:
        raise ValueError("Missing Native Lab file list")
    actual={p.relative_to(folder).as_posix() for p in folder.rglob("*")
            if p.is_file() and p.name!="NATIVE_LAB_MANIFEST.sha256.json"}
    if actual!=set(expected):
        raise ValueError(f"Native Lab missing/unexpected files: {sorted(actual^set(expected))}")
    for name,sha in expected.items():
        src=folder/name
        if not src.is_file() or src.is_symlink() or digest(src)!=sha:
            raise ValueError(f"Native Lab hash mismatch: {name}")
    print(f"PASS: {len(expected)} Native Lab source/host hashes verified",flush=True)


def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output",type=Path)
    mode.add_argument("--verify",type=Path)
    p.add_argument("--host-dir",type=Path)
    args=p.parse_args()
    if args.output:
        if not args.host_dir:
            p.error("--host-dir is required for assembly")
        build(args.output,args.host_dir)
    else:
        verify(args.verify)


if __name__=="__main__":
    main()
