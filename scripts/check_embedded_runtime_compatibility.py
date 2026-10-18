"""Static embedded Python dependency check; never execute the legacy runtime.

PASS means pinned distribution metadata matches current C11 requirements.
It does not prove Windows DLL loading, PyMuPDF, network or GUI compatibility.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def check(runtime: Path, requirements: Path) -> dict:
    site = runtime / "Lib" / "site-packages"
    if not site.is_dir() or not (runtime / "python.exe").is_file() or not (runtime / "python312.dll").is_file():
        raise ValueError("Windows Python 3.12 embeddable Runtime is incomplete")
    installed = {}
    for metadata in sorted(site.glob("*.dist-info/METADATA")):
        headers = Parser().parsestr(metadata.read_text(encoding="utf-8", errors="replace"), headersonly=True)
        if headers.get("Name") and headers.get("Version"):
            installed[norm(headers["Name"])] = headers["Version"]
    compared = []
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matched = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+*-]+)", line)
        if not matched:
            raise ValueError("requirement is not an exact pin")
        name, version = matched.groups()
        actual = installed.get(norm(name))
        compared.append({"name": name, "required": version,
                         "installed": actual, "status": "PASS" if actual == version else "MISSING_OR_DIFFERENT"})
    return {
        "schema": "srw.embedded-python-compatibility.v1",
        "pinned_dependencies": len(compared),
        "matched": sum(x["status"] == "PASS" for x in compared),
        "status": "PINNED_METADATA_MATCH" if all(x["status"] == "PASS" for x in compared) else "C11_DEPENDENCIES_NOT_READY",
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
