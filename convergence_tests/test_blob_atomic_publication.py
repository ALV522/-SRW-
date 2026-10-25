"""Content-addressed Source files must never become visible partially written.

Uses only synthetic byte strings, isolated filesystem roots and deterministic
publication hooks. The actual backup writer (not a mocked ZIP) is exercised.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from srw.modules.fullworkbench import BlobStore
from srw.runtime.backup_truth import validate_backup_archive, write_backup_archive


class BlobAtomicPublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="srw-blob-atomic-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.blobs = self.root / "data" / "blobs"
        self.store = BlobStore(self.blobs)
        self.raw = b"synthetic resume " * 4096
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.dest = self.blobs / self.digest[:2] / self.digest
        self.db = self.root / "snapshot.db"
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
            connection.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            connection.commit()
        finally:
            # sqlite3's transaction context manager does not close the handle;
            # Windows must release it before TemporaryDirectory.cleanup().
            connection.close()

    def test_backup_during_publication_cannot_observe_half_blob_or_staging(self):
        import os
        real_replace = os.replace
        observed = []

        def at_atomic_publish(source, target):
            self.assertEqual(Path(target), self.dest)
            self.assertFalse(self.dest.exists(), "final name exposed before data completed")
            self.assertEqual(Path(source).read_bytes(), self.raw)
            self.assertFalse(list(self.blobs.rglob("*.tmp")), "backup must not enumerate staging files")
            archive = self.root / "during-publication.zip"
            write_backup_archive(archive, self.db, self.blobs)
            observed.append(validate_backup_archive(archive)["blob_count"])
            return real_replace(source, target)

        with patch("srw.modules.fullworkbench.os.replace", side_effect=at_atomic_publish):
            self.assertEqual(self.store.put(self.raw), self.digest)
        self.assertEqual(observed, [0])
        self.assertEqual(self.dest.read_bytes(), self.raw)
        archive = self.root / "after-publication.zip"
        write_backup_archive(archive, self.db, self.blobs)
        self.assertEqual(validate_backup_archive(archive)["blob_count"], 1)

    def test_failed_publish_never_creates_truncated_final_name(self):
        with patch("srw.modules.fullworkbench.os.replace", side_effect=OSError("synthetic rename failure")):
            with self.assertRaisesRegex(OSError, "synthetic rename failure"):
                self.store.put(self.raw)
        self.assertFalse(self.dest.exists())
        # Failed attempt should not leave a private resume copy in staging.
        staging = self.blobs.parent / ".blobs-staging"
        self.assertFalse(list(staging.glob("*")) if staging.exists() else [])

    def test_existing_corrupt_content_address_is_never_reported_as_saved(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self.dest.write_bytes(b"truncated legacy partial")
        with self.assertRaisesRegex(OSError, "corrupt|mismatch"):
            self.store.put(self.raw)
        self.assertEqual(self.dest.read_bytes(), b"truncated legacy partial")

    def test_read_rejects_corrupt_existing_source_before_downstream_provider(self):
        # OCR/ASR/Evidence read through BlobStore.get. A tampered Source must
        # never be returned as if it still matched the immutable digest.
        self.assertEqual(self.store.put(self.raw), self.digest)
        self.assertEqual(self.store.get(self.digest), self.raw)
        self.dest.write_bytes(b"tampered synthetic source")
        with self.assertRaisesRegex(OSError, "corrupt|mismatch"):
            self.store.get(self.digest)
        self.assertEqual(self.dest.read_bytes(), b"tampered synthetic source")

    def test_legacy_named_blob_read_remains_compatible_but_unsafe_names_fail(self):
        legacy = self.blobs / "ab" / "abc"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b"synthetic legacy blob content")
        self.assertEqual(self.store.get("abc"), b"synthetic legacy blob content")
        with self.assertRaisesRegex(OSError, "invalid"):
            self.store.get("../outside")

    def test_duplicate_put_is_idempotent_and_matches_content_hash(self):
        self.assertEqual(self.store.put(self.raw), self.digest)
        self.assertEqual(self.store.put(self.raw), self.digest)
        self.assertEqual(self.store.get(self.digest), self.raw)
        self.assertEqual([x for x in self.blobs.rglob("*") if x.is_file()], [self.dest])

    def test_concurrent_same_digest_has_one_publication_and_no_overlapping_replace(self):
        # Windows rename/open sharing violations surfaced when identical
        # uploads ran concurrently. Hold the first publication at the final
        # rename while another put begins. A per-digest lock must prevent
        # the second writer from racing the check / rename / hash read.
        first_entered = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        original_replace = os.replace
        published = []

        def hold_replace(source, target):
            published.append(Path(target))
            first_entered.set()
            if not release_first.wait(2):
                raise AssertionError("synthetic publisher stalled")
            return original_replace(source, target)

        def concurrent_put():
            second_started.set()
            return self.store.put(self.raw)

        with patch("srw.modules.fullworkbench.os.replace", side_effect=hold_replace):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.store.put, self.raw)
                self.assertTrue(first_entered.wait(2))
                second = pool.submit(concurrent_put)
                self.assertTrue(second_started.wait(2))
                # Old implementation reaches a second os.replace while the
                # first is blocked; lock-striped code cannot enter it.
                time.sleep(0.10)
                release_first.set()
                self.assertEqual(first.result(timeout=3), self.digest)
                self.assertEqual(second.result(timeout=3), self.digest)
        self.assertEqual(published, [self.dest])
        self.assertEqual(self.dest.read_bytes(), self.raw)

    def test_same_content_concurrent_puts_publish_only_complete_bytes(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(self.store.put, [self.raw] * 6))
        self.assertEqual(results, [self.digest] * 6)
        self.assertEqual(self.dest.read_bytes(), self.raw)
        self.assertEqual([x for x in self.blobs.rglob("*") if x.is_file()], [self.dest])


if __name__ == "__main__":
    unittest.main()
