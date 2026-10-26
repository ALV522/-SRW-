"""Restore residue must not survive a hard kill while holding candidate data.

``apply_pending_restore`` unpacks the scheduled archive into a TemporaryDirectory
named ``srw-restore-*`` inside ``data/`` and takes the pre-restore rollback copy
in ``srw-prerestore-*``. ``TemporaryDirectory`` removes both on normal exit, but a
hard kill (power loss, Task Manager, ``os._exit``) leaves them on disk with a full
database snapshot and every Source blob. `cleanup_stale_backup_artifacts` only
knows ``.backup-snapshot-*``, ``.restore-staging-*`` and the ``backups/`` staging
patterns, so those two directories are never reclaimed.

Two consequences, both operator-visible:

* disk and privacy: an interrupted restore keeps a second copy of the whole
  recruiting database and its evidence files in a public workspace directory,
  outside any backup retention rule;
* supportability: repeated failed restores accumulate, and nothing tells the
  operator why ``data/`` keeps growing.

These cases are **deterministic and currently RED by design**: they assert the
reclaim that Track A chose to implement together with the crash-safe restore
journal (#130). They are test-only; no launcher, Core, Schema or Host file is
touched, and the production fix stays Track A's.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from srw.runtime.maintenance import cleanup_stale_backup_artifacts

DB_BYTES = b"SQLite format 3\x00synthetic-database-snapshot"
BLOB_BYTES = b"synthetic candidate evidence bytes"


def _make_residue(root: Path, prefix: str) -> Path:
    """Recreate what a hard-killed restore leaves behind under ``data/``."""

    residue = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    (residue / "srw_v1.db").write_bytes(DB_BYTES)
    blob_dir = residue / "blobs" / "ab"
    blob_dir.mkdir(parents=True)
    (blob_dir / ("ab" * 32)).write_bytes(BLOB_BYTES)
    return residue


class RestoreResidueCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(
            prefix="srw-restore-residue-", ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        (self.data / "backups").mkdir(parents=True)

    # ------------------------------------------------------------------ tests

    def test_hard_killed_restore_work_directory_is_reclaimed(self) -> None:
        residue = _make_residue(self.data, "srw-restore-")
        self.assertTrue(residue.is_dir(), "fixture must exist before cleanup")

        cleanup_stale_backup_artifacts(self.data)

        self.assertFalse(
            residue.exists(),
            "a hard-killed srw-restore-* directory holds a full database snapshot "
            "and every Source blob; startup cleanup must reclaim it",
        )

    def test_hard_killed_pre_restore_snapshot_is_reclaimed(self) -> None:
        residue = _make_residue(self.data, "srw-prerestore-")
        self.assertTrue(residue.is_dir(), "fixture must exist before cleanup")

        cleanup_stale_backup_artifacts(self.data)

        self.assertFalse(
            residue.exists(),
            "a hard-killed srw-prerestore-* directory is a duplicate of the live "
            "database and must not outlive the restore attempt",
        )

    def test_unrelated_directories_are_still_left_alone(self) -> None:
        # The reclaim must stay a name-scoped cleanup, not "delete everything that
        # looks temporary": an operator workspace may hold legitimate folders.
        # Names inside the SRW prefix namespace (``srw-restore-*``) are SRW-owned by
        # convention and are intentionally not used as the control here.
        keep_dir = self.data / "evidence"
        keep_dir.mkdir()
        (keep_dir / "note.txt").write_text("operator file", encoding="utf-8")
        near_miss = self.data / "restore-notes"
        near_miss.mkdir()
        (near_miss / "keep.txt").write_text("not a temp directory", encoding="utf-8")

        cleanup_stale_backup_artifacts(self.data)

        self.assertTrue((keep_dir / "note.txt").is_file())
        self.assertTrue((near_miss / "keep.txt").is_file())


if __name__ == "__main__":
    unittest.main()
