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

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

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

    def test_empty_duplicate_or_malformed_output_is_refused(self):
        refused = (
            "",
            "\n",
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


if __name__ == "__main__":
    unittest.main()
