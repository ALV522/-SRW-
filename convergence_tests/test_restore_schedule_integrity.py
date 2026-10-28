"""Scheduling must enforce the same backup truth as startup restoration."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.backup_truth import BACKUP_MANIFEST_NAME

ROOT = Path(__file__).resolve().parents[1]


class RestoreScheduleIntegrityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-restore-schedule-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.data = root / "data"
        self.data.mkdir()
        self.client = self.enterContext(TestClient(create_v1_app(
            f"sqlite+pysqlite:///{(self.data / 'srw_v1.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )))
        response = self.client.post("/api/v1/projects", json={
            "title": "Synthetic retained project", "role_title": "Synthetic analyst",
            "brief_summary": "Disposable restore integrity test",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.projects_before = self.client.get("/api/v1/projects").json()
        blob = self.data / "blobs" / "ab" / "synthetic"
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"synthetic evidence bytes")
        response = self.client.post("/api/v1/system/backups")
        self.assertEqual(response.status_code, 200, response.text)
        self.archive = self.data / "backups" / response.json()["filename"]
        self.marker = self.data / "pending_restore.json"

    def schedule(self, archive=None):
        path = archive or self.archive
        return self.client.post(f"/api/v1/system/backups/{path.name}/restore")

    def corrupt_archive(self, kind):
        with zipfile.ZipFile(self.archive) as source:
            members = {info.filename: source.read(info) for info in source.infolist()}
        if kind == "blob":
            members["data/blobs/ab/synthetic"] = b"changed evidence bytes"
        elif kind == "missing_blob":
            del members["data/blobs/ab/synthetic"]
        elif kind == "manifest":
            members[BACKUP_MANIFEST_NAME] = b"not JSON"
        elif kind == "extra":
            members["data/unexpected.txt"] = b"unlisted bytes"
        with zipfile.ZipFile(self.archive, "w") as target:
            for name, raw in members.items():
                target.writestr(name, raw)

    def test_invalid_backup_cannot_replace_an_existing_restore_plan(self):
        for kind in ("blob", "missing_blob", "manifest", "extra"):
            with self.subTest(kind=kind):
                original = self.archive.read_bytes()
                self.marker.write_text('{"backup":"previous-verified.zip","keep":true}')
                marker_before = self.marker.read_bytes()
                try:
                    self.corrupt_archive(kind)
                    response = self.schedule()
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertEqual(response.json()["error"]["code"], "invariant_conflict")
                    self.assertEqual(self.marker.read_bytes(), marker_before)
                    self.assertEqual(self.client.get("/api/v1/projects").json(), self.projects_before)
                finally:
                    self.archive.write_bytes(original)

    def test_bad_backup_does_not_create_a_restore_marker(self):
        self.corrupt_archive("blob")
        response = self.schedule()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertFalse(self.marker.exists())

    def test_valid_backup_schedules_exact_bytes_and_cancel_preserves_live_state(self):
        response = self.schedule()
        self.assertEqual(response.status_code, 200, response.text)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(response.json(), {
            "scheduled": True, "filename": self.archive.name, "sha256": digest,
            "schema_revision": "v1_0014", "restart_required": True,
        })
        self.assertEqual(json.loads(self.marker.read_text()), {
            "backup": self.archive.name, "sha256": digest, "schema_revision": "v1_0014",
        })
        cancelled = self.client.post("/api/v1/system/restore/cancel")
        self.assertEqual(cancelled.json(), {"scheduled": False})
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.client.get("/api/v1/projects").json(), self.projects_before)

    def test_cleanup_only_journal_blocks_new_restore_scheduling_without_mutation(self):
        # A live Core may have successfully reopened with journal-owned AV debris.
        # It must not schedule another restore using the same reserved old paths.
        journal = self.data / ".srw-restore-journal.json"
        journal.write_text('{"schema":"srw.restore-journal.v1",'
                           '"phase":"FINALIZED_CLEANUP_PENDING"}', encoding="utf-8")
        for with_marker in (False, True):
            with self.subTest(existing_plan=with_marker):
                if with_marker:
                    self.marker.write_bytes(b"previous synthetic plan")
                original = self.marker.read_bytes() if self.marker.exists() else None
                response = self.schedule()
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["error"]["code"], "invariant_conflict")
                self.assertEqual(self.marker.read_bytes() if self.marker.exists() else None, original)
                self.assertEqual(self.client.get("/api/v1/projects").json(), self.projects_before)
                self.marker.unlink(missing_ok=True)

    def test_legacy_database_only_backup_remains_schedulable(self):
        legacy = self.archive.parent / "legacy.zip"
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(legacy, "w") as target:
            target.writestr("data/srw_v1.db", source.read("data/srw_v1.db"))
        response = self.schedule(legacy)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["filename"], "legacy.zip")

    def test_missing_backup_still_returns_not_found(self):
        response = self.schedule(self.archive.parent / "absent.zip")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.marker.exists())

    def test_incompatible_schema_is_rejected_before_marker_write(self):
        database = self.data / "schema-probe.db"
        with zipfile.ZipFile(self.archive) as source:
            original = source.read("data/srw_v1.db")
        legacy = self.archive.parent / "incompatible.zip"
        for revision in ("v1_0015", "v1_0000", "invalid"):
            with self.subTest(revision=revision):
                database.write_bytes(original)
                connection = sqlite3.connect(database)
                try:
                    connection.execute("UPDATE v1_schema_meta SET schema_revision=?", (revision,))
                    connection.commit()
                finally:
                    connection.close()
                with zipfile.ZipFile(legacy, "w") as target:
                    target.write(database, "data/srw_v1.db")
                response = self.schedule(legacy)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertIn("schema is not compatible", response.json()["detail"])
                self.assertFalse(self.marker.exists())
