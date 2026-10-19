"""Synthetic-only tests for SRW unprotected-main agent preflight policy."""
from __future__ import annotations

import unittest
from scripts.agent_preflight import check_worktree


class AgentPreflightPolicyTests(unittest.TestCase):
    SHA = "a" * 40
    MAIN_SHA = "b" * 40

    def args(self, **overrides):
        data = {
            "branch": "fix/task-41",
            "git_status": "",
            "issue": "41",
            "acknowledged": True,
            "main_sha": self.MAIN_SHA,
            "head_sha": self.SHA,
        }
        data.update(overrides)
        return data

    def test_clean_task_branch_with_issue_and_acknowledgement(self):
        self.assertEqual(check_worktree(**self.args()), [])

    def test_rejects_main_and_detached(self):
        for branch in ("main", "master", "HEAD", ""):
            with self.subTest(branch=branch):
                self.assertTrue(any("never edit" in x for x in check_worktree(**self.args(branch=branch))))

    def test_rejects_dirty_tree(self):
        problems = check_worktree(**self.args(git_status=" M AGENTS.md"))
        self.assertTrue(any("not clean" in x for x in problems))

    def test_rejects_unread_or_missing_issue(self):
        self.assertTrue(check_worktree(**self.args(acknowledged=False)))
        self.assertTrue(check_worktree(**self.args(issue="not-an-issue")))

    def test_rejects_unverifiable_sha(self):
        self.assertTrue(check_worktree(**self.args(main_sha="unknown")))
        self.assertTrue(check_worktree(**self.args(head_sha="abc")))


if __name__ == "__main__":
    unittest.main()
