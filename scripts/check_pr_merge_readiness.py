"""Fail-closed, read-only PR readiness reporter (#135).

Consumes an externally collected GitHub *snapshot*. It neither writes repo
files nor triggers merges. Even perfect checks cannot establish that agent
preflight was run before edits, that a real independent person reviewed code,
or that target-machine Native acceptance occurred.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = (
    "source-gate (ubuntu-latest, py3.12)",
    "source-gate (windows-latest, py3.12)",
    "governance-contract",
    "chromium-real-browser-ubuntu",
)
SHA = re.compile(r"[a-f0-9]{40}\Z")
NON_BLOCKING_PR_CHECKS = {"audit-main-commit-associated-with-PR"}


def assess(snapshot: dict) -> dict:
    """Report machine evidence separately from unverifiable manual gates."""
    failures: list[str] = []
    manual: list[str] = []
    pr = snapshot.get("pr") or {}
    sha = pr.get("head_sha", "")
    main = snapshot.get("main_sha", "")
    base = pr.get("base_sha", "")
    if not all(isinstance(x, str) and SHA.fullmatch(x) for x in (sha, main, base)):
        failures.append("missing or invalid exact main/base/head SHA")
    if pr.get("base_ref") != "main":
        failures.append("target branch is not main")
    if pr.get("draft") is not False:
        failures.append("PR is draft or draft state is unknown")
    if base != main:
        failures.append("PR base differs from latest main; require re-integration")

    checks = snapshot.get("checks")
    if not isinstance(checks, list):
        checks = []
        failures.append("check-run evidence is missing")
    by_name: dict[str, list[dict]] = {}
    for c in checks:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str):
            failures.append("malformed check-run record")
            continue
        by_name.setdefault(c["name"], []).append(c)
    for name in REQUIRED:
        entries = by_name.get(name, [])
        if len(entries) != 1:
            failures.append(f"{name}: require exactly one attached check-run")
            continue
        c = entries[0]
        if c.get("head_sha") != sha:
            failures.append(f"{name}: check-run HEAD differs from PR HEAD")
        if c.get("status") != "completed" or c.get("conclusion") != "success":
            failures.append(f"{name}: not completed SUCCESS")
    for name, entries in by_name.items():
        if name in REQUIRED or name in NON_BLOCKING_PR_CHECKS:
            continue
        for c in entries:
            if c.get("head_sha") != sha:
                failures.append(f"{name}: other applicable check HEAD drift")
            elif c.get("status") != "completed" or c.get("conclusion") not in {"success", "skipped"}:
                failures.append(f"{name}: extra check not successful")
    unresolved = snapshot.get("unresolved_review_threads")
    if unresolved is None or not isinstance(unresolved, int) or unresolved < 0:
        failures.append("unresolved review thread count unverified")
    elif unresolved:
        failures.append(f"{unresolved} unresolved review threads")

    reviews = snapshot.get("reviews")
    fresh_reviews: list[dict] = []
    if not isinstance(reviews, list):
        manual.append("independent review record unavailable")
    else:
        for review in reviews:
            if not isinstance(review, dict) or review.get("head_sha") != sha:
                continue
            if review.get("verdict") in {"ACCEPT", "NEEDS_CHANGES", "BLOCK"}:
                fresh_reviews.append(review)
        if not fresh_reviews:
            manual.append("no verdict linked to exact PR HEAD")
        if any(r["verdict"] != "ACCEPT" for r in fresh_reviews):
            failures.append("latest-head review contains NEEDS_CHANGES/BLOCK")
        if fresh_reviews and all(r.get("reviewer_account") == pr.get("author_account") for r in fresh_reviews):
            manual.append("same-account reviews provide process separation only, not independent GitHub identity")
    preflight = snapshot.get("preflight")
    if not isinstance(preflight, dict) or preflight.get("passed") is not True:
        manual.append("pre-edit clean-worktree preflight PASS not supplied")
    else:
        manual.append("preflight attestation supplied; pre-edit timing and clean worktree cannot be machine-proven")
    manual.extend((
        "human inspect exact diff / source-manifest mutation and required release gates",
        "Windows Native/real GUI and other physical evidence are separate, not inferred from PR checks",
        "no server-side branch protection evidenced by this advisory snapshot",
    ))
    return {
        "head_sha": sha,
        "main_sha": main,
        "checks": "BLOCKED" if failures else "GREEN_FOR_LISTED_CHECKS_ONLY",
        "advisory": "BLOCKED" if failures else "CI_READY_HUMAN_GATES_REQUIRED",
        "merge_authorized": False,
        "blockers": sorted(set(failures)),
        "manual_requirements": sorted(set(manual)),
        "checked_names": list(REQUIRED),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path,
                        help="JSON exported from exact GitHub PR and check-runs; read-only")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be object")
        result = assess(snapshot)
    except (OSError, ValueError) as exc:
        print(json.dumps({"advisory": "BLOCKED", "merge_authorized": False,
                          "blockers": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
