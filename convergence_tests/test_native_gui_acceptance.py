"""Pure parser/state-gate regression tests, no WPF process or user data."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.accept_rebuilt_native_gui import (
    REQUIRED, safe_host_events, verify_gui_event_sequence,
)
from scripts.native_payload import PayloadError


class NativeGuiAcceptanceTests(unittest.TestCase):
    def test_complete_lifecycle_and_closed_lock(self):
        r = verify_gui_event_sequence(list(REQUIRED), lock_exists=False)
        self.assertTrue(r["wpf_navigation_loaded"])
        self.assertTrue(r["graceful_shutdown"])
        self.assertTrue(r["workspace_lock_released"])

    def test_backend_ready_alone_is_not_gui_pass(self):
        with self.assertRaisesRegex(PayloadError, "frontend_loaded"):
            verify_gui_event_sequence(["host_started", "backend_ready"], lock_exists=False)

    def test_missing_lock_release_blocks(self):
        with self.assertRaisesRegex(PayloadError, "lock remains"):
            verify_gui_event_sequence(list(REQUIRED), lock_exists=True)

    def test_wrong_event_order_blocks(self):
        bad = list(REQUIRED)
        bad.remove("frontend_loaded")
        bad.insert(2, "frontend_loaded")
        with self.assertRaisesRegex(PayloadError, "out of order"):
            verify_gui_event_sequence(bad, lock_exists=False)

    def test_no_raw_candidate_ids_enter_sanitized_event_names(self):
        with tempfile.TemporaryDirectory(prefix="srw-gui-events-test-") as td:
            log = Path(td) / "host.log"
            record = {"event": "frontend_loaded", "details": {
                "url": "/api/v1/candidates/private-candidate-id?token=secret"}}
            log.write_text(json.dumps(record) + "\n", encoding="utf-8")
            self.assertEqual(safe_host_events(log), ["frontend_loaded"])
            self.assertNotIn("private-candidate-id", str(safe_host_events(log)))

    def test_restart_must_use_only_current_cycle_log_events(self):
        with tempfile.TemporaryDirectory(prefix="srw-gui-restarts-test-") as td:
            log = Path(td) / "host.log"
            log.write_text("".join(json.dumps({"event": x}) + "\n" for x in REQUIRED),
                           encoding="utf-8")
            offset = log.stat().st_size
            with log.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"event": "host_started"}) + "\n")
            self.assertEqual(safe_host_events(log, offset=offset), ["host_started"])
            with self.assertRaisesRegex(PayloadError, "backend_ready"):
                verify_gui_event_sequence(safe_host_events(log, offset=offset), lock_exists=False)

    def test_unknown_or_malformed_log_lines_are_ignored(self):
        with tempfile.TemporaryDirectory(prefix="srw-gui-broken-json-test-") as td:
            log = Path(td) / "host.log"
            log.write_text("broken\n" + json.dumps({"event": "backend_ready"}) + "\n"
                           + json.dumps({"event": "backend_stderr", "details": {
                               "line": "secret"}}) + "\n", encoding="utf-8")
            self.assertEqual(safe_host_events(log), ["backend_ready"])

    def test_truncated_log_between_cycles_rejected(self):
        with tempfile.TemporaryDirectory(prefix="srw-gui-truncated-test-") as td:
            log = Path(td) / "host.log"
            log.write_text("A", encoding="utf-8")
            with self.assertRaisesRegex(PayloadError, "truncated"):
                safe_host_events(log, offset=2)


if __name__ == "__main__":
    unittest.main()
