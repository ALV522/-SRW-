"""Backup creation must be atomic: an interrupted backup may never look usable.

The product risk this pins: ``write_backup_archive`` opens the final ``*.zip`` path
directly, so a crash or a failing blob read in the middle of ``ZipFile.write``
leaves a truncated archive under a normal backup name. ``GET /api/v1/system/backups``
lists every ``*.zip`` by name and size without validating, so that half-product is
offered to the operator as a usable backup and only fails later, at the moment they
actually need to restore.

These tests are deterministic: the interruption is injected, not timed. They are
written to fail against the current implementation (RED) and to pass once publishing
is staged and atomic, which is Track A's implementation to make.

Contract these tests pin (agreed with Track A):
* staging names must never end in ``.zip`` - ``Path.glob("*.zip")`` matches dotfiles,
  so ``.tmp-x.zip`` is listed just like a real backup; a ``.partial`` suffix is not;
* the backup list stays a cheap naming filter, not an unbounded per-request SHA scan,
  so a legally named but truncated archive may still appear - it must be refused at
  scheduling time instead;
* a failed attempt never pollutes ``pending_restore.json`` and never overwrites a
  previously valid archive.
"""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from knowledge_fixture import create_minimal_knowledge_tree
from starlette.testclient import TestClient

from srw.api.app import create_v1_app
from srw.modules.fullworkbench import create_backup
from srw.runtime.backup_truth import validate_backup_archive


class BackupAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        # Windows keeps a handle on the SQLite files until the connection is
        # collected, so scratch cleanup must not turn a passing test into an error.
        self.tmp = tempfile.TemporaryDirectory(
            prefix="srw-backup-atomicity-", ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.backups = self.data / "backups"
        self.backups.mkdir(parents=True)
        self.blobs = self.data / "blobs"
        # Content-addressed names are validated on backup (modern 64-hex SHA), so the
        # fixture must be a real digest of its bytes rather than a plausible-looking one.
        payload = b"synthetic source bytes"
        digest = hashlib.sha256(payload).hexdigest()
        (self.blobs / digest[:2]).mkdir(parents=True)
        (self.blobs / digest[:2] / digest).write_bytes(payload)
        self.db = self.data / "srw_v1.db"
        con = sqlite3.connect(self.db)
        try:
            # A real backup is validated with PRAGMA quick_check plus a schema read,
            # so the fixture must carry the same metadata table a live Core writes.
            con.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
            con.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            con.execute("CREATE TABLE marker (id TEXT PRIMARY KEY, note TEXT)")
            con.execute("INSERT INTO marker VALUES ('a', 'lives in the backup')")
            con.commit()
        finally:
            con.close()

    def archives(self) -> list[str]:
        return sorted(path.name for path in self.backups.glob("*.zip"))

    def interrupting_write(self, *, fail_on_call: int = 2):
        """Raise on the Nth ZipFile.write, after the archive file already exists."""
        real_write = zipfile.ZipFile.write
        state = {"calls": 0}

        def fail_after_first_entry(archive, *args, **kwargs):
            state["calls"] += 1
            if state["calls"] >= fail_on_call:
                raise OSError("simulated interruption while writing the archive")
            return real_write(archive, *args, **kwargs)

        return mock.patch.object(zipfile.ZipFile, "write", fail_after_first_entry)

    # ------------------------------------------------------------------ tests

    def test_interrupted_backup_publishes_no_archive_and_keeps_the_old_one(self) -> None:
        valid = create_backup(self.data, self.db)
        original_bytes = valid.read_bytes()
        before = self.archives()

        with self.interrupting_write():
            with self.assertRaises(OSError):
                create_backup(self.data, self.db)

        self.assertEqual(self.archives(), before,
                         "an interrupted backup must not publish a *.zip under a normal name")
        self.assertEqual(valid.read_bytes(), original_bytes,
                         "the existing backup bytes must not be touched")
        self.assertTrue(validate_backup_archive(valid)["manifest_present"])

    def test_half_product_is_not_listed_and_cannot_be_scheduled(self) -> None:
        # This case drives the real app, so the database must be one the migrations
        # created - a hand-written two-table file would fail at the first query.
        app_db = self.data / "app.db"
        app = create_v1_app(
            f"sqlite+pysqlite:///{app_db.as_posix()}",
            data_dir=self.data,
            knowledge_dir=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
            frontend_dist=Path(__file__).resolve().parents[1] / "frontend" / "dist",
        )
        with TestClient(app) as client:
            valid = create_backup(self.data, app_db)
            positive = client.post(f"/api/v1/system/backups/{valid.name}/restore")
            self.assertEqual(positive.status_code, 200, positive.text)
            client.post("/api/v1/system/restore/cancel")

            # A crash can leave staging bytes or a truncated archive. Staging must be
            # invisible to the listing (naming filter); the truncated one may appear
            # but must be rejected when scheduling, which is asserted below.
            (self.backups / ".srw-staging-7f3a.partial").write_bytes(b"PK\x03\x04partial")
            (self.backups / ".tmp-interrupted.zip").write_bytes(b"PK\x03\x04partial")
            (self.backups / "srw-backup-20260101-000000-000000.zip").write_bytes(b"PK\x03\x04partial")

            listed = client.get("/api/v1/system/backups").json()["backups"]
            names = {row["filename"] for row in listed}
            self.assertNotIn(".srw-staging-7f3a.partial", names,
                             "a .partial staging file must never be listed")
            self.assertNotIn(".tmp-interrupted.zip", names,
                             "a dot-prefixed .zip is still matched by glob and must be filtered")
            self.assertIn(valid.name, names)

            half = client.post(
                "/api/v1/system/backups/srw-backup-20260101-000000-000000.zip/restore")
            self.assertGreaterEqual(half.status_code, 400,
                                    "a truncated archive must be refused at scheduling time")
            marker = self.data / "pending_restore.json"
            self.assertFalse(marker.exists(), "a refused backup must not leave a pending marker")


if __name__ == "__main__":
    unittest.main()
