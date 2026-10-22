#!/usr/bin/env python
"""Verify the /api/v1 HTTP route inventory against the reviewed baseline (G1 contract).

The baseline docs/contracts/api-v1-inventory.txt is the reviewed product contract
surface: any added, removed or re-method route fails this check until the baseline is
updated deliberately in the same change. The check never touches a user workspace --
the app is built against temporary directories only (charter A8).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "contracts" / "api-v1-inventory.txt"
FRONTEND_DIST = ROOT / "frontend" / "dist"

BASELINE_HEADER = (
    "# SRW /api/v1 route inventory baseline (G1 product contract)\n"
    "# Regenerate only with reviewed route changes:\n"
    "#   python scripts/check_api_contract.py --write\n"
)


def collect_inventory() -> list[str]:
    """Build the v1 app in isolation and return sorted 'METHOD /path' lines."""
    sys.path.insert(0, str(ROOT / "backend"))
    from srw.api.app import create_v1_app
    from srw.supervisor.service import SupervisorService

    with tempfile.TemporaryDirectory(prefix="srw-api-contract-") as tmp:
        root = Path(tmp)
        # In-memory SQLite: route registration never queries, and no file handle
        # can block temp-dir cleanup on Windows.
        # The Supervisor attach routes are part of the reviewed surface (they are
        # registered whenever this process is the Supervisor), so the inventory
        # is collected with a supervisor service attached.
        app = create_v1_app(
            "sqlite+pysqlite:///:memory:",
            data_dir=root / "data",
            knowledge_dir=root / "knowledge" / "active",
            frontend_dist=FRONTEND_DIST,
            supervisor_service=SupervisorService(idle_grace_seconds=300.0),
        )
        lines: list[str] = []
        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if not path or not methods:
                continue
            for method in sorted(methods):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                lines.append(f"{method} {path}")
        return sorted(lines)


def load_baseline(path: Path = BASELINE) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"baseline missing: {path} (generate with --write)")
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def render(inventory: list[str]) -> str:
    return BASELINE_HEADER + "\n".join(inventory) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the baseline")
    parser.add_argument("--print", action="store_true", help="print the current inventory")
    parser.add_argument("--baseline", type=Path, default=BASELINE, help="baseline file to compare against")
    args = parser.parse_args(argv)

    inventory = collect_inventory()

    if args.print:
        sys.stdout.write(render(inventory))
        return 0
    if args.write:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(render(inventory), encoding="utf-8")
        print(f"wrote {args.baseline} with {len(inventory)} routes")
        return 0

    baseline = load_baseline(args.baseline)
    if inventory == baseline:
        print(f"API route inventory matches baseline: {len(inventory)} routes PASS")
        return 0

    expected = set(baseline)
    actual = set(inventory)
    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    print("API route inventory DRIFT detected (update the baseline deliberately in the same change):")
    for line in added:
        print(f"  + {line}")
    for line in removed:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
