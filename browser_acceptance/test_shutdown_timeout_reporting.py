"""Pure browser-suite regression for the #159 post-202 Core shutdown timeout.

This does not launch Chromium, Core or a user workspace. It proves the real
browser acceptance's *failure reporting* contract: a 25-second timeout
remains FAIL, diagnostics are bounded and redacted, no second process wait,
and both clean and nonzero exits keep their original pass/fail semantics.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_restore_cancel_restart as acceptance


class _StubProcess:
    def __init__(self, *, code: int = 0, timeout: bool = False) -> None:
        self.code = code
        self.timeout = timeout
        self.waits: list[float | None] = []
        self.polls = 0
        self.communicates = 0
        self.terminates = 0

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        if self.timeout:
            raise subprocess.TimeoutExpired(
                cmd="PRIVATE-PROCESS-COMMAND-MUST-NOT-LEAK", timeout=timeout)
        return self.code

    def poll(self) -> int | None:
        self.polls += 1
        return None if self.timeout else self.code

    def communicate(self, *args, **kwargs):
        self.communicates += 1
        raise AssertionError("must never try to communicate with a hung Core")

    def terminate(self):
        self.terminates += 1
        raise AssertionError("diagnosis must leave process cleanup to tearDown")


class BrowserShutdownReportTests(unittest.TestCase):
    def make_case(self, root: Path):
        case = acceptance.RestoreCancelRestartAcceptance(
            "test_cancelled_restore_keeps_later_work_across_restart")
        case.root = root
        case.data = root / "data"
        case.stderr = SimpleNamespace(name=str(root / "backend.stderr.log"))
        case.api = lambda method, route, payload: self.assertEqual(
            (method, route, payload),
            ("POST", "/api/v1/runtime/shutdown", {}))
        return case

    def test_timeout_stays_failed_and_sensitive_state_is_redacted(self) -> None:
        secret = "abcDEF0123456789longsecret"
        with tempfile.TemporaryDirectory(prefix="srw-shutdown-fixture-") as tmp:
            root = Path(tmp)
            (root / "backend.stderr.log").write_text(
                f"Authorization: Bearer {secret}\n"
                "INFO: Application shutdown pending\n",
                encoding="utf-8")
            case = self.make_case(root)
            proc = _StubProcess(timeout=True)
            with self.assertRaises(AssertionError) as exc:
                case.stop_core(proc)
            report = str(exc.exception)
        self.assertIn("shutdown window (#159)", report)
        self.assertIn("process=alive", report)
        self.assertIn("elapsed_seconds=", report)
        self.assertIn("lease=", report)
        self.assertIn("Application shutdown pending", report)
        self.assertNotIn(secret, report)
        self.assertNotIn("PRIVATE-PROCESS-COMMAND", report)
        self.assertLess(len(report.encode("utf-8")), 2800)
        self.assertEqual(proc.waits, [25])
        self.assertEqual(proc.communicates, 0)
        self.assertEqual(proc.terminates, 0)

    def test_exit_zero_and_absent_lease_still_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="srw-shutdown-fixture-") as tmp:
            root = Path(tmp)
            # The real-process fixture now requires per-Core phase evidence.
            # Keep this pure unit test's synthetic clean-exit contract aligned.
            (root / "backend.stderr.log").write_text(
                "SRW_TEST_CORE_INSTANCE ordinal=1\\n"
                "SRW_SHUTDOWN_PHASE stage=drain_enter\\n"
                "SRW_SHUTDOWN_PHASE stage=lifespan_exit\\n",
                encoding="utf-8",
            )
            case = self.make_case(root)
            proc = _StubProcess()
            case.processes = [proc]
            with patch.object(acceptance, "inspect_lease",
                              return_value=SimpleNamespace(state=acceptance.ABSENT)):
                case.stop_core(proc)
        self.assertEqual(proc.waits, [25])

    def test_second_core_cannot_inherit_first_core_phase_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="srw-shutdown-fixture-") as tmp:
            root = Path(tmp)
            (root / "backend.stderr.log").write_text(
                "SRW_TEST_CORE_INSTANCE ordinal=1\\n"
                "SRW_SHUTDOWN_PHASE stage=drain_enter\\n"
                "SRW_SHUTDOWN_PHASE stage=lifespan_exit\\n"
                "SRW_TEST_CORE_INSTANCE ordinal=2\\n"
                "SRW_SHUTDOWN_PHASE stage=drain_enter\\n",
                encoding="utf-8",
            )
            case = self.make_case(root)
            proc = _StubProcess()
            case.processes = [_StubProcess(), proc]
            with patch.object(acceptance, "inspect_lease",
                              return_value=SimpleNamespace(state=acceptance.ABSENT)):
                with self.assertRaisesRegex(AssertionError, "test-only lifespan exit marker missing"):
                    case.stop_core(proc)
        self.assertEqual(proc.waits, [25])

    def test_nonzero_exit_still_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="srw-shutdown-fixture-") as tmp:
            case = self.make_case(Path(tmp))
            proc = _StubProcess(code=7)
            with self.assertRaises(AssertionError):
                case.stop_core(proc)
        self.assertEqual(proc.waits, [25])
