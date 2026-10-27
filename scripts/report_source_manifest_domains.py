"""Read-only pilot: partition the authoritative Source Manifest without changing it.

All domain manifests are *derived in memory*. Nothing is a second source of
truth, and this tool cannot rehash a tampered tracked file into compliance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts.check_source_integrity import read_manifest, validate

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PREFIXES = {
    "backend": ("backend/",),
    "frontend": ("frontend/",),
    "desktop": ("desktop/",),
    "tests": ("convergence_tests/", "browser_acceptance/"),
    "docs": ("docs/",),
    "automation": ("scripts/", ".github/", ".cursor/", "build-lock/", "verification/"),
}


def domain_for(path: str) -> str:
    for name, prefixes in DOMAIN_PREFIXES.items():
        if path.startswith(prefixes):
            return name
    return "root-other"


def render_partition(entries: dict[str, str], original: bytes) -> dict:
    """Prove disjoint/complete mapping and exact-byte equivalence, then summarize."""
    shards: dict[str, dict[str, str]] = {name: {} for name in (*DOMAIN_PREFIXES, "root-other")}
    for path, digest in entries.items():
        shards[domain_for(path)][path] = digest
    observed = [p for entries in shards.values() for p in entries]
    if len(observed) != len(set(observed)) or set(observed) != set(entries):
        raise ValueError("partition has missing or duplicate tracked entries")

    # The old authority dictates canonical global order; a partition cannot
    # silently rearrange entries, normalize unsafe paths or bless fresh bytes.
    canonical = "".join(f"{entries[path]}  {path}\n" for path in sorted(entries)).encode("utf-8")
    if canonical != original:
        raise ValueError("root manifest bytes are not canonical; refuse pilot")
    domains = {}
    for name, values in shards.items():
        fragment = "".join(f"{values[path]}  {path}\n" for path in sorted(values)).encode("utf-8")
        domains[name] = {
            "count": len(values),
            "sha256": hashlib.sha256(fragment).hexdigest(),
            "paths": sorted(values),
        }
    return {
        "schema": "srw.source-manifest-domain-pilot.v1",
        "authority": "SOURCE_MANIFEST.sha256",
        "authority_sha256": hashlib.sha256(original).hexdigest(),
        "entries": len(entries),
        "coverage": "EXACT_UNION_NO_OVERLAP",
        "mode": "READ_ONLY_NOT_AUTHORITATIVE",
        "domains": domains,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", action="store_true", help="emit a compact CI job summary")
    args = parser.parse_args()
    import subprocess as _subprocess
    try:
        raw = (ROOT / "SOURCE_MANIFEST.sha256").read_bytes()
        manifest = read_manifest(ROOT / "SOURCE_MANIFEST.sha256")
        tracked = set(_subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                      capture_output=True, check=True).stdout.decode("utf-8").strip("\0").split("\0"))
        errors = validate(ROOT, tracked)
        if errors:
            raise ValueError("source integrity failed: " + "; ".join(errors[:5]))
        report = render_partition(manifest, raw)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"DOMAIN PILOT BLOCKED: {exc}")
        return 1
    if args.markdown:
        print(f"### Source-manifest domain pilot (read-only)\n\nAuthority: `SOURCE_MANIFEST.sha256` "
              f"(`{report['authority_sha256']}`), **{report['entries']}** entries. "
              "All tracked bytes passed the existing integrity gate.\n")
        print("| Derived partition | Count | SHA-256 |\n|---|---:|---|")
        for name, d in report["domains"].items():
            print(f"| {name} | {d['count']} | `{d['sha256']}` |")
        print("\n**Exact union, no overlap:** PASS. "
              "No authoritative manifest was changed or auto-repaired.")
    else:
        print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
