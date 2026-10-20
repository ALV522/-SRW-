"""Synthetic Host JSONL evidence must not turn errors into GUI acceptance."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.accept_rebuilt_native_gui import safe_host_events, verify_gui_event_sequence
from scripts.audit_windows_host_gui_log import REQUIRED, inspect
from scripts.native_payload import PayloadError


class GuiEvidenceFailClosedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log = Path(temporary.name) / 'host.log'

    def records(self):
        return [{'event': e, 'identity': {'host_session_id': 'synthetic-session'},
                 'details': None} for e in REQUIRED]

    def write(self, records):
        self.log.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')

    def accept(self):
        return verify_gui_event_sequence(safe_host_events(self.log), lock_exists=False)

    def test_clean_sanitized_session_remains_accepted(self):
        rows = self.records()
        rows.insert(7, {'event': 'backend_http', 'identity': rows[0]['identity'],
                        'details': {'status': 200, 'method': 'GET', 'route': 'runtime_api'}})
        rows.insert(7, {'event': 'backend_stdout', 'identity': rows[0]['identity'],
                        'details': {'line': '"GET /api/v1/ERROR HTTP/1.1" 200'}})
        self.write(rows)
        self.assertTrue(self.accept()['graceful_shutdown'])
        self.assertEqual(inspect(self.log)['status'], 'WINDOWS_GUI_BASELINE_HOST_LOG_PASS')

    def test_error_events_cannot_be_hidden_by_complete_lifecycle(self):
        for event, details in [('backend_force_kill', None), ('backend_exception', {'exception_type': 'ValueError'}),
                               ('backend_http', {'status': 500}), ('shutdown_request_failed', None),
                               ('webview_failed', None), ('backend_start_retry', None),
                               ('backend_stderr', 'ERROR: synthetic failure'),
                               ('backend_stderr', {'line': 'Exception: synthetic failure'}),
                               ('backend_stdout', {'line': 'ValueError: synthetic failure'})]:
            with self.subTest(event=event):
                rows = self.records()
                rows.insert(7, {'event': event, 'identity': rows[0]['identity'], 'details': details})
                self.write(rows)
                with self.assertRaises(PayloadError):
                    self.accept()

    def test_log_auditor_recognizes_sanitized_errors(self):
        for event, details in [('backend_exception', {'exception_type': 'ValueError'}),
                               ('backend_http', {'status': 503}), ('shutdown_request_failed', None)]:
            with self.subTest(event=event):
                rows = self.records()
                rows.insert(7, {'event': event, 'identity': rows[0]['identity'], 'details': details})
                self.write(rows)
                self.assertNotEqual(inspect(self.log)['status'], 'WINDOWS_GUI_BASELINE_HOST_LOG_PASS')

    def test_lifecycle_cannot_be_stitched_from_two_sessions(self):
        rows = self.records()
        for row in rows[6:]:
            row['identity'] = {'host_session_id': 'other-synthetic-session'}
        self.write(rows)
        with self.assertRaises(PayloadError):
            self.accept()

    def test_missing_identity_and_malformed_final_records_block(self):
        for mode in ('identity', 'json', 'utf8'):
            with self.subTest(mode=mode):
                rows = self.records()
                if mode == 'identity':
                    rows[0].pop('identity')
                self.write(rows)
                if mode != 'identity':
                    with self.log.open('ab') as out:
                        out.write(b'not-json\n' if mode == 'json' else b'\xff\n')
                with self.assertRaises(PayloadError):
                    self.accept()

    def test_error_messages_and_reports_do_not_expose_raw_details(self):
        rows = self.records()
        rows.insert(7, {'event': 'backend_exception', 'identity': rows[0]['identity'],
                        'details': {'message': 'SYNTHETIC_PRIVATE_TOKEN', 'exception_type': 'ValueError'}})
        self.write(rows)
        with self.assertRaises(PayloadError) as caught:
            self.accept()
        self.assertNotIn('SYNTHETIC_PRIVATE_TOKEN', str(caught.exception))
        self.assertNotIn('synthetic-session', str(caught.exception))
        self.assertNotIn('SYNTHETIC_PRIVATE_TOKEN', json.dumps(inspect(self.log)))
