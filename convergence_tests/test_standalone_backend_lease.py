"""A directly launched C11 backend must honor the WPF/Browser single-writer lease.

All scenarios use a temporary synthetic data root and fake Uvicorn lifecycle;
no user SQLite, real WPF window, Provider or production Knowledge is opened.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from srw.workspace_lease import ACTIVE, ABSENT, WorkspaceLease, WorkspaceLeaseError, inspect_lease


class StandaloneBackendLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-backend-lease-")
        self.data = Path(self.tmp.name) / "workspace" / "data"
        self.args = Namespace(host="127.0.0.1", port=8791, edition="web", workspace_lock="backend")
        self.app = SimpleNamespace(state=SimpleNamespace())
        self.environment = {"RECRUITMENT_DATA_DIR": str(self.data),
                            "RECRUITMENT_FRONTEND_DIST": str(Path(self.tmp.name) / "front"),
                            "RECRUITMENT_KNOWLEDGE_DIR": str(Path(self.tmp.name) / "knowledge")}

    def tearDown(self):
        self.tmp.cleanup()

    def launch_with_fakes(self, *, on_run=None, on_restore=None, args=None):
        from scripts import run_local
        import launch_alpha10
        import srw.api.app
        import uvicorn
        with patch.dict(os.environ, self.environment), \
             patch.object(run_local, "parse_args", return_value=args or self.args), \
             patch.object(launch_alpha10, "apply_pending_restore", side_effect=on_restore) as restore, \
             patch.object(srw.api.app, "create_v1_app", return_value=self.app) as create_app, \
             patch.object(uvicorn, "Config", return_value=object()), \
             patch.object(uvicorn, "Server") as server:
            server.return_value.run.side_effect = on_run
            result = run_local.main()
        return result, restore, create_app

    def test_active_native_host_owner_blocks_before_any_backup_restore(self):
        with WorkspaceLease(self.data, edition="windows", port=8791):
            with self.assertRaises(SystemExit) as blocked:
                self.launch_with_fakes(on_restore=lambda: self.fail("restore before lease"))
            self.assertIn("INSTANCE_ALREADY_RUNNING", str(blocked.exception))
            self.assertEqual(inspect_lease(self.data).state, ACTIVE)

    def test_direct_backend_holds_lease_during_restore_api_and_server_then_releases(self):
        observed = []
        def on_restore():
            observed.append("restore")
            self.assertEqual(inspect_lease(self.data).state, ACTIVE)
            with self.assertRaises(WorkspaceLeaseError):
                WorkspaceLease(self.data, edition="windows").acquire()
        def on_run():
            observed.append("serve")
            self.assertEqual(inspect_lease(self.data).state, ACTIVE)
        result, restore, app = self.launch_with_fakes(on_run=on_run, on_restore=on_restore)
        self.assertEqual(result, 0)
        self.assertEqual(observed, ["restore", "serve"])
        restore.assert_called_once()
        app.assert_called_once()
        self.assertEqual(inspect_lease(self.data).state, ABSENT)

    def test_corrupt_foreign_lease_blocks_without_recovery_or_restore(self):
        directory = self.data / "app.lock"
        directory.mkdir(parents=True)
        marker = directory / "instance.json"
        marker.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(SystemExit) as blocked:
            self.launch_with_fakes(on_restore=lambda: self.fail("restore under corrupt lease"))
        self.assertIn("WORKSPACE_LEASE_UNUSABLE", str(blocked.exception))
        self.assertEqual(marker.read_text(encoding="utf-8"), "{not-json")

    def test_failing_backend_releases_lease_and_allows_a_clean_restart(self):
        def on_run():
            self.assertEqual(inspect_lease(self.data).state, ACTIVE)
            raise RuntimeError("synthetic Uvicorn failed")
        with self.assertRaisesRegex(RuntimeError, "synthetic Uvicorn failed"):
            self.launch_with_fakes(on_run=on_run)
        self.assertEqual(inspect_lease(self.data).state, ABSENT)
        result, _, _ = self.launch_with_fakes()
        self.assertEqual(result, 0)
        self.assertEqual(inspect_lease(self.data).state, ABSENT)

    def test_host_owned_mode_does_not_try_second_lease(self):
        args = Namespace(host="127.0.0.1", port=8791, edition="windows", workspace_lock="host")
        self.environment.update({"RECRUITMENT_INSTANCE_ID": "synthetic-host-id",
                                 "RECRUITMENT_SESSION_ID": "synthetic-session-id",
                                 "RECRUITMENT_SESSION_TOKEN": "synthetic-token-not-real"})
        with WorkspaceLease(self.data, edition="windows", port=8791):
            result, restore, app = self.launch_with_fakes(args=args,
                on_restore=lambda: self.assertEqual(inspect_lease(self.data).state, ACTIVE),
                on_run=lambda: self.assertEqual(inspect_lease(self.data).state, ACTIVE))
            self.assertEqual(result, 0)
            restore.assert_called_once()
            app.assert_called_once()
        self.assertEqual(inspect_lease(self.data).state, ABSENT)


if __name__ == "__main__":
    unittest.main()
