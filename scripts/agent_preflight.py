"""Read-only, fail-closed pre-edit gate for SRW coding agents.

Invoke on a *clean, dedicated task branch*, before changing tracked files:
    python scripts/agent_preflight.py --issue 41 --acknowledge-reading

This script cannot prove a model has read instructions and cannot replace a
protected branch. It prevents accidental edits on main by compliant agents.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from scripts.check_governance_contract import validate as governance_validate
from scripts.check_release_truth import validate as release_validate
from scripts.check_source_integrity import validate as source_validate

ROOT = Path(__file__).resolve().parents[1]
ISSUE_RE = re.compile(r"#[1-9][0-9]*|[1-9][0-9]*")


def check_worktree(*, branch: str, git_status: str, issue: str,
                   acknowledged: bool, main_sha: str, head_sha: str) -> list[str]:
    """Pure policy check, deliberately testable without Git or private data."""
    problems: list[str] = []
    if not acknowledged:
        problems.append("read and acknowledge AGENTS.md onboarding before edits")
    if not ISSUE_RE.fullmatch(issue):
        problems.append("link a specific GitHub issue number")
    if branch in {"", "HEAD", "main", "master"}:
        problems.append("never edit on main/detached HEAD; create a task branch first")
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        problems.append("exact current HEAD SHA is unavailable")
    if not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        problems.append("local main SHA is unavailable: fetch main before editing")
    if git_status.strip():
        problems.append("working tree is not clean; record/review existing changes before editing")
    return problems


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True, help="GitHub issue number, e.g. 41")
    parser.add_argument("--acknowledge-reading", action="store_true",
                        help="Explicit declaration, not machine proof, that all required G1 documents were read")
    args = parser.parse_args()
    problems = []
    try:
        branch = _git("symbolic-ref", "--short", "-q", "HEAD")
        head_sha = _git("rev-parse", "HEAD")
        main_sha = _git("rev-parse", "refs/heads/main")
        dirty = _git("status", "--porcelain")
    except subprocess.CalledProcessError:
        problems.append("Git checkout, local main, or branch identity unavailable")
        branch, head_sha, main_sha, dirty = "", "", "", ""
    problems += check_worktree(
        branch=branch, git_status=dirty, issue=args.issue,
        acknowledged=args.acknowledge_reading, main_sha=main_sha, head_sha=head_sha,
    )
    if head_sha and main_sha:
        try:
            # Current branch may already include task commits, but must share
            # a valid base with the local main tip (not an unrelated history).
            _git("merge-base", "HEAD", "refs/heads/main")
        except subprocess.CalledProcessError:
            problems.append("work branch has no common history with local main")
    problems += governance_validate(ROOT)
    problems += release_validate()
    if (ROOT / "SOURCE_MANIFEST.sha256").exists():
        problems += source_validate(ROOT)
    else:
        problems.append("SOURCE_MANIFEST.sha256 is missing")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "UNKNOWN"
    print("SRW AGENT PREFLIGHT (read-only)")
    print(f"issue=#{args.issue} branch={branch or 'UNKNOWN'}")
    print(f"source_head={head_sha or 'UNKNOWN'} main={main_sha or 'UNKNOWN'} version={version}")
    print("Browser / Windows GUI / Native / dual-carrier acceptance: UNKNOWN until exact evidence is reviewed")
    if problems:
        for problem in problems:
            print(f"BLOCKED: {problem}")
        return 2
    print("PRE-EDIT POLICY PASS: safe to work on dedicated branch; NOT a test or release PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
