"""Report committed source-manifest changes without writing or approving any hash.

This is a reviewer aid, NOT an integrity test and NOT a manifest auto-updater.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.check_source_integrity import read_manifest

MANIFEST = "SOURCE_MANIFEST.sha256"


def parse_manifest_text(text: str) -> dict[str, str]:
    # Share strict duplicate/path validation with the authoritative source gate.
    with tempfile.TemporaryDirectory(prefix="srw-source-diff-") as root:
        path = Path(root) / MANIFEST
        path.write_text(text, encoding="utf-8")
        return read_manifest(path)


def manifest_changes(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    old, new = set(before), set(after)
    return {
        "added": sorted(new - old),
        "deleted": sorted(old - new),
        "changed": sorted(p for p in old & new if before[p] != after[p]),
    }


def domain_counts(changes: dict[str, list[str]]) -> dict[str, int]:
    # No hard-coded four-domain list: even a new top-level directory is covered.
    counts: Counter[str] = Counter()
    for paths in changes.values():
        for path in paths:
            counts[path.split("/", 1)[0] if "/" in path else "(root)"] += 1
    return dict(sorted(counts.items()))


def render_changes(changes: dict[str, list[str]]) -> str:
    lines = ["ADVISORY MANIFEST DELTA -- NOT SOURCE INTEGRITY PASS"]
    for kind in ("added", "deleted", "changed"):
        lines.append(f"{kind.upper()}: {len(changes[kind])}")
        lines.extend("  " + path for path in changes[kind])
    domains = domain_counts(changes)
    lines.append("AFFECTED TOP-LEVEL DOMAINS: " + (
        ", ".join(f"{name}={count}" for name, count in domains.items()) or "(none)"
    ))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True,
                        help="Fetched local branch or exact SHA, e.g. main")
    args = parser.parse_args()
    try:
        base_sha = subprocess.run(
            ["git", "rev-parse", "--verify", args.base_ref + "^{commit}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        original = subprocess.run(
            ["git", "show", f"{base_sha}:{MANIFEST}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        current = (ROOT / MANIFEST).read_text(encoding="utf-8")
        diff = manifest_changes(parse_manifest_text(original), parse_manifest_text(current))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"MANIFEST DELTA UNAVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(f"base-ref={args.base_ref} resolved={base_sha}")
    print(render_changes(diff))
    print("Review actual code diff and run check_source_integrity.py separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
