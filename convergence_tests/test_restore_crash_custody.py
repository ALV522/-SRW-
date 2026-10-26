"""P0 #130 RED regressions: restore crash ownership and undo snapshot custody.

All bytes are disposable synthetic SQLite/Blob material. A deliberately killed
child process tests a process death, not just a Python exception/finally path.
On the current launcher these two tests FAIL; they are the implementation
contract, not a patch to the restore code.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts import launch_alpha10 as launcher
from srw.runtime.backup_truth import write_backup_archive, validate_backup_archive

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CLOCK = "20990101-030405"


class RestoreCrashCustodyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-restore-crash-custody-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.db = self.data / "srw_v1.db"
        self.backups = self.data / "backups"
        self.backups.mkdir()
        self._db(self.db, "BEFORE")
        self.old_blob = self.data / "blobs" / "old" / "previous"
        self.old_blob.parent.mkdir(parents=True)
        self.old_blob.write_bytes(b"BEFORE synthetic blob")

        source = self.root / "to-restore.db"
        self._db(source, "AFTER")
        new_blobs = self.root / "to-restore-blobs" / "new"
        new_blobs.mkdir(parents=True)
        (new_blobs / "replacement").write_bytes(b"AFTER synthetic blob")
        self.archive = self.backups / "target.zip"
        write_backup_archive(self.archive, source, new_blobs.parent)
        self.marker = self.data / "pending_restore.json"
        self.marker.write_text(json.dumps({
            "backup": self.archive.name,
            "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }), encoding="utf-8")

    @staticmethod
    def _db(path: Path, value: str):
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            conn.execute("CREATE TABLE workload (value TEXT NOT NULL)")
            conn.execute("INSERT INTO workload VALUES (?)", (value,))
            conn.commit()

    def _value(self, path: Path):
        with closing(sqlite3.connect(path)) as conn:
            return conn.execute("SELECT value FROM workload").fetchone()[0]

    def test_unclaimed_prior_rollback_file_is_never_deleted_by_a_new_restore(self):
        # An old rollback file without a journal has UNKNOWN ownership.
        # A fail-closed implementation may reject the restore; silently
        # deleting somebody else's rollback bytes is never permitted.
        orphan = self.data / ".srw_v1.db.restore-old"
        orphan.write_bytes(b"synthetic prior rollback material; keep exact bytes")
        sentinel = orphan.read_bytes()
        with patch.object(launcher, "DATA", self.data), patch.object(launcher, "DB", self.db):
            try:
                launcher.apply_pending_restore()
            except (OSError, RuntimeError):
                pass
        self.assertTrue(orphan.is_file(),
                        "UNOWNED rollback file was deleted/overwritten without journal custody")
        self.assertEqual(orphan.read_bytes(), sentinel,
                         "UNOWNED rollback bytes changed without a verified transaction owner")

    def test_hard_process_kill_after_db_publish_preserves_original_undo_on_restart(self):
        # Kill the *subprocess* immediately after os.replace(new_db, live_db).
        # The current launcher leaves a mixed state and a pending marker.
        # A second start must not replace the original undo ZIP with a
        # snapshot of that partially published replacement database.
        code = """
import os, sys
from pathlib import Path
from scripts import launch_alpha10 as launch
data = Path(sys.argv[1])
launch.DATA = data
launch.DB = data / "srw_v1.db"
launch.time.strftime = lambda fmt: "20990101-030405"
real_replace = launch.os.replace

def kill_at_db_publication(source, destination):
    real_replace(source, destination)
    if Path(destination) == launch.DB and Path(source).name == ".srw_v1.db.restore-new":
        os._exit(97)

launch.os.replace = kill_at_db_publication
launch.apply_pending_restore()
raise SystemExit(98)
"""
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [
            str(ROOT), str(ROOT / "backend"), env.get("PYTHONPATH", ""),
        ]))
        proc = subprocess.run(
            [sys.executable, "-c", code, str(self.data)],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(proc.returncode, 97,
                         f"the process-kill checkpoint did not execute: {proc.stderr}")
        snapshot = self.backups / ("pre_restore-" + SYNTHETIC_CLOCK + ".zip")
        self.assertTrue(snapshot.is_file(), "initial pre-restore undo was not published")
        original_snapshot = snapshot.read_bytes()
        self.assertEqual(validate_backup_archive(snapshot)["manifest_present"], True)
        self.assertEqual(self._value(self.data / ".srw_v1.db.restore-old"), "BEFORE")
        self.assertEqual(self._value(self.db), "AFTER")
        self.assertEqual(self.old_blob.read_bytes(), b"BEFORE synthetic blob")
        self.assertTrue(self.marker.exists())

        with patch.object(launcher, "DATA", self.data), \
             patch.object(launcher, "DB", self.db), \
             patch.object(launcher.time, "strftime",
                          side_effect=lambda fmt: SYNTHETIC_CLOCK):
            try:
                launcher.apply_pending_restore()
            except (OSError, RuntimeError):
                # A journal-aware implementation is allowed to stop fail-closed
                # if it cannot safely decide whether to roll forward/back.
                pass

        self.assertTrue(snapshot.is_file(),
                        "the original pre-restore undo disappeared on restart")
        self.assertEqual(snapshot.read_bytes(), original_snapshot,
                         "restart replaced the original undo with a partial AFTER-state snapshot")


if __name__ == "__main__":
    unittest.main()
