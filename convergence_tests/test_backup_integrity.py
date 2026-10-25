from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import warnings
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts import launch_alpha10 as launcher
from srw.modules.fullworkbench import create_backup
from srw.runtime.backup_truth import (
    BackupTruthError, BACKUP_MANIFEST_NAME, write_backup_archive,
    validate_backup_archive, extract_validated_backup,
)


class BackupRestoreIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.live = self.data / "srw_v1.db"
        self.backups = self.data / "backups"
        self.backups.mkdir()

    def make_db(self, path: Path, value: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Closing a sqlite3 transaction context does NOT close its connection.
        # Windows requires explicit close before unlink, rename and temp cleanup.
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
            db.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            db.execute("CREATE TABLE workload (value TEXT NOT NULL)")
            db.execute("INSERT INTO workload VALUES (?)", (value,))
            db.commit()

    def read_db(self, path: Path) -> str:
        with closing(sqlite3.connect(path)) as db:
            return db.execute("SELECT value FROM workload").fetchone()[0]

    def make_archive(self, value="new") -> Path:
        source = self.root / "source.db"
        self.make_db(source, value)
        inputs = self.root / "source-blobs" / "ab"
        inputs.mkdir(parents=True)
        (inputs / "abc").write_bytes(b"new resume bytes")
        zip_path = self.backups / "restore.zip"
        write_backup_archive(zip_path, source, self.root / "source-blobs")
        return zip_path

    def test_manifested_backup_roundtrip_and_exact_blobs(self):
        source = self.root / "local.db"
        self.make_db(source, "business-state")
        blobs = self.data / "blobs" / "aa"
        blobs.mkdir(parents=True)
        (blobs / "payload").write_bytes(b"private local content")
        archive = create_backup(self.data, source)
        truth = validate_backup_archive(archive, expected_schema="v1_0014")
        self.assertTrue(truth["manifest_present"])
        self.assertEqual(truth["blob_count"], 1)
        with tempfile.TemporaryDirectory() as td:
            result = extract_validated_backup(archive, td)
            self.assertEqual(result["integrity_level"], "manifest_sha256")
            self.assertEqual(self.read_db(Path(td) / "data" / "srw_v1.db"), "business-state")
            self.assertEqual((Path(td) / "data" / "blobs" / "aa" / "payload").read_bytes(), b"private local content")

    def test_content_addressed_source_backup_requires_filename_hash(self):
        source = self.root / "content-address-source.db"
        self.make_db(source, "correct")
        raw = b"synthetic applicant resume content"
        digest = hashlib.sha256(raw).hexdigest()
        root = self.root / "content-address-blobs"
        blob = root / digest[:2] / digest
        blob.parent.mkdir(parents=True)
        blob.write_bytes(raw)
        good = self.root / "good-content-address.zip"
        write_backup_archive(good, source, root)
        self.assertEqual(validate_backup_archive(good)["blob_count"], 1)
        # Simulate an interrupted legacy write/corruption before the next
        # backup scan. The backup must refuse to proclaim new damaged bytes
        # authoritative simply because it can record their own SHA.
        blob.write_bytes(b"incomplete source file")
        corrupt_backup = self.root / "corrupt-source-backup.zip"
        with self.assertRaisesRegex(BackupTruthError, "content.address|hash mismatch"):
            write_backup_archive(corrupt_backup, source, root)
        self.assertFalse(corrupt_backup.exists())

    def test_misplaced_modern_content_address_is_rejected_without_legacy_regression(self):
        source = self.root / "shard-source.db"
        self.make_db(source, "candidate evidence")
        raw = b"synthetic immutable content"
        digest = hashlib.sha256(raw).hexdigest()
        wrong_shard = "ff" if digest[:2] != "ff" else "ee"
        root = self.root / "misplaced-blobs"
        p = root / wrong_shard / digest
        p.parent.mkdir(parents=True)
        p.write_bytes(raw)
        with self.assertRaisesRegex(BackupTruthError, "shard mismatch"):
            write_backup_archive(self.root / "wrong-shard.zip", source, root)
        # Non-hash legacy names are not silently converted to a new format.
        p.rename(p.with_name("legacy-evidence-attachment"))
        legacy = self.root / "legacy-named-backup.zip"
        write_backup_archive(legacy, source, root)
        self.assertEqual(validate_backup_archive(legacy)["blob_count"], 1)

    def test_self_consistent_forged_manifest_still_rejects_wrong_content_address(self):
        source = self.root / "forged-source.db"
        self.make_db(source, "correct")
        valid_bytes = b"synthetic immutable Source"
        bad_bytes = b"synthetic forged Source"
        digest = hashlib.sha256(valid_bytes).hexdigest()
        source_root = self.root / "sha-blobs"
        canonical = source_root / digest[:2] / digest
        canonical.parent.mkdir(parents=True)
        canonical.write_bytes(valid_bytes)
        archive = self.root / "valid-content-address.zip"
        write_backup_archive(archive, source, source_root)
        with zipfile.ZipFile(archive) as z:
            original = {name: z.read(name) for name in z.namelist()}
        target = "data/blobs/" + digest[:2] + "/" + digest
        manifest = json.loads(original[BACKUP_MANIFEST_NAME])
        self.assertEqual(len(manifest["blobs"]), 1)
        manifest["blobs"][0]["sha256"] = hashlib.sha256(bad_bytes).hexdigest()
        manifest["blobs"][0]["size_bytes"] = len(bad_bytes)
        forged = self.root / "forged-content-address.zip"
        with zipfile.ZipFile(forged, "w", zipfile.ZIP_DEFLATED) as z:
            for name, body in original.items():
                if name == target:
                    body = bad_bytes
                elif name == BACKUP_MANIFEST_NAME:
                    body = json.dumps(manifest).encode("utf-8")
                z.writestr(name, body)
        # A match between member bytes and manifest digest alone is NOT enough.
        with self.assertRaisesRegex(BackupTruthError, "content.address|hash mismatch"):
            validate_backup_archive(forged)

    def test_modified_member_rejected_even_if_zip_is_valid(self):
        archive = self.make_archive()
        with zipfile.ZipFile(archive) as zip_in:
            files = [(info.filename, zip_in.read(info)) for info in zip_in.infolist()]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_out:
            for name, body in files:
                zip_out.writestr(name, b"tampered bytes" if name.startswith("data/blobs/") else body)
        with self.assertRaisesRegex(BackupTruthError, "digest mismatch"):
            validate_backup_archive(archive)

    def test_legacy_backups_supported_but_unexpected_paths_rejected(self):
        db = self.root / "legacy.db"
        self.make_db(db, "old-version")
        legacy = self.backups / "legacy.zip"
        with zipfile.ZipFile(legacy, "w") as z:
            z.write(db, "data/srw_v1.db")
            # A pre-manifest archive can include historically named sources.
            z.writestr("data/blobs/ab/legacy-evidence", b"synthetic old source")
        self.assertEqual(validate_backup_archive(legacy)["integrity_level"], "legacy_unmanifested")
        with zipfile.ZipFile(legacy, "a") as z:
            z.writestr("data/private.json", b"not allowed")
        with self.assertRaisesRegex(BackupTruthError, "unexpected member"):
            validate_backup_archive(legacy)

    def test_duplicate_zip_entries_are_rejected(self):
        archive = self.make_archive()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "a") as z:
                z.writestr("data/srw_v1.db", b"duplicate")
        with self.assertRaisesRegex(BackupTruthError, "duplicate ZIP"):
            validate_backup_archive(archive)

    def test_failed_pending_restore_keeps_live_database_and_marker(self):
        self.make_db(self.live, "original")
        archive = self.make_archive()
        marker = self.data / "pending_restore.json"
        marker.write_text(json.dumps({
            "backup": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }))
        with zipfile.ZipFile(archive, "a") as z:
            z.writestr("data/unrelated.txt", "unsafe")
        # Keep outer ZIP hash current; internal allowlist still must reject member.
        marker.write_text(json.dumps({
            "backup": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }))
        with patch.object(launcher, "DATA", self.data), patch.object(launcher, "DB", self.live):
            with self.assertRaises(BackupTruthError):
                launcher.apply_pending_restore()
        self.assertEqual(self.read_db(self.live), "original")
        self.assertTrue(marker.exists())

    def test_successful_restore_replaces_state_and_preserves_pre_restore_snapshot(self):
        self.make_db(self.live, "before")
        old_blobs = self.data / "blobs" / "old"
        old_blobs.mkdir(parents=True)
        (old_blobs / "original").write_bytes(b"old")
        archive = self.make_archive("after")
        marker = self.data / "pending_restore.json"
        marker.write_text(json.dumps({
            "backup": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "schema_revision": "v1_0014",
        }))
        with patch.object(launcher, "DATA", self.data), patch.object(launcher, "DB", self.live):
            restored = launcher.apply_pending_restore()
        self.assertEqual(restored, "restore.zip")
        self.assertEqual(self.read_db(self.live), "after")
        self.assertEqual((self.data / "blobs" / "ab" / "abc").read_bytes(), b"new resume bytes")
        self.assertFalse((self.data / "blobs" / "old").exists())
        self.assertFalse(marker.exists())
        pre = list(self.backups.glob("pre_restore-*.zip"))
        self.assertEqual(len(pre), 1)
        self.assertTrue(validate_backup_archive(pre[0])["manifest_present"])
        with tempfile.TemporaryDirectory() as td:
            extract_validated_backup(pre[0], td)
            self.assertEqual(self.read_db(Path(td) / "data" / "srw_v1.db"), "before")


if __name__ == "__main__":
    unittest.main()
