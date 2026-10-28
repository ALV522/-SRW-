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

    def test_restore_with_unchanged_blob_tree_is_not_falsely_blocked(self):
        # A restore can legitimately revert only SQLite rows. If no new
        # candidate material was saved after the snapshot, the live Blobs
        # already match the target and should remain authoritative.
        self.old_blob.unlink()
        self.old_blob.parent.rmdir()
        target_blob = self.data / "blobs" / "new" / "replacement"
        target_blob.parent.mkdir(parents=True)
        target_blob.write_bytes(b"replacement synthetic blob")
        self.assertEqual(self._restart(), "target.zip")
        self.assertEqual(self._read_db(), "AFTER")
        self.assertEqual(target_blob.read_bytes(), b"replacement synthetic blob")
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.marker.exists())

    def test_identical_db_and_blobs_are_a_valid_noop_restore(self):
        # Source and live are identical: no destructive DB/Blob moves needed.
        # Write a NEW archive instead of rewriting the fixture's target.zip: the
        # merged #139 writer publishes with a no-clobber hard link, so re-using the
        # existing name would fail for the wrong reason and hide the no-op contract.
        noop = self.data / "backups" / "noop-unchanged.zip"
        write_backup_archive(noop, self.db, self.data / "blobs")
        self.marker.write_text(json.dumps({
            "backup": "noop-unchanged.zip",
            "sha256": hashlib.sha256(noop.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }), encoding="utf-8")
        self.assertEqual(self._restart(), "noop-unchanged.zip")
        self.assertEqual(self._read_db(), "BEFORE")
        self.assertEqual(self.old_blob.read_bytes(), b"original synthetic blob")
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.marker.exists())

    def test_malformed_undo_zip_cannot_authorize_database_swap(self):
        undo = self.data / "backups" / "pre_restore-broken.zip"
        undo.write_bytes(b"truncated synthetic ZIP")
        from srw.runtime.backup_truth import BackupTruthError
        with patch.object(launcher, "_pre_restore_backup", return_value=undo):
            with self.assertRaises(BackupTruthError):
                self._restart()
        self.assertEqual(self._read_db(), "BEFORE")
        self.assertEqual(self.old_blob.read_bytes(), b"original synthetic blob")
        self.assertTrue(self.marker.exists())
        self.assertFalse(self.journal.exists())

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

    def test_committed_cleanup_lock_allows_writes_then_restart_without_rechecking_target(self):
        # RED on the previous design: AV can hold an owned old DB after COMMITTED.
        # The first launch must complete the mandatory marker/journal transition,
        # while optional cleanup may be retried after real recruitment writes.
        original = Path.unlink
        old_db = self.data / ".srw_v1.db.restore-old"
        def blocked(path, *args, **kwargs):
            if path == old_db:
                raise PermissionError("synthetic AV owned rollback lock")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", blocked):
            self.assertEqual(self._restart(), "target.zip")
            self.assertFalse(self.marker.exists())
            self.assertTrue(old_db.exists())
            terminal = json.loads(self.journal.read_text(encoding="utf-8"))
            self.assertEqual(terminal["phase"], "FINALIZED_CLEANUP_PENDING")
            snapshots = list((self.data / "backups").glob("pre_restore-*.zip"))
            self.assertEqual(len(snapshots), 1)
            undo = snapshots[0].read_bytes()
            with closing(sqlite3.connect(self.db)) as conn:
                conn.execute("UPDATE workload SET value='NEW_USER_WRITE'")
                conn.commit()
            self.assertEqual(self._read_db(), "NEW_USER_WRITE")
            self.assertIsNone(self._restart())
            self.assertEqual(self._read_db(), "NEW_USER_WRITE")
            self.assertTrue(self.journal.exists())
        self.assertIsNone(self._restart())
        self.assertEqual(self._read_db(), "NEW_USER_WRITE")
        self.assertFalse(self.journal.exists())
        self.assertEqual(snapshots[0].read_bytes(), undo)
        self.assertEqual(len(list((self.data / "backups").glob("pre_restore-*.zip"))), 1)

    def test_finalized_cleanup_unknown_symlink_or_changed_undo_fails_closed(self):
        original = Path.unlink
        old_db = self.data / ".srw_v1.db.restore-old"
        def blocked(path, *args, **kwargs):
            if path == old_db:
                raise PermissionError("synthetic AV lock")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", blocked):
            self.assertEqual(self._restart(), "target.zip")
        self.assertEqual(json.loads(self.journal.read_text())["phase"],
                         "FINALIZED_CLEANUP_PENDING")
        original_undo = next((self.data / "backups").glob("pre_restore-*.zip"))
        before = original_undo.read_bytes()
        original_undo.write_bytes(b"changed synthetic undo")
        with self.assertRaisesRegex(RuntimeError, "pre-restore snapshot changed"):
            self._restart()
        original_undo.write_bytes(before)
        old_db.unlink()
        escape = self.root / "outside-old-db"
        escape.write_bytes(b"unowned synthetic")
        try:
            old_db.symlink_to(escape)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit creation of synthetic symlinks")
        with self.assertRaisesRegex(RuntimeError, "unsafe symlink"):
            self._restart()
        self.assertEqual(escape.read_bytes(), b"unowned synthetic")
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
