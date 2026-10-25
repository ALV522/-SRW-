from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_windows_host_gui_log import REQUIRED, inspect


class NativeHostLogAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "host.log"

    def _write(self, *, events=REQUIRED, additional=(), session="session-synthetic"):
        rows = []
        for index, event in enumerate(events):
            rows.append({
                "ts": f"2026-10-19T03:12:{index:02d}+00:00",
                "event": event,
                "identity": {"host_session_id": session, "instance_id": "sensitive"},
                "details": {"application_root": "D:/private/path"},
            })
        for index, (method, uri, code) in enumerate(additional, start=len(events)):
            rows.append({
                "ts": f"2026-10-19T03:12:{index:02d}+00:00",
                "event": "backend_stdout", "identity": {"host_session_id": session},
                "details": {"line": f'INFO:     127.0.0.1:9999 - "{method} {uri} HTTP/1.1" {code} TEST'},
            })
        self.file.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        return rows

    def test_gui_lifecycle_pass_with_recruitment_writes_and_nonblocking_favicon(self):
        self._write(additional=(
            ("POST", "/api/v1/projects", 200),
            ("PATCH", "/api/v1/protocol-revisions/sensitive-uuid", 200),
            ("GET", "/favicon.ico", 404),
        ))
        out = inspect(self.file)
        self.assertEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")
        self.assertTrue(out["host_shutdown_clean"])
        self.assertEqual(out["business_operations_http_success"]["project_created_http_200"], 1)
        self.assertEqual(out["business_operations_http_success"]["protocol_revision_updated_http_200"], 1)
        self.assertEqual(out["nonblocking_issues"], ["favicon_404_nonblocking"])
        self.assertFalse(out["full_recruitment_business_accepted"])
        self.assertNotIn("sensitive-uuid", json.dumps(out))
        self.assertNotIn("D:/private/path", json.dumps(out))
        self.assertEqual(out["timing"]["seconds_to_frontend_loaded"], 6)

    def test_modern_redacted_host_http_records_operator_route_families_not_exact_actions(self):
        rows = self._write()
        rows.extend({
            "ts": "2026-10-19T03:12:20+00:00", "event": "backend_http",
            "identity": {"host_session_id": "session-synthetic"},
            "details": details,
        } for details in (
            {"method": "POST", "status": 200, "route": "project_api"},
            {"method": "PATCH", "status": 200, "route": "protocol_api"},
            {"method": "POST", "status": 201, "route": "candidate_api"},
            {"method": "POST", "status": 409, "route": "candidate_api"},
            {"method": "POST", "status": 200, "route": "private-SYNTHETIC_SECRET"},
            {"method": ["POST", "SYNTHETIC_SECRET"], "status": 200, "route": "candidate_api"},
            {"method": "POST", "status": 200, "route": ["candidate_api", "SYNTHETIC_SECRET"]},
            {"method": "GET", "status": 200, "route": "candidate_api"},
        ))
        self.file.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        out = inspect(self.file)
        self.assertEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")
        self.assertEqual(out["business_http_redacted_write_counts"], {
            "POST project_api": 1, "PATCH protocol_api": 1, "POST candidate_api": 1,
        })
        # Route FAMILY cannot prove a specific candidate create / protocol
        # publish. Do not elevate these counts to complete workflow acceptance.
        self.assertEqual(out["business_operations_http_success"], {})
        self.assertFalse(out["full_recruitment_business_accepted"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(out))
        self.assertNotIn("session-synthetic", json.dumps(out))

    def test_mixed_legacy_and_redacted_events_use_one_nonduplicating_source(self):
        rows = self._write(additional=(("POST", "/api/v1/projects", 200),))
        rows.append({
            "ts": "2026-10-19T03:12:20+00:00", "event": "backend_http",
            "identity": {"host_session_id": "session-synthetic"},
            "details": {"method": "POST", "status": 200, "route": "project_api"},
        })
        self.file.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        out = inspect(self.file)
        self.assertEqual(out["business_http_redacted_write_counts"], {"POST project_api": 1})
        self.assertEqual(out["business_operations_http_success"], {})

    def test_missing_frontend_load_fails_despite_backend_ready(self):
        self._write(events=tuple(x for x in REQUIRED if x != "frontend_loaded"))
        out = inspect(self.file)
        self.assertNotEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")
        self.assertIn("frontend_loaded", out["missing_lifecycle_event_names"])

    def test_forced_kill_or_http_500_fails_closed(self):
        self._write(events=REQUIRED + ("backend_force_kill",),
                    additional=(("GET", "/api/v1/dashboard", 500),))
        out = inspect(self.file)
        self.assertNotEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")
        self.assertIn("backend_force_kill", out["nonretryable_or_forced_host_events"])
        self.assertGreater(out["fatal_log_count"], 0)

    def test_cannot_stitch_lifecycle_across_different_host_sessions(self):
        first = self._write(events=REQUIRED[:6], session="early")
        second = self._write(events=REQUIRED[6:], session="later")
        self.file.write_text("\n".join(json.dumps(row) for row in first + second))
        out = inspect(self.file)
        self.assertEqual(out["sessions_in_log"], 2)
        self.assertNotEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")

    def test_out_of_order_shutdown_is_not_accepted(self):
        events = list(REQUIRED)
        a, b = events.index("workspace_released"), events.index("host_closed")
        events[a], events[b] = events[b], events[a]
        self._write(events=events)
        out = inspect(self.file)
        self.assertFalse(out["required_lifecycle_events_complete"])
        self.assertNotEqual(out["status"], "WINDOWS_GUI_BASELINE_HOST_LOG_PASS")


if __name__ == "__main__":
    unittest.main()
