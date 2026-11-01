"""Read-only, fail-closed pre-edit gate for SRW coding agents.

Invoke on a *clean, dedicated task branch*, before changing tracked files:
    python scripts/agent_preflight.py --issue 41 --acknowledge-reading

This script cannot prove a model has read instructions and cannot replace a
protected branch. It prevents accidental edits on main by compliant agents.

Since #174 it also verifies the *remote* main identity, because a clean branch cut
from a stale local ``main`` used to pass: the gate compared HEAD with
``refs/heads/main`` locally and only asked for a shared ancestor. The gate now
requires the audited GitHub ``origin``, a single valid ``refs/heads/main`` from a
bounded ``git ls-remote``, that SHA equal to the local ``main``, and a task branch
that actually contains the current main tip. Every doubt blocks; none warns and
passes.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_governance_contract import validate as governance_validate
from scripts.check_release_truth import validate as release_validate
from scripts.check_source_integrity import validate as source_validate

ROOT = Path(__file__).resolve().parents[1]
ISSUE_RE = re.compile(r"#[1-9][0-9]*|[1-9][0-9]*")

#: The audited SRW origins. Exactly these strings, nothing normalised into place:
#: a lookalike host, an ``http``/``file`` URL or a credential-bearing URL must never
#: be treated as the SRW remote.
CANONICAL_REMOTES = {
    "https://github.com/ALV522/-SRW-.git": "https",
    "git@github.com:ALV522/-SRW-.git": "ssh",
    "ssh://git@github.com/ALV522/-SRW-.git": "ssh",
}

#: A bounded, non-interactive network read. A hung remote blocks the gate instead of
#: hanging the agent, and no prompt may ever appear.
REMOTE_TIMEOUT_SECONDS = 20.0
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
           "GIT_ASKPASS": "", "SSH_ASKPASS": ""}


def canonical_remote(url: str | None) -> str | None:
    """Return the audited label of an accepted origin, else None.

    The rejected input is never echoed by callers: a URL can carry a token.
    """
    if not isinstance(url, str):
        return None
    return CANONICAL_REMOTES.get(url.strip())


def parse_remote_main(output: str | None) -> str | None:
    """Return the single main SHA from ``git ls-remote`` output, else None.

    Exactly one ``<sha>\\trefs/heads/main`` line is accepted. Empty output, two lines
    (duplicated or diverging answers), another ref, a truncated/upper-case SHA or
    extra columns are all refused.
    """
    lines = [line for line in (output or "").splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    fields = lines[0].split()
    if len(fields) != 2:
        return None
    sha, ref = fields
    if ref != "refs/heads/main" or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    return sha


def check_remote(*, raw_urls: list[str], effective_urls: list[str],
                 rewrite_configured: bool, ls_remote_returncode: int,
                 ls_remote_stdout: str, local_main_sha: str,
                 main_is_ancestor: bool) -> list[str]:
    """Pure remote-identity policy: return blocking problems, never warnings."""
    if not raw_urls:
        return ["origin remote is not configured; the audited SRW GitHub origin is required"]
    if len(raw_urls) > 1:
        return ["origin has multiple configured URLs; exactly one audited URL is required"]
    if canonical_remote(raw_urls[0]) is None:
        return ["origin is not the audited SRW GitHub remote"]
    if rewrite_configured:
        return ["a Git url.*.insteadOf rewrite changes the effective origin"]
    if len(effective_urls) != 1 or effective_urls[0] != raw_urls[0]:
        return ["origin resolves to a different effective URL than configured"]
    if ls_remote_returncode != 0:
        return ["remote main is unreadable (unreachable, absent, timed out, or denied)"]
    parsed = parse_remote_main(ls_remote_stdout)
    if parsed is None:
        return ["remote refs/heads/main is missing, duplicated, or malformed"]
    if parsed != local_main_sha:
        return ["local main is stale; fetch origin main before editing"]
    if not main_is_ancestor:
        return ["task branch does not contain the current main tip; rebase onto main first"]
    return []


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
        env={**os.environ, **GIT_ENV},
    ).stdout.strip()


def _git_run(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run git without prompting; return the completed process instead of raising."""
    return subprocess.run(
        ["git", "-c", "credential.helper=", *args], cwd=ROOT, text=True,
        capture_output=True, env={**os.environ, **GIT_ENV}, timeout=timeout,
    )


def _remote_facts() -> dict:
    """Collect the raw and effective origin URLs, rewrites, and remote main SHA."""
    facts: dict = {"raw_urls": [], "effective_urls": [], "rewrite_configured": False,
                   "ls_remote_returncode": 1, "ls_remote_stdout": "", "main_is_ancestor": False}
    config = _git_run("config", "--get-all", "remote.origin.url")
    if config.returncode == 0:
        facts["raw_urls"] = [line.strip() for line in config.stdout.splitlines() if line.strip()]

    effective = _git_run("remote", "get-url", "--all", "origin")
    if effective.returncode == 0:
        facts["effective_urls"] = [line.strip() for line in effective.stdout.splitlines()
                                   if line.strip()]

    rewrites = _git_run("config", "--get-regexp", r"^url\..*\.insteadof$")
    if rewrites.returncode == 0:
        for line in rewrites.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            prefix = parts[1].strip()
            if prefix and any(url.startswith(prefix) for url in facts["raw_urls"]):
                facts["rewrite_configured"] = True
    if facts["raw_urls"] and facts["effective_urls"] and \
            facts["raw_urls"] != facts["effective_urls"]:
        facts["rewrite_configured"] = True

    try:
        remote = _git_run("ls-remote", "--exit-code", "origin", "refs/heads/main",
                          timeout=REMOTE_TIMEOUT_SECONDS)
        facts["ls_remote_returncode"] = remote.returncode
        facts["ls_remote_stdout"] = remote.stdout
    except (subprocess.TimeoutExpired, OSError):
        facts["ls_remote_returncode"] = 124
        facts["ls_remote_stdout"] = ""

    try:
        ancestor = _git_run("merge-base", "--is-ancestor", "refs/heads/main", "HEAD")
        facts["main_is_ancestor"] = ancestor.returncode == 0
    except (subprocess.SubprocessError, OSError):
        facts["main_is_ancestor"] = False
    return facts


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
        facts = _remote_facts()
        problems += check_remote(
            raw_urls=facts["raw_urls"], effective_urls=facts["effective_urls"],
            rewrite_configured=facts["rewrite_configured"],
            ls_remote_returncode=facts["ls_remote_returncode"],
            ls_remote_stdout=facts["ls_remote_stdout"],
            local_main_sha=main_sha, main_is_ancestor=facts["main_is_ancestor"],
        )
        remote_main = parse_remote_main(facts["ls_remote_stdout"]) or "UNKNOWN"
    else:
        remote_main = "UNKNOWN"
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
    print(f"remote_main={remote_main} (git ls-remote origin refs/heads/main)")
    print("Browser / Windows GUI / Native / dual-carrier acceptance: UNKNOWN until exact evidence is reviewed")
    if problems:
        for problem in problems:
            print(f"BLOCKED: {problem}")
        return 2
    print("PRE-EDIT POLICY PASS: safe to work on dedicated branch; NOT a test or release PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
