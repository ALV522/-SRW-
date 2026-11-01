"""#174: the pre-edit gate must verify the *remote* main identity, not a local ref.

The defect this replaces: a clean task branch cut from a stale local `main` passed
the old gate, because the gate compared HEAD against `refs/heads/main` and only asked
for *some* common ancestor. On this workstation that happened for real
(`origin/main = d2f7fd8e` while GitHub main was `a6cc26b3`).

The oracles below are pure-function tests: no Git, no network, no private paths. The
rule they pin is fail-closed - every doubt (missing origin, lookalike host,
credential in the URL, an `insteadOf` rewrite, an unreadable remote, a duplicated or
malformed ref, a stale local main, a branch that does not contain the tip) produces a
blocking problem, never a warning that still lets the edit through.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from scripts import agent_preflight as gate  # noqa: E402
from scripts.agent_preflight import (  # noqa: E402
    canonical_remote,
    check_remote,
    parse_remote_main,
)

MAIN = "17c59e3efd1fff71132dfcc9230a326abc6a99ac"
OLD = "a6cc26b373abf7c2a4859346b8f4eb7b46692fcb"
CANONICAL = "https://github.com/ALV522/-SRW-.git"
LS_OK = f"{MAIN}\trefs/heads/main\n"


def _check(**overrides):
    defaults = dict(
        raw_urls=[CANONICAL],
        effective_urls=[CANONICAL],
        rewrite_configured=False,
        ls_remote_returncode=0,
        ls_remote_stdout=LS_OK,
        local_main_sha=MAIN,
        main_is_ancestor=True,
    )
    defaults.update(overrides)
    return check_remote(**defaults)


class CanonicalRemoteTests(unittest.TestCase):
    def test_the_audited_github_forms_are_accepted(self):
        for url in (CANONICAL,
                    "git@github.com:ALV522/-SRW-.git",
                    "ssh://git@github.com/ALV522/-SRW-.git"):
            with self.subTest(url=url):
                self.assertIsNotNone(canonical_remote(url))

    def test_lookalike_hosts_schemes_and_credentials_are_rejected(self):
        rejected = (
            "http://github.com/ALV522/-SRW-.git",
            "git://github.com/ALV522/-SRW-.git",
            "file:///C:/src/-SRW-",
            "/mnt/c/src/-SRW-",
            "https://github.com/ALV522/-SRW-",
            "https://github.com/ALV522/-SRW-.git/",
            "https://github.com.evil.example/ALV522/-SRW-.git",
            "https://evilgithub.com/ALV522/-SRW-.git",
            "https://github.com@evil.example/ALV522/-SRW-.git",
            "https://token@github.com/ALV522/-SRW-.git",
            "https://user:pass@github.com/ALV522/-SRW-.git",
            "git@github.com:someone-else/-SRW-.git",
            "ssh://root@github.com/ALV522/-SRW-.git",
            "git@github.com:ALV522/-SRW-",
            "",
        )
        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(canonical_remote(url))
        self.assertIsNone(canonical_remote(None))

    def test_a_credentialed_url_is_never_echoed_back(self):
        secret = "ghp_EXAMPLESECRETVALUE"
        problems = _check(raw_urls=[f"https://{secret}@github.com/ALV522/-SRW-.git"])
        self.assertTrue(problems)
        self.assertFalse(any(secret in problem for problem in problems),
                         "the gate must not copy the remote URL into its output")


class LsRemoteParsingTests(unittest.TestCase):
    def test_exactly_one_well_formed_ref_is_required(self):
        self.assertEqual(parse_remote_main(LS_OK), MAIN)
        self.assertEqual(parse_remote_main(f"{MAIN}\trefs/heads/main\r\n"), MAIN)
        self.assertEqual(parse_remote_main(f"{MAIN}\trefs/heads/main"), MAIN)

    def test_empty_duplicate_or_malformed_output_is_refused(self):
        refused = (
            "",
            "\n",
            "\n\n",
            LS_OK + "\n",
            LS_OK + LS_OK,
            f"{OLD}\trefs/heads/main\n{MAIN}\trefs/heads/main\n",
            f"{MAIN}\trefs/heads/mainx\n",
            f"{MAIN[:39]}\trefs/heads/main\n",
            f"{MAIN.upper()}\trefs/heads/main\n",
            f"{MAIN}\trefs/heads/main\textra\n",
            f"not-a-sha\trefs/heads/main\n",
        )
        for output in refused:
            with self.subTest(output=output):
                self.assertIsNone(parse_remote_main(output))

    def test_a_space_separator_is_not_a_tab_separator(self):
        # `git ls-remote` separates the SHA from the ref with a TAB. Accepting a
        # space here would also accept hand-written or rewritten output.
        for output in (f"{MAIN} refs/heads/main\n",
                       f"{MAIN}  refs/heads/main\n",
                       f"{MAIN}\t refs/heads/main\n",
                       f" {MAIN}\trefs/heads/main\n",
                       f"{MAIN}\trefs/heads/main \n"):
            with self.subTest(output=output):
                self.assertIsNone(parse_remote_main(output))


class RemoteIdentityGateTests(unittest.TestCase):
    def test_matching_remote_and_local_main_passes(self):
        self.assertEqual(_check(), [])

    def test_stale_local_main_is_blocked(self):
        problems = _check(local_main_sha=OLD)
        self.assertTrue(any("stale" in p for p in problems), problems)

    def test_unreadable_remote_is_blocked_not_warned(self):
        for code in (1, 2, 128, 255):
            with self.subTest(returncode=code):
                problems = _check(ls_remote_returncode=code, ls_remote_stdout="")
                self.assertTrue(any("unreadable" in p for p in problems), problems)

    def test_duplicate_or_missing_ref_is_blocked(self):
        for output in ("", LS_OK + LS_OK, f"{MAIN}\trefs/heads/mainx\n"):
            with self.subTest(output=output):
                problems = _check(ls_remote_stdout=output)
                self.assertTrue(any("missing, duplicated, or malformed" in p for p in problems),
                                problems)

    def test_branch_that_does_not_contain_the_main_tip_is_blocked(self):
        problems = _check(main_is_ancestor=False)
        self.assertTrue(any("does not contain the current main tip" in p for p in problems),
                        problems)

    def test_absent_or_duplicated_origin_is_blocked(self):
        self.assertTrue(_check(raw_urls=[]))
        self.assertTrue(_check(raw_urls=[CANONICAL, CANONICAL]))

    def test_wrong_origin_and_rewrites_are_blocked(self):
        self.assertTrue(_check(raw_urls=["https://github.com/other/-SRW-.git"]))
        self.assertTrue(_check(rewrite_configured=True))
        self.assertTrue(_check(effective_urls=["https://evil.example/-SRW-.git"]))
        self.assertTrue(_check(effective_urls=[]))

    def test_every_failure_shape_returns_at_least_one_problem(self):
        failures = (
            dict(raw_urls=[]),
            dict(raw_urls=["file:///C:/src/-SRW-"]),
            dict(rewrite_configured=True),
            dict(effective_urls=["git@evil.example:ALV522/-SRW-.git"]),
            dict(ls_remote_returncode=2, ls_remote_stdout=""),
            dict(ls_remote_stdout=""),
            dict(ls_remote_stdout=LS_OK + LS_OK),
            dict(local_main_sha=OLD),
            dict(main_is_ancestor=False),
        )
        for overrides in failures:
            with self.subTest(**{k: str(v)[:40] for k, v in overrides.items()}):
                self.assertTrue(_check(**overrides), overrides)


def _completed(returncode: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode,
                                       stdout=stdout, stderr="")


def _facts(**overrides) -> dict:
    base = {"raw_urls": [CANONICAL], "effective_urls": [CANONICAL],
            "rewrite_configured": False, "ls_remote_returncode": 0,
            "ls_remote_stdout": LS_OK, "main_is_ancestor": True}
    base.update(overrides)
    return base


class GitCommandPathTests(unittest.TestCase):
    """R1: the real subprocess path must be covered by mocks, not only pure functions."""

    def test_git_run_is_non_interactive_and_isolates_credentials(self):
        with mock.patch.object(gate.subprocess, "run") as run:
            run.return_value = _completed(0, "x")
            gate._git_run("ls-remote", "--exit-code", "origin", "refs/heads/main",
                          timeout=gate.REMOTE_TIMEOUT_SECONDS)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["git", "-c", "credential.helper=", "ls-remote",
                                   "--exit-code", "origin", "refs/heads/main"])
        self.assertEqual(kwargs["timeout"], gate.REMOTE_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(kwargs["env"]["GCM_INTERACTIVE"], "never")
        self.assertFalse(kwargs["env"]["GIT_ASKPASS"], "askpass must be neutralised")
        self.assertTrue(kwargs["capture_output"])

    def _facts_with(self, *, urls=(CANONICAL,), effective=(CANONICAL,), rewrites="",
                    ls=(0, LS_OK), ancestor=0, raise_ls=None):
        calls: dict = {}

        def fake_run(*args, timeout=None):
            calls[tuple(args)] = timeout
            if args[:2] == ("config", "--get-all"):
                return _completed(0 if urls else 1, "".join(f"{u}\n" for u in urls))
            if args[:2] == ("remote", "get-url"):
                return _completed(0 if effective else 1, "".join(f"{u}\n" for u in effective))
            if args[:2] == ("config", "--get-regexp"):
                return _completed(0 if rewrites else 1, rewrites)
            if args[0] == "ls-remote":
                if raise_ls is not None:
                    raise raise_ls
                return _completed(*ls)
            if args[0] == "merge-base":
                return _completed(ancestor, "")
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(gate, "_git_run", side_effect=fake_run):
            return gate._remote_facts(), calls

    def test_remote_facts_assembles_the_real_command_results(self):
        facts, calls = self._facts_with()
        self.assertEqual(facts["raw_urls"], [CANONICAL])
        self.assertEqual(facts["effective_urls"], [CANONICAL])
        self.assertFalse(facts["rewrite_configured"])
        self.assertEqual(facts["ls_remote_returncode"], 0)
        self.assertEqual(facts["ls_remote_stdout"], LS_OK)
        self.assertTrue(facts["main_is_ancestor"])
        ls_args = ("ls-remote", "--exit-code", "origin", "refs/heads/main")
        self.assertIn(ls_args, calls)
        self.assertEqual(calls[ls_args], gate.REMOTE_TIMEOUT_SECONDS,
                         "the network read must stay bounded")

    def test_remote_facts_maps_timeout_and_oserror_to_unreadable(self):
        for error in (subprocess.TimeoutExpired(cmd="git", timeout=20), OSError("boom")):
            with self.subTest(error=type(error).__name__):
                facts, _ = self._facts_with(raise_ls=error)
                self.assertEqual(facts["ls_remote_returncode"], 124)
                self.assertEqual(facts["ls_remote_stdout"], "")

    def test_remote_facts_detects_rewrite_and_effective_url_drift(self):
        with self.subTest("insteadOf prefix"):
            facts, _ = self._facts_with(rewrites=f"url.git@evil.example:.insteadof {CANONICAL}\n")
            self.assertTrue(facts["rewrite_configured"])
        with self.subTest("effective url differs"):
            facts, _ = self._facts_with(effective=("git@evil.example:ALV522/-SRW-.git",))
            self.assertTrue(facts["rewrite_configured"])
        with self.subTest("multi-valued remote"):
            facts, _ = self._facts_with(urls=(CANONICAL, CANONICAL))
            self.assertEqual(len(facts["raw_urls"]), 2)

    def test_remote_facts_reads_ancestry_exit_code(self):
        self.assertFalse(self._facts_with(ancestor=1)[0]["main_is_ancestor"])
        self.assertTrue(self._facts_with(ancestor=0)[0]["main_is_ancestor"])


class PreflightMainControlFlowTests(unittest.TestCase):
    """R1: the *control flow* that used to produce a false PASS is regression-pinned."""

    def _run_main(self, facts, *, branch="fix/task", head=MAIN, main=MAIN, status=""):
        def fake_git(*args):
            if args[0] == "symbolic-ref":
                return branch
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return head
            if args[0] == "rev-parse":
                return main
            if args[0] == "status":
                return status
            raise AssertionError(f"unexpected git call: {args}")

        buffer = io.StringIO()
        with mock.patch.object(gate, "_git", side_effect=fake_git), \
                mock.patch.object(gate, "_remote_facts", return_value=facts), \
                mock.patch.object(gate, "governance_validate", return_value=[]), \
                mock.patch.object(gate, "release_validate", return_value=[]), \
                mock.patch.object(gate, "source_validate", return_value=[]), \
                mock.patch.object(sys, "argv", ["agent_preflight.py", "--issue", "174",
                                                "--acknowledge-reading"]), \
                contextlib.redirect_stdout(buffer):
            status_code = gate.main()
        return status_code, buffer.getvalue()

    def test_matching_remote_passes_and_prints_the_evidence(self):
        code, out = self._run_main(_facts())
        self.assertEqual(code, 0, out)
        self.assertIn("PRE-EDIT POLICY PASS", out)
        self.assertIn(f"remote_main={MAIN}", out)

    def test_unreadable_remote_blocks_and_never_prints_a_sha(self):
        code, out = self._run_main(_facts(ls_remote_returncode=1, ls_remote_stdout=""))
        self.assertEqual(code, 2, out)
        self.assertIn("remote main is unreadable", out)
        self.assertIn("remote_main=UNKNOWN", out)

    def test_stale_local_main_blocks(self):
        code, out = self._run_main(_facts(ls_remote_stdout=f"{OLD}\trefs/heads/main\n"))
        self.assertEqual(code, 2, out)
        self.assertIn("stale", out)

    def test_branch_without_the_main_tip_blocks(self):
        code, out = self._run_main(_facts(main_is_ancestor=False))
        self.assertEqual(code, 2, out)
        self.assertIn("does not contain the current main tip", out)

    def test_credential_remote_blocks_without_echoing_the_token(self):
        secret = "ghp_EXAMPLESECRETVALUE"
        code, out = self._run_main(_facts(raw_urls=[f"https://{secret}@github.com/ALV522/-SRW-.git"],
                                          effective_urls=[]))
        self.assertEqual(code, 2, out)
        self.assertNotIn(secret, out, "the gate must not copy the remote URL into its output")

    def test_dirty_tree_still_blocks_even_with_a_good_remote(self):
        code, out = self._run_main(_facts(), status=" M AGENTS.md")
        self.assertEqual(code, 2, out)
        self.assertIn("working tree is not clean", out)


if __name__ == "__main__":
    unittest.main()
