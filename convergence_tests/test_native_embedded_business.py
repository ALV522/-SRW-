"""Native embedded business test report is strict, synthetic and not WPF UI evidence."""
from __future__ import annotations

import json
import os
import subprocess
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
            suites = native.run_embedded_regressions(ROOT, Path(sys.executable).resolve(strict=True), timeout=180)
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


# A stand-in for a leaked child trace: a Windows user-site path plus a token. The
# probe must never put anything like this into a verdict.
LEAK_SENTINEL = "LEAKED-SITE-C:/Users/someone/AppData/Roaming/Python/secret-token"


def probe_line(missing=()) -> str:
    return native.PROBE_TAG + json.dumps({"missing": list(missing)}, separators=(",", ":"))


class EmbeddedDependencyProbeTests(unittest.TestCase):
    """The isolated interpreter is proven before any business suite runs (#172)."""

    def drive(self, handler, *, timeout: int = 180):
        """Run one probe plus one suite through a mocked subprocess.run."""
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return handler(argv, kwargs)

        groups = {"project_protocol": native.SUITES["project_protocol"]}
        with patch.object(native, "SUITES", groups), \
                patch.object(native, "MIN_TESTS", {name: 1 for name in groups}), \
                patch.object(native.subprocess, "run", side_effect=fake_run):
            try:
                return calls, native.run_embedded_regressions(
                    ROOT, Path(sys.executable).resolve(strict=True), timeout=timeout)
            except PayloadError as exc:
                return calls, exc

    @staticmethod
    def is_probe(argv) -> bool:
        return len(argv) > 4 and argv[4] == native.PROBE_DRIVER

    def test_probe_runs_first_with_the_same_isolation_as_the_suites(self):
        def handler(argv, kwargs):
            # The real driver emits one summary line; the probe emits one verdict.
            out = probe_line() if self.is_probe(argv) else native.DRIVER_TAG + json.dumps(
                {"tests": 2, "failures": 0, "errors": 0, "skipped": 0, "passed": True})
            return subprocess.CompletedProcess(argv, 0, out, "")

        calls, result = self.drive(handler)
        self.assertIsInstance(result, list, result)
        self.assertTrue(self.is_probe(calls[0][0]),
                        "the dependency probe must be the first child process")

        probe_argv, probe_kwargs = calls[0]
        self.assertEqual(list(probe_argv[:5]),
                         [str(Path(sys.executable).resolve(strict=True)), "-I", "-B", "-c",
                          native.PROBE_DRIVER])
        self.assertEqual(list(probe_argv[5:]), list(native.RUNTIME_DEPS))
        self.assertFalse(probe_kwargs["check"])

        suite_kwargs = calls[1][1]
        for key in ("cwd", "env", "timeout", "encoding", "errors"):
            self.assertEqual(probe_kwargs[key], suite_kwargs[key], key)
        self.assertEqual(probe_kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")

    def test_missing_dependencies_block_before_any_business_suite(self):
        for code in (0, 1):
            with self.subTest(code=code):
                calls, result = self.drive(
                    lambda argv, kwargs, c=code: subprocess.CompletedProcess(
                        argv, c, probe_line(["httpx"]), ""))
                self.assertIsInstance(result, PayloadError)
                self.assertEqual(len(calls), 1, "no business suite may run after a failed probe")
                message = str(result)
                for dependency in native.RUNTIME_DEPS:
                    self.assertIn(dependency, message)
                self.assertIn("user-site", message)
                self.assertIn("dev_venv.ps1", message)

    def test_probe_timeout_is_its_own_verdict(self):
        def handler(argv, kwargs):
            if self.is_probe(argv):
                raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])
            raise AssertionError("a business suite must not run after a probe timeout")

        calls, result = self.drive(handler)
        self.assertIsInstance(result, PayloadError)
        self.assertEqual(len(calls), 1)
        self.assertIn("timed out", str(result))
        self.assertNotIn("cannot import", str(result))

    def test_unrunnable_probe_is_its_own_verdict(self):
        def raising(argv, kwargs):
            raise OSError("cannot execute")

        calls, result = self.drive(raising)
        self.assertIsInstance(result, PayloadError)
        self.assertEqual(len(calls), 1)
        self.assertIn("no usable result", str(result))

        for code, stdout in [(0, ""), (0, "garbage"), (1, probe_line()),
                             (0, native.PROBE_TAG + "[]"),
                             (0, native.PROBE_TAG + '{"missing":"httpx"}'),
                             (0, probe_line() + "\n" + probe_line())]:
            with self.subTest(code=code, stdout=stdout[:24]):
                calls, result = self.drive(
                    lambda argv, kwargs, c=code, s=stdout: subprocess.CompletedProcess(argv, c, s, ""))
                self.assertIsInstance(result, PayloadError)
                self.assertEqual(len(calls), 1)
                self.assertIn("no usable result", str(result))

    def test_probe_output_is_never_echoed_in_the_verdict(self):
        for code, stdout in [(0, LEAK_SENTINEL + "\n" + probe_line(["httpx"])),
                             (1, LEAK_SENTINEL),
                             (0, probe_line() + LEAK_SENTINEL)]:
            with self.subTest(code=code):
                _, result = self.drive(
                    lambda argv, kwargs, c=code, s=stdout: subprocess.CompletedProcess(argv, c, s, ""))
                self.assertIsInstance(result, PayloadError)
                for leaked in ("LEAKED-SITE", "secret-token", "AppData"):
                    self.assertNotIn(leaked, str(result))

    def test_a_passing_probe_still_executes_and_validates_the_suites(self):
        def handler(argv, kwargs):
            out = probe_line() if self.is_probe(argv) else native.DRIVER_TAG + json.dumps(
                {"tests": 4, "failures": 0, "errors": 0, "skipped": 0, "passed": True})
            return subprocess.CompletedProcess(argv, 0, out, "")

        calls, result = self.drive(handler)
        self.assertEqual(result, [{"suite": "project_protocol", "status": "PASS", "tests": 4}])
        self.assertEqual([self.is_probe(argv) for argv, _ in calls], [True, False])

    def test_a_passing_probe_does_not_soften_a_failing_suite(self):
        def handler(argv, kwargs):
            if self.is_probe(argv):
                return subprocess.CompletedProcess(argv, 0, probe_line(), "")
            out = native.DRIVER_TAG + json.dumps(
                {"tests": 3, "failures": 0, "errors": 0, "skipped": 1, "passed": True})
            return subprocess.CompletedProcess(argv, 0, out, "")

        _, result = self.drive(handler)
        self.assertIsInstance(result, PayloadError, "a skip after a healthy probe is still a failure")
        self.assertIn("skipped or incomplete", str(result))

    def test_declared_runtime_dependencies_are_pinned(self):
        self.assertEqual(set(native.RUNTIME_DEPS), {"httpx", "sqlalchemy", "starlette"})
