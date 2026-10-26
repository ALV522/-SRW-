"""P0 #130: real subprocess death at successive durable restore checkpoints.

All state is synthetic and isolated. A killed child bypasses Python finally,
then the *same* workspace is opened again to prove idempotent recovery.
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


class RestoreJournalCheckpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-journal-matrix-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.db = self.data / "srw_v1.db"
        self._make_db(self.db, "BEFORE")
        self.old_blob = self.data / "blobs" / "old" / "legacy"
        self.old_blob.parent.mkdir(parents=True)
        self.old_blob.write_bytes(b"original synthetic blob")

        src = self.root / "source.db"
        self._make_db(src, "AFTER")
        src_blobs = self.root / "src-blobs" / "new"
        src_blobs.mkdir(parents=True)
        (src_blobs / "replacement").write_bytes(b"replacement synthetic blob")
        self.archive = self.data / "backups" / "target.zip"
        write_backup_archive(self.archive, src, src_blobs.parent)
        self.marker = self.data / "pending_restore.json"
        self.marker.write_text(json.dumps({
            "backup": "target.zip", "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }), encoding="utf-8")
        self.journal = self.data / ".srw-restore-journal.json"

    @staticmethod
    def _make_db(path, value):
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            conn.execute("CREATE TABLE workload (value TEXT NOT NULL)")
            conn.execute("INSERT INTO workload VALUES (?)", (value,))
            conn.commit()

    def _read_db(self):
        with closing(sqlite3.connect(self.db)) as conn:
            return conn.execute("SELECT value FROM workload").fetchone()[0]

    def _restart(self):
        with patch.object(launcher, "DATA", self.data), patch.object(launcher, "DB", self.db):
            return launcher.apply_pending_restore()

    def _child_die_after_rename(self, destination, source_name):
        script = """
import os
import sys
from pathlib import Path
from scripts import launch_alpha10 as launcher
root = Path(sys.argv[1])
destination = root / sys.argv[2]
source_name = sys.argv[3]
launcher.DATA = root
launcher.DB = root / "srw_v1.db"
original = os.replace
def crash(source, target):
    original(source, target)
    if Path(target) == destination and Path(source).name == source_name:
        os._exit(97)
os.replace = crash
launcher.apply_pending_restore()
raise SystemExit(98)
"""
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (
            str(ROOT), str(ROOT / "backend"), env.get("PYTHONPATH", ""),
        )))
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.data), destination, source_name],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 97, result.stderr)
        self.assertTrue(self.journal.is_file(), "child did not publish a restore journal")
        self.assertTrue(self.marker.is_file(), "child incorrectly cleared restore plan")

    def _assert_single_undo_and_finish(self):
        snapshots = list((self.data / "backups").glob("pre_restore-*.zip"))
        self.assertEqual(len(snapshots), 1)
        undo = snapshots[0]
        before = undo.read_bytes()
        self.assertTrue(validate_backup_archive(undo)["manifest_present"])
        self.assertEqual(self._restart(), "target.zip")
        self.assertEqual(self._read_db(), "AFTER")
        self.assertFalse(self.old_blob.exists())
        self.assertEqual((self.data / "blobs" / "new" / "replacement").read_bytes(),
                         b"replacement synthetic blob")
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.journal.exists())
        self.assertEqual(undo.read_bytes(), before)
        self.assertEqual(list((self.data / "backups").glob("pre_restore-*.zip")), [undo])
        # A second restart must not replay a committed plan.
        self.assertIsNone(self._restart())
        self.assertEqual(undo.read_bytes(), before)

    def test_kill_after_original_db_moved_before_new_db_publish(self):
        self._child_die_after_rename(".srw_v1.db.restore-old", "srw_v1.db")
        self.assertFalse(self.db.exists())
        self.assertTrue((self.data / ".srw_v1.db.restore-old").exists())
        self._assert_single_undo_and_finish()

    def test_kill_after_original_blobs_moved_before_new_blobs_publish(self):
        self._child_die_after_rename(".blobs.restore-old", "blobs")
        self.assertFalse((self.data / "blobs").exists())
        self.assertTrue((self.data / ".blobs.restore-old").exists())
        self._assert_single_undo_and_finish()

    def test_kill_after_new_blobs_published_before_committed_journal(self):
        self._child_die_after_rename("blobs", ".blobs.restore-new")
        self.assertEqual(self._read_db(), "AFTER")
        self.assertEqual((self.data / "blobs" / "new" / "replacement").read_bytes(),
                         b"replacement synthetic blob")
        self._assert_single_undo_and_finish()

    def test_inconsistent_journal_fails_closed_before_any_unowned_cleanup(self):
        journal = self.journal
        journal.write_text('{"schema":"unknown-restore-journal"}', encoding="utf-8")
        existing = self.db.read_bytes()
        blob = self.old_blob.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "unknown restore journal"):
            self._restart()
        self.assertEqual(self.db.read_bytes(), existing)
        self.assertEqual(self.old_blob.read_bytes(), blob)
        self.assertTrue(self.marker.exists())

    def test_unknown_prior_blob_rollback_is_preserved(self):
        leftover = self.data / ".blobs.restore-old"
        leftover.mkdir()
        (leftover / "do-not-delete").write_bytes(b"unowned synthetic rollback")
        with self.assertRaisesRegex(RuntimeError, "unclaimed restore rollback"):
            self._restart()
        self.assertEqual((leftover / "do-not-delete").read_bytes(),
                         b"unowned synthetic rollback")
        self.assertEqual(self._read_db(), "BEFORE")
        self.assertTrue(self.marker.exists())

    def test_missing_pinned_undo_after_crash_stops_before_serving(self):
        self._child_die_after_rename(".srw_v1.db.restore-old", "srw_v1.db")
        snapshots = list((self.data / "backups").glob("pre_restore-*.zip"))
        self.assertEqual(len(snapshots), 1)
        snapshots[0].write_bytes(b"tampered undo synthetic test")
        with self.assertRaisesRegex(RuntimeError, "pre-restore snapshot changed"):
            self._restart()
        self.assertFalse(self.db.exists())
        self.assertTrue((self.data / ".srw_v1.db.restore-old").exists())
        self.assertTrue(self.journal.exists())

    def test_committed_marker_cleanup_failure_retries_without_second_undo(self):
        real_unlink = Path.unlink
        failure = []

        def interrupted_unlink(path, *args, **kwargs):
            if path == self.marker and not failure:
                failure.append(True)
                raise PermissionError("simulated antivirus marker lock")
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", interrupted_unlink):
            with self.assertRaisesRegex(PermissionError, "marker lock"):
                self._restart()
        self.assertEqual(failure, [True])
        state = json.loads(self.journal.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "COMMITTED")
        self.assertEqual(self._read_db(), "AFTER")
        self._assert_single_undo_and_finish()


if __name__ == "__main__":
    unittest.main()
