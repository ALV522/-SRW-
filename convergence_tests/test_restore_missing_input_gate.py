"""#130 P0: a scheduled restore must fail closed, never be swallowed by the launcher.

The launcher used to wrap ``apply_pending_restore()`` in ``except FileNotFoundError:
pass``. Any ``FileNotFoundError`` raised *inside* an owned restore transaction (for
example the archive disappearing between validation and open) therefore let Core
start on stale data while the marker stayed behind: the operator saw a restore that
had been "scheduled" and silently did nothing.

These tests pin the two halves of the contract:
* a missing restore input raises, leaves no Core database, and keeps the marker bytes;
* the launcher does not convert that failure into a normal startup;
* a data dir that owns no restore still starts normally (no over-correction).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import launch_alpha10  # noqa: E402
import run_local  # noqa: E402
from srw.runtime.restore_transaction import apply_restore  # noqa: E402

SCHEMA = "v1_0014"


def _forbidden_schema(_path):
    raise AssertionError("read_schema must not run when the restore source is missing")


class MissingRestoreInputGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="srw-130-")
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.data.mkdir()
        self.db = self.data / "srw_v1.db"
        self.marker = self.data / "pending_restore.json"

    def _schedule(self, backup: str) -> bytes:
        raw = json.dumps({"backup": backup, "sha256": "0" * 64,
                          "schema_revision": SCHEMA},
                         separators=(",", ":")).encode("utf-8")
        self.marker.write_bytes(raw)
        return raw

    def test_missing_archive_fails_closed_and_keeps_marker_bytes(self):
        raw = self._schedule("srw-backup-vanished.zip")
        with self.assertRaises(RuntimeError) as caught:
            apply_restore(self.data, self.db, SCHEMA, lambda: None, _forbidden_schema)
        self.assertIn("fail closed", str(caught.exception))
        self.assertFalse(self.db.exists(), "Core database must not be created")
        self.assertEqual(self.marker.read_bytes(), raw,
                         "marker must survive byte-for-byte so a retry can resume")

    def test_launcher_does_not_swallow_file_not_found(self):
        raw = self._schedule("srw-backup-vanished.zip")
        env = {"RECRUITMENT_DATA_DIR": str(self.data)}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(sys, "argv", ["run_local.py", "--port", "8123"]), \
                mock.patch.object(launch_alpha10, "apply_pending_restore",
                                  side_effect=FileNotFoundError("restore input vanished")), \
                mock.patch("srw.api.app.create_v1_app",
                           side_effect=AssertionError("Core must not start")), \
                mock.patch("uvicorn.Config"), mock.patch("uvicorn.Server"):
            with self.assertRaises(FileNotFoundError):
                run_local.main()
        self.assertFalse(self.db.exists(),
                         "Core must not start after a failed pending restore")
        self.assertEqual(self.marker.read_bytes(), raw)

    def test_workspace_without_restore_still_starts(self):
        env = {"RECRUITMENT_DATA_DIR": str(self.data)}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(sys, "argv", ["run_local.py", "--port", "8123"]), \
                mock.patch.object(launch_alpha10, "apply_pending_restore") as restore, \
                mock.patch("srw.api.app.create_v1_app", return_value=mock.Mock()) as created, \
                mock.patch("uvicorn.Config"), mock.patch("uvicorn.Server"):
            self.assertEqual(run_local.main(), 0)
        restore.assert_called_once()
        created.assert_called_once()


if __name__ == "__main__":
    unittest.main()
