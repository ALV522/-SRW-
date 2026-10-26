"""Offline mocked REST/GraphQL source for bounded exact-HEAD PR snapshots."""
from __future__ import annotations

import copy
import json
import unittest

from scripts.collect_pr_readiness_snapshot import GitHubReader, collect, _verdict
from scripts.check_pr_merge_readiness import REQUIRED, assess

HEAD = "a" * 40
MAIN = "b" * 40


class FakeGitHub:
    def __init__(self):
        self.main_reads = 0
        self.pr_reads = 0
        self.next_main = None
        self.next_head = None
        self.thread_nodes = [{"isResolved": True}]
        self.graphql_errors = None
        self.incomplete_checks = False
        self.review_body = "Verdict: ACCEPT"

    def request(self, path, body=None):
        if path.endswith("/branches/main"):
            self.main_reads += 1
            value = self.next_main if self.main_reads == 2 and self.next_main else MAIN
            return {"commit": {"sha": value}}
        if path.endswith("/pulls/135"):
            self.pr_reads += 1
            head = self.next_head if self.pr_reads == 2 and self.next_head else HEAD
            return {
                "head": {"sha": head},
                "base": {"sha": MAIN, "ref": "main"},
                "draft": False, "user": {"login": "shared-user"},
            }
        if "/check-runs?" in path:
            checks = [
                {"name": name, "head_sha": HEAD,
                 "status": "completed", "conclusion": "success"}
                for name in REQUIRED
            ]
            return {"total_count": len(checks) + int(self.incomplete_checks),
                    "check_runs": checks}
        if "/reviews?" in path:
            return [{
                "state": "COMMENTED", "commit_id": HEAD,
                "body": self.review_body, "user": {"login": "shared-user"},
            }]
        if path == "/graphql":
            if self.graphql_errors:
                return {"errors": [{"message": "synthetic denied"}]}
            return {"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": copy.deepcopy(self.thread_nodes),
                                  "pageInfo": {"hasNextPage": False, "endCursor": None}},
            }}}}
        raise AssertionError("unexpected synthetic endpoint " + path)


class ReadonlyGitHubSnapshotTests(unittest.TestCase):
    def test_complete_consistent_snapshot_is_not_merge_authorization(self):
        client = FakeGitHub()
        snap = collect(client, "ALV522/-SRW-", 135)
        self.assertEqual(client.main_reads, 2)
        self.assertEqual(client.pr_reads, 2)
        self.assertEqual(snap["main_sha"], MAIN)
        self.assertEqual(snap["pr"]["head_sha"], HEAD)
        self.assertIsNone(snap["preflight"])
        self.assertEqual(snap["unresolved_review_threads"], 0)
        self.assertEqual(assess(snap)["checks"], "GREEN_FOR_LISTED_CHECKS_ONLY")
        self.assertFalse(assess(snap)["merge_authorized"])
        self.assertNotIn("Verdict: ACCEPT", json.dumps(snap))

    def test_detects_main_head_race(self):
        client = FakeGitHub()
        client.next_main = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "moved"):
            collect(client, "ALV522/-SRW-", 135)

    def test_detects_pr_head_race(self):
        client = FakeGitHub()
        client.next_head = "d" * 40
        with self.assertRaisesRegex(RuntimeError, "moved"):
            collect(client, "ALV522/-SRW-", 135)

    def test_resolved_and_unresolved_review_threads_are_distinguished(self):
        client = FakeGitHub()
        client.thread_nodes.append({"isResolved": False})
        snap = collect(client, "ALV522/-SRW-", 135)
        self.assertEqual(snap["unresolved_review_threads"], 1)
        self.assertEqual(assess(snap)["advisory"], "BLOCKED")

    def test_rest_paginated_check_run_truncation_fails_closed(self):
        client = FakeGitHub()
        client.incomplete_checks = True
        with self.assertRaisesRegex(RuntimeError, "incomplete check-run pagination"):
            collect(client, "ALV522/-SRW-", 135)

    def test_graphql_denial_is_not_treated_as_zero_threads(self):
        client = FakeGitHub()
        client.graphql_errors = True
        with self.assertRaisesRegex(RuntimeError, "cannot verify"):
            collect(client, "ALV522/-SRW-", 135)

    def test_review_verdict_must_be_explicit_not_negated_prose(self):
        self.assertEqual(_verdict({"state": "COMMENTED", "body": "I do NOT ACCEPT this"}), "UNKNOWN")
        self.assertEqual(_verdict({"state": "COMMENTED", "body": "Verdict: NEEDS_CHANGES"}), "NEEDS_CHANGES")
        self.assertEqual(_verdict({"state": "CHANGES_REQUESTED", "body": "Verdict: ACCEPT"}), "BLOCK")
        self.assertEqual(_verdict({"state": "APPROVED", "body": ""}), "ACCEPT")

    def test_invalid_repo_pr_and_missing_token_fail(self):
        with self.assertRaises(ValueError):
            collect(FakeGitHub(), "../escape", 135)
        with self.assertRaises(ValueError):
            collect(FakeGitHub(), "ALV522/-SRW-", 0)
        with self.assertRaises(ValueError):
            GitHubReader("")


if __name__ == "__main__":
    unittest.main()
