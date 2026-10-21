#!/usr/bin/env python
"""Static frontend contract check: window-symbol integrity and API path existence.

The HTML/Browser frontend is a set of ES modules communicating through window globals
and inline handlers; a renamed or dropped global breaks the UI only at click time.
This check makes that break class fail the source gate instead:

1. every window.X referenced from JS or inline handlers must be defined by a loaded module;
2. every statically visible /api/v1 fetch path must exist in the reviewed route inventory
   (docs/contracts/api-v1-inventory.txt), after normalizing path parameters.

It is a static guard, not a substitute for real Chromium acceptance.
"""
from __future__ import annotations


import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
INVENTORY = ROOT / "docs" / "contracts" / "api-v1-inventory.txt"

SCRIPT_SRC = re.compile(r'<script[^>]+src="([^"]+)"', re.I)
WINDOW_DEF = re.compile(r"window\.([A-Za-z_$][\w$]*)\s*=")
WINDOW_USE = re.compile(r"window\.([A-Za-z_$][\w$]*)")
INLINE_HANDLER = re.compile(r'\bon[a-z]+\s*=\s*"([^"]*)"')
BARE_CALL = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
TEMPLATE_EXPR = re.compile(r"\$\{[^{}]*\}")
FETCH_PATH = re.compile(r"""['"`](/api/v1/[^'"`$]*)['"`]""")

# Globals an inline handler may legitimately call without a window assignment.
BROWSER_GLOBALS = {
    "location", "history", "open", "console", "event", "confirm", "prompt", "alert",
    "close", "focus", "blur", "print", "scrollTo", "setTimeout", "clearTimeout",
    "fetch", "btoa", "atob", "encodeURIComponent", "decodeURIComponent", "parseInt",
    "parseFloat", "isNaN", "String", "Number", "Boolean", "Array", "Object", "JSON",
    "Date", "Math", "RegExp", "Error", "Promise", "Map", "Set", "URL",
}


def loaded_modules(dist: Path = DIST) -> list[Path]:
    html = (dist / "index.html").read_text(encoding="utf-8")
    modules = []
    for src in SCRIPT_SRC.findall(html):
        name = src.rsplit("/", 1)[-1]
        path = dist / name
        if path.is_file():
            modules.append(path)
    return modules


def collect_definitions(modules: list[Path]) -> set[str]:
    defined: set[str] = set()
    for path in modules:
        defined.update(WINDOW_DEF.findall(path.read_text(encoding="utf-8")))
    return defined


def collect_references(modules: list[Path]) -> set[str]:
    used: set[str] = set()
    for path in modules:
        text = path.read_text(encoding="utf-8")
        used.update(WINDOW_USE.findall(text))
        for handler in INLINE_HANDLER.findall(text):
            # Template expressions are evaluated at render time in module scope;
            # only the remaining bare calls run when the handler fires (global scope).
            runtime_handler = TEMPLATE_EXPR.sub("''", handler)
            used.update(BARE_CALL.findall(runtime_handler))
    return used


def collect_api_paths(modules: list[Path]) -> set[str]:
    paths: set[str] = set()
    for path in modules:
        text = path.read_text(encoding="utf-8")
        for raw in FETCH_PATH.findall(text):
            # Normalize template parameters and trailing slashes for comparison.
            normalized = re.sub(r"\$\{[^}]*\}", "{}", raw).rstrip("/")
            paths.add(normalized)
    return paths


def load_inventory_paths(inventory: Path = INVENTORY) -> set[str]:
    paths: set[str] = set()
    for line in inventory.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        _, _, path = line.partition(" ")
        normalized = re.sub(r"\{[^}]*\}", "{}", path).rstrip("/")
        paths.add(normalized)
    return paths


def main(dist: Path | None = None, inventory: Path | None = None) -> int:
    """Run the check; returns 0 (pass), 1 (drift) or 2 (no modules found)."""
    dist = dist or DIST
    inventory = inventory or INVENTORY

    modules = loaded_modules(dist)
    if not modules:
        print("frontend contract check: no modules loaded from index.html")
        return 2

    problems: list[str] = []

    defined = collect_definitions(modules)
    used = collect_references(modules)
    for symbol in sorted(used - defined):
        if symbol in BROWSER_GLOBALS:
            continue
        problems.append(f"window symbol referenced but not defined: {symbol}")

    inventory_paths = load_inventory_paths(inventory)
    for path in sorted(collect_api_paths(modules)):
        if path not in inventory_paths:
            problems.append(f"frontend calls an unregistered API path: {path}")

    if problems:
        print("frontend contract DRIFT detected:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"frontend contract PASS: {len(modules)} modules, "
        f"{len(used)} window symbols resolved, {len(collect_api_paths(modules))} API paths registered"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
