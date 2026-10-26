"""Synthetic fail-closed matrix for advisory PR readiness (#135)."""
from __future__ import annotations

import copy
import unittest

from scripts.check_pr_merge_readiness import REQUIRED, assess

HEAD = "a" * 40
MAIN = "b" * 40


def sample():
    return {
        "pr": {
            "head_sha": HEAD, "base_sha": MAIN, "base_ref": "main",
            "draft": False, "author_account": "same-github-login",
        },
        "main_sha": MAIN,
        "checks": [
            {"name": name, "head_sha": HEAD, "status": "completed", "conclusion": "success"}
            for name in REQUIRED
        ],
        "reviews": [{"head_sha": HEAD, "verdict": "ACCEPT",
                     "reviewer_account": "same-github-login"}],
        "unresolved_review_threads": 0,
        "preflight": {"passed": True, "evidence": "claimed-output"},
    }


class MergeReadinessTests(unittest.TestCase):
    def test_all_green_is_never_permission_to_merge(self):
        got = assess(sample())
        self.assertEqual(got["checks"], "GREEN_FOR_LISTED_CHECKS_ONLY")
        self.assertEqual(got["advisory"], "CI_READY_HUMAN_GATES_REQUIRED")
        self.assertFalse(got["merge_authorized"])
        self.assertTrue(any("same-account" in s for s in got["manual_requirements"]))
        self.assertTrue(any("pre-edit timing" in s for s in got["manual_requirements"]))

    def test_windows_source_failure_blocks(self):
        s = sample()
        s["checks"][1]["conclusion"] = "failure"
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_missing_required_check_blocks(self):
        s = sample()
        s["checks"].pop()
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_old_head_checks_never_apply_to_rebased_pr(self):
        s = sample()
        s["pr"]["head_sha"] = "c" * 40
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_drifting_main_blocks_even_if_check_runs_green(self):
        s = sample()
        s["main_sha"] = "c" * 40
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_missing_review_or_preflight_does_not_look_like_verified(self):
        s = sample()
        s["reviews"] = []
        s["preflight"] = None
        got = assess(s)
        self.assertFalse(got["merge_authorized"])
        self.assertTrue(any("no verdict" in m for m in got["manual_requirements"]))
        self.assertTrue(any("not supplied" in m for m in got["manual_requirements"]))

    def test_stale_or_blocking_reviews_never_gain_approval(self):
        s = sample()
        s["reviews"][0]["head_sha"] = "c" * 40
        self.assertTrue(any("no verdict" in m for m in assess(s)["manual_requirements"]))
        s["reviews"][0] = {"head_sha": HEAD, "verdict": "BLOCK"}
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_unresolved_threads_and_unknown_are_blocking(self):
        s = sample()
        s["unresolved_review_threads"] = 1
        self.assertEqual(assess(s)["advisory"], "BLOCKED")
        s["unresolved_review_threads"] = None
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_other_failed_checks_cannot_be_ignored(self):
        s = sample()
        s["checks"].append({"name": "source-integrity", "head_sha": HEAD,
                            "status": "completed", "conclusion": "failure"})
        self.assertEqual(assess(s)["advisory"], "BLOCKED")

    def test_skipped_pr_only_main_audit_is_not_failure(self):
        s = sample()
        s["checks"].append({"name": "audit-main-commit-associated-with-PR",
                            "head_sha": HEAD, "status": "completed", "conclusion": "skipped"})
        self.assertEqual(assess(s)["checks"], "GREEN_FOR_LISTED_CHECKS_ONLY")


if __name__ == "__main__":
    unittest.main()
