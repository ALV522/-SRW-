"""Native embedded business test report is strict, synthetic and not WPF UI evidence."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import accept_native_business as native
from scripts.native_payload import PayloadError

ROOT = Path(__file__).resolve().parents[1]


class NativeBusinessAcceptanceTests(unittest.TestCase):
    def valid(self, tests=3):
        return native.DRIVER_TAG + json.dumps({
            "tests": tests, "failures": 0, "errors": 0,
            "skipped": 0, "passed": True,
        })

    def test_explicit_suite_pass_keeps_only_safe_aggregate_counters(self):
        data = native.validated_result(self.valid(3), 0, suite="offer_human_transition")
        self.assertEqual(data, {"suite": "offer_human_transition", "status": "PASS", "tests": 3})
        self.assertNotIn("candidate", str(data))

    def test_skip_error_fail_and_nonzero_exit_all_block(self):
        for updates, code in [({"skipped": 1}, 0), ({"errors": 1}, 0),
                              ({"failures": 1}, 0), ({"passed": False}, 0),
                              ({}, 2), ({"tests": 0}, 0), ({"tests": True}, 0)]:
            sample = {"tests": 3, "failures": 0, "errors": 0, "skipped": 0, "passed": True}
            sample.update(updates)
            with self.subTest(sample=sample, code=code), self.assertRaises(PayloadError):
                native.validated_result(native.DRIVER_TAG + json.dumps(sample), code,
                                        suite="candidate_decision")

    def test_duplicate_or_forged_result_cannot_make_a_report_pass(self):
        for out in ["", "broken", self.valid(2) + "\n" + self.valid(3),
                    native.DRIVER_TAG + "INVALID", native.DRIVER_TAG + "[]"]:
            with self.subTest(out=out[:30]), self.assertRaises(PayloadError):
                native.validated_result(out, 0, suite="project_protocol")

    def test_real_local_python_runs_declared_business_core_groups_without_native_claim(self):
        # On any Source CI OS this calls the SAME driver with current source
        # Python rather than the Windows embedded Python. It cannot produce
        # NATIVE_WINDOWS_PASS; that requires CLI Windows+identity gates.
        groups = {"project_protocol": native.SUITES["project_protocol"],
                  "candidate_decision": native.SUITES["candidate_decision"]}
        with patch.object(native, "SUITES", groups), patch.object(native, "MIN_TESTS", {k:1 for k in groups}):
            suites = native.run_embedded_regressions(ROOT, Path(sys.executable), timeout=180)
        self.assertEqual(set(x["suite"] for x in suites), set(groups))
        self.assertTrue(all(x["tests"] >= 1 for x in suites))

    @unittest.skipUnless(os.name != "nt", "Linux gate confirms non-Windows does not claim Native")
    def test_linux_cli_does_not_claim_windows_native(self):
        with patch.object(sys, "argv", ["accept_native_business", "--root", str(ROOT),
                                        "--zip", str(ROOT / "not-a-candidate.zip"),
                                        "--expected-zip-sha256", "f"*64,
                                        "--evidence", str(ROOT / "should-not-create.json")]):
            self.assertEqual(native.main(), 2)
        self.assertFalse((ROOT / "should-not-create.json").exists())
