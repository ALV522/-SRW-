"""Deterministic tests for the bounded shutdown-timeout diagnosis (#159).

Why this module exists
----------------------
Issue #159 keeps one real Windows failure OPEN with an **unknown** root cause:
`test_real_restore_restart::test_backup_scheduled_then_tampered_restart_blocked_and_exact_retry_restores`
timed out inside `stop_server`'s `proc.wait(timeout=15)`. A later rerun passed,
which is exactly the case where "it went green" must not be accepted as an
explanation. These tests do not reproduce the hang and do not claim to; they pin
the *reporting* contract so the next occurrence is judgeable:

* the 15 s wait is unchanged and is still one `wait(timeout=15)` call;
* a timeout still **fails** the acceptance test;
* the failure carries elapsed time, process state, lease state and a bounded,
  redacted stderr tail;
* the diagnostic never calls `communicate()` on the live process, so it cannot
  become a second unbounded wait;
* a clean exit still passes and a non-zero exit still fails.

Everything is synthetic: a stub process object, no Core, no production data.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

# The acceptance TestCase is reached through its module alias on purpose:
# ``unittest.TestLoader.loadTestsFromModule`` collects every ``TestCase``
# attribute of a module, including imported ones, so importing the class by name
# would run the 8-second process-spawning acceptance test a second time from
# here. Only plain functions and constants are imported directly.
import test_real_restore_restart as restart_support
from test_real_restore_restart import (
    STDERR_READ_WINDOW_BYTES,
    STDERR_TAIL_BYTES,
    STDERR_TAIL_LINES,
    describe_shutdown_timeout,
    read_stderr_tail,
    redact_stderr_tail,
    safe_lease_state,
)

#: Any real credential-shaped string must disappear from a failure message.
PLANTED_SECRET = "0f" * 32
PLANTED_TOKEN = f"srw1.abcdef0123456789.{PLANTED_SECRET}"


class _StubProcess:
    """Minimal Popen stand-in: only the surface ``stop_server`` may touch."""

    def __init__(self, returncode: int | None = 0, *, wait_outcome: str = "exit") -> None:
        self.returncode = returncode
        self.pid = 424242
        self.wait_outcome = wait_outcome
        self.wait_calls: list[float | None] = []
        self.poll_calls = 0
        self.communicate_calls = 0
        self.terminate_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self.wait_outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="stub-core", timeout=timeout)
        assert self.returncode is not None
        return self.returncode

    def poll(self) -> int | None:
        self.poll_calls += 1
        return None if self.wait_outcome == "timeout" else self.returncode

    def communicate(self, *args, **kwargs):
        self.communicate_calls += 1
        raise AssertionError("diagnosis must not call communicate() on a live process")

    def terminate(self) -> None:
        self.terminate_calls += 1


class RedactionTests(unittest.TestCase):
    def test_credential_shapes_never_survive(self) -> None:
        raw = (
            f"presented {PLANTED_TOKEN} at the gate\n"
            "Authorization: Bearer abcdef0123456789abcdef\n"
            "Cookie: srw=abcdef0123456789; other=1\n"
            "X-SRW-Session: 0123456789abcdef\n"
            "token=abcdef0123456789 secret: hunter2\n"
            "push with ghp_abcdefghijklmnopqrstuvwxyz0123456789\n"
        )
        redacted = redact_stderr_tail(raw)
        for secret in (PLANTED_SECRET, "abcdef0123456789abcdef", "hunter2",
                       "ghp_abcdefghijklmnopqrstuvwxyz0123456789"):
            self.assertNotIn(secret, redacted)
        self.assertIn("srw1.<redacted>", redacted)
        self.assertIn("Authorization: <redacted>", redacted)
        self.assertIn("token=<redacted>", redacted)

    def test_a_bare_bearer_scheme_is_redacted_too(self) -> None:
        redacted = redact_stderr_tail("retry with Bearer abcdef0123456789abcdef\n")
        self.assertIn("Bearer <redacted>", redacted)
        self.assertNotIn("abcdef0123456789abcdef", redacted)

    def test_environment_assignments_lose_their_values(self) -> None:
        redacted = redact_stderr_tail(
            "RECRUITMENT_DATA_DIR=C:\\Users\\someone\\srw\\data\n"
            "PYTHONPATH=/home/someone/src/backend\n"
            "not_an_env_line=kept\n"
        )
        self.assertIn("RECRUITMENT_DATA_DIR=<redacted>", redacted)
        self.assertIn("PYTHONPATH=<redacted>", redacted)
        self.assertNotIn("someone", redacted)
        self.assertIn("not_an_env_line=kept", redacted)

    def test_workspace_root_becomes_a_placeholder(self) -> None:
        root = Path(tempfile.gettempdir()) / "srw-synthetic-workspace"
        raw = f"opening {root / 'data' / 'srw_v1.db'} for restore\n"
        redacted = redact_stderr_tail(raw, workspace_root=root)
        self.assertIn("<workspace>", redacted)
        self.assertIn("srw_v1.db", redacted)
        self.assertNotIn("srw-synthetic-workspace", redacted)
        self.assertNotIn(str(root.parent), redacted)

    def test_host_paths_keep_only_the_basename_and_location(self) -> None:
        redacted = redact_stderr_tail(
            '  File "C:\\Users\\someone\\proj\\backend\\srw\\api\\app.py", line 42\n'
            '  File "/home/someone/proj/backend/srw/api/app.py", line 43, in handler\n'
        )
        self.assertEqual(redacted.count("<path>/app.py"), 2)
        self.assertIn("line 42", redacted)
        self.assertIn("line 43", redacted)
        self.assertNotIn("someone", redacted)
        self.assertNotIn("proj", redacted)

    def test_api_routes_are_not_mistaken_for_paths(self) -> None:
        raw = "POST /api/v1/runtime/shutdown -> 202; readiness /health/ready -> 200\n"
        redacted = redact_stderr_tail(raw)
        self.assertIn("/api/v1/runtime/shutdown", redacted)
        self.assertIn("/health/ready", redacted)

    def test_only_the_tail_is_kept_and_it_is_byte_bounded(self) -> None:
        raw = b"HEAD-MARKER\n" + b"x" * (STDERR_TAIL_BYTES * 2) + b"\nTAIL-MARKER\n"
        redacted = redact_stderr_tail(raw)
        self.assertIn("TAIL-MARKER", redacted)
        self.assertNotIn("HEAD-MARKER", redacted)
        self.assertLessEqual(len(redacted.encode("utf-8")), STDERR_TAIL_BYTES)

    def test_line_count_is_bounded(self) -> None:
        raw = "\n".join(f"line-{index}" for index in range(STDERR_TAIL_LINES * 3))
        redacted = redact_stderr_tail(raw)
        self.assertEqual(len(redacted.splitlines()), STDERR_TAIL_LINES)
        self.assertIn(f"line-{STDERR_TAIL_LINES * 3 - 1}", redacted)
        self.assertNotIn("line-0\n", redacted + "\n")

    def test_undecodable_bytes_do_not_raise(self) -> None:
        redacted = redact_stderr_tail(b"\xff\xfe\x00broken \xf0\x9f")
        self.assertIsInstance(redacted, str)

    def test_path_collapsing_cannot_push_the_message_over_the_cap(self) -> None:
        # A *single* line is the case that escapes a line-count cap: "/a" ->
        # "<path>/a" turns 800 bytes into 3600, and one line is still one line,
        # so only a byte bound applied *after* redaction keeps the message small.
        raw = "/a " * 400
        redacted = redact_stderr_tail(raw)
        self.assertIn("<path>/a", redacted)
        self.assertEqual(len(redacted.splitlines()), 1)
        self.assertLessEqual(len(redacted.encode("utf-8")), STDERR_TAIL_BYTES)

    def test_a_credential_straddling_the_read_window_leaves_no_fragment(self) -> None:
        # The window starts 68 bytes into the token. Redacting after truncation
        # would keep the remaining secret suffix; the window is line-aligned and
        # the partial line is dropped whole.
        token = "srw1.abcdef0123456789." + "c" * 64
        suffix = b"z" * (STDERR_READ_WINDOW_BYTES - 20)
        raw = b"before\n" + token.encode() + b"\n" + suffix
        window_start = len(raw) - STDERR_READ_WINDOW_BYTES
        self.assertTrue(7 < window_start < 7 + len(token),
                        "fixture must place the window edge inside the token")
        redacted = redact_stderr_tail(raw)
        self.assertNotIn("srw1.", redacted)
        self.assertNotIn("c" * 64, redacted)
        self.assertIsNone(re.search(r"[0-9a-f]{16,}", redacted))
        self.assertLessEqual(len(redacted.encode("utf-8")), STDERR_TAIL_BYTES)

    def test_reading_a_file_that_starts_mid_line_drops_that_line(self) -> None:
        # A small explicit window makes the edge observable: with the production
        # window (8192) a token cut by the read edge is necessarily ~6 kB away
        # from the 2048-byte output tail, so it could never reach the message and
        # the defect would be invisible. Shrinking the window keeps the same code
        # path while letting a leak show.
        with tempfile.TemporaryDirectory(prefix="srw-stderr-window-") as tmp:
            log = Path(tmp) / "backend.stderr.log"
            token = "srw1.abcdef0123456789." + "d" * 64
            raw = b"q" * 200 + f"{token}\n".encode() + b"after-the-cutmarker\n"
            log.write_bytes(raw)
            window = 64
            self.assertTrue(len(raw) - window > 200,
                            "fixture must place the window edge inside the token")
            redacted = read_stderr_tail(log, window=window)
        self.assertIn("after-the-cutmarker", redacted,
                      "lines after the cut must still be reported")
        self.assertNotIn("srw1.", redacted)
        self.assertNotIn("d" * 32, redacted)

    def test_production_window_is_wider_than_the_output_cap(self) -> None:
        # The property that makes a read-edge cut unreachable in production: a
        # token split by the 8192-byte window has more than the entire output
        # budget (2048) behind it, so the fragment cannot survive the tail cap.
        self.assertGreater(STDERR_READ_WINDOW_BYTES - 128, STDERR_TAIL_BYTES)

    def test_a_single_line_longer_than_the_cap_keeps_its_tail(self) -> None:
        redacted = redact_stderr_tail("x" * (STDERR_TAIL_BYTES * 3) + "END-MARKER")
        self.assertIn("END-MARKER", redacted)
        self.assertTrue(redacted.startswith("…"))
        self.assertLessEqual(len(redacted.encode("utf-8")), STDERR_TAIL_BYTES)

    def test_reading_a_missing_log_is_named_not_raised(self) -> None:
        missing = Path(tempfile.gettempdir()) / "srw-no-such-stderr-log.log"
        self.assertTrue(read_stderr_tail(missing).startswith("unavailable:"))
        self.assertEqual(read_stderr_tail(missing), "unavailable:FileNotFoundError")


class RenderingTests(unittest.TestCase):
    def test_alive_and_exited_are_distinguishable(self) -> None:
        alive = describe_shutdown_timeout(elapsed_seconds=15.0, returncode=None,
                                          lease_state="active", stderr_tail="")
        exited = describe_shutdown_timeout(elapsed_seconds=0.5, returncode=9,
                                           lease_state="absent", stderr_tail="boom")
        self.assertIn("process=alive", alive)
        self.assertIn("process=exited(9)", exited)
        self.assertIn("elapsed_seconds=15.000", alive)
        self.assertIn("lease=active", alive)
        self.assertIn("<empty>", alive)
        self.assertIn("    boom", exited)

    def test_unrepresentable_elapsed_degrades_instead_of_raising(self) -> None:
        rendered = describe_shutdown_timeout(elapsed_seconds="not-a-number",  # type: ignore[arg-type]
                                             returncode=None, lease_state="absent",
                                             stderr_tail="x")
        self.assertIn("elapsed_seconds=unavailable", rendered)

    def test_safe_lease_state_names_a_broken_inspection(self) -> None:
        class Good:
            state = "absent"

        def broken(_data_dir):
            raise OSError("lease unreadable")

        self.assertEqual(safe_lease_state("/nowhere", inspection=lambda _d: Good()), "absent")
        self.assertEqual(safe_lease_state("/nowhere", inspection=broken),
                         "unavailable:OSError")


class ShutdownTimeoutContractTests(unittest.TestCase):
    """The acceptance path itself: still fails, still 15 s, now diagnosable."""

    def _case(self) -> "restart_support.RealProcessRestoreAcceptance":
        # A real TestCase is used on purpose: the contract under test is that the
        # *acceptance test* still fails, not that some helper returns a string.
        case = restart_support.RealProcessRestoreAcceptance(
            "test_backup_scheduled_then_tampered_restart_blocked_and_exact_retry_restores"
        )
        case.setUp()
        self.addCleanup(case.doCleanups)
        # Only the HTTP call is stubbed; shutdown acceptance itself is untouched.
        case.api = lambda method, path, payload=None: {"accepted": True}  # type: ignore[assignment]
        return case

    def test_timeout_still_fails_and_carries_bounded_redacted_diagnostics(self) -> None:
        case = self._case()
        case.stderr.write((
            f"shutdown requested with {PLANTED_TOKEN}\n"
            f"RECRUITMENT_DATA_DIR={case.data}\n"
            "Traceback (most recent call last):\n"
            '  File "C:\\host\\proj\\backend\\srw\\app.py", line 7, in run\n'
            "RuntimeError: synthetic shutdown wedged\n"
        ).encode("utf-8"))
        case.stderr.flush()
        stub = _StubProcess(returncode=None, wait_outcome="timeout")

        with self.assertRaises(AssertionError) as caught:
            case.stop_server(stub)

        message = str(caught.exception)
        # 1. the original contract is preserved: one bounded wait, no second wait
        self.assertEqual(stub.wait_calls, [15])
        self.assertEqual(stub.communicate_calls, 0)
        # 2. the four diagnostic facts are present and parseable
        self.assertIn("#159", message)
        self.assertIn("process=alive", message)
        self.assertIn("lease=absent", message)
        self.assertIn("RuntimeError: synthetic shutdown wedged", message)
        elapsed = [line for line in message.splitlines() if "elapsed_seconds=" in line][0]
        self.assertGreaterEqual(float(elapsed.split("=", 1)[1]), 0.0)
        # 3. nothing host-specific or credential-shaped leaks
        self.assertNotIn(PLANTED_SECRET, message)
        self.assertNotIn(str(case.data), message)
        self.assertNotIn(str(case.root), message)
        self.assertNotIn("C:\\host\\proj", message)
        self.assertIn("<path>/app.py", message)
        # 4. the message stays bounded
        self.assertLessEqual(len(message.encode("utf-8")), STDERR_TAIL_BYTES + 512)

    def test_clean_exit_still_passes(self) -> None:
        case = self._case()
        stub = _StubProcess(returncode=0)
        case.stop_server(stub)  # must not raise
        self.assertEqual(stub.wait_calls, [15])

    def test_non_zero_exit_still_fails(self) -> None:
        case = self._case()
        stub = _StubProcess(returncode=3)
        with self.assertRaises(AssertionError) as caught:
            case.stop_server(stub)
        self.assertIn("3 != 0", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
