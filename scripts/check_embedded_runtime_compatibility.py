"""Statically check the effective pinned dependencies of an embedded Python.

The optional Lib/c11-overlay is accepted only when python312._pth lists it
before Lib/site-packages. Metadata checks are not executable smoke tests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = "Lib/c11-overlay"
LEGACY = "Lib/site-packages"


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def _effective_sites(runtime: Path) -> tuple[list[Path], bool]:
    legacy = runtime / "Lib" / "site-packages"
    pth = runtime / "python312._pth"
    overlay = runtime / "Lib" / "c11-overlay"
    if not overlay.exists():
        return [legacy], False
    if not overlay.is_dir() or not pth.is_file() or pth.is_symlink():
        raise ValueError("C11 overlay exists but embedded Python path is unconfigured")
    lines = [x.strip().replace("\\", "/").casefold()
             for x in pth.read_text(encoding="utf-8-sig").splitlines()
             if x.strip() and not x.lstrip().startswith("#")]
    if lines.count(OVERLAY.casefold()) != 1 or LEGACY.casefold() not in lines:
        raise ValueError("embedded Python path must include one C11 overlay and legacy site-packages")
    if lines.index(OVERLAY.casefold()) > lines.index(LEGACY.casefold()):
        raise ValueError("C11 overlay must have precedence over legacy packages")
    return [overlay, legacy], True


def check(runtime: Path, requirements: Path) -> dict:
    sites, overlay_active = _effective_sites(runtime)
    if (not sites[-1].is_dir() or not (runtime / "python.exe").is_file()
        or not (runtime / "python312.dll").is_file()):
        raise ValueError("Windows Python 3.12 embeddable Runtime is incomplete")
    installed: dict[str, tuple[str, str]] = {}
    for site in sites:
        for metadata in sorted(site.glob("*.dist-info/METADATA")):
            headers = Parser().parsestr(
                metadata.read_text(encoding="utf-8", errors="replace"),
                headersonly=True,
            )
            if headers.get("Name") and headers.get("Version"):
                key = norm(headers["Name"])
                if key not in installed:
                    installed[key] = (headers["Version"], "c11-overlay" if site == sites[0] and overlay_active else "legacy")
    compared = []
    observed = set()
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+*-]+)", line)
        if not match:
            raise ValueError("requirement is not an exact pin")
        name, required = match.groups()
        key = norm(name)
        if key in observed:
            raise ValueError("duplicate pinned dependency")
        observed.add(key)
        version, origin = installed.get(key, (None, None))
        compared.append({
            "name": name, "required": required, "installed": version,
            "origin": origin,
            "status": "PASS" if version == required else "MISSING_OR_DIFFERENT",
        })
    return {
        "schema": "srw.embedded-python-compatibility.v2",
        "pinned_dependencies": len(compared),
        "matched": sum(x["status"] == "PASS" for x in compared),
        "status": "PINNED_METADATA_MATCH" if all(x["status"] == "PASS" for x in compared) else "C11_DEPENDENCIES_NOT_READY",
        "c11_overlay_on_path": overlay_active,
        "windows_runtime_executed": False,
        "c11_runtime_smoke_passed": False,
        "dependencies": compared,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--requirements", type=Path, default=ROOT / "requirements-ci.txt")
    args = p.parse_args()
    try:
        result = check(args.runtime, args.requirements)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PINNED_METADATA_MATCH" else 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
