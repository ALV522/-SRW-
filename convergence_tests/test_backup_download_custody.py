"""Issue #131: backup downloads serve bounded validated snapshots, not mutable names."""
from __future__ import annotations

import io
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.maintenance import cleanup_stale_backup_artifacts
from srw.runtime.backup_download import validated_download_snapshot, VerifiedBackupFileResponse
import srw.api.routes.system as system_routes_module


class BackupDownloadCustodyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-backup-download-contract-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.data = root / "data"
        self.data.mkdir()
        self.backups = self.data / "backups"
        app = create_v1_app(
            f"sqlite+pysqlite:///{(self.data/'srw_v1.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=root / "frontend",
        )
        self.client = self.enterContext(TestClient(app))
        self.name = self.client.post('/api/v1/system/backups').json()['filename']
        self.path = self.backups / self.name

    def _get(self, suffix=''):
        return self.client.get(f'/api/v1/system/backups/{self.name}', headers={"Range": suffix} if suffix else {})

    def _no_staging(self):
        self.assertEqual(list(self.backups.glob('.backup-download-*')), [])

    def test_valid_zip_is_delivered_and_no_staging_remains(self):
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text[:100] if response.status_code != 200 else '')
        self.assertEqual(response.content, self.path.read_bytes())
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        self.assertIn(self.name, response.headers['content-disposition'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn('data/srw_v1.db', archive.namelist())
        self._no_staging()

    def test_corrupted_published_archive_is_not_downloadable(self):
        self.path.write_bytes(b'not-a-zip\x00synthetic')
        response = self._get()
        self.assertGreaterEqual(response.status_code, 400)
        self.assertNotIn(b'not-a-zip', response.content)
        self._no_staging()

    def test_snapshot_is_independent_of_later_public_name_replacement(self):
        original = self.path.read_bytes()
        snapshot, private_dir = validated_download_snapshot(self.path, self.backups)
        try:
            # A replace/truncate after validation must not change the bytes that
            # will later be streamed from the private snapshot.
            self.path.write_bytes(b"replacement-is-not-a-backup")
            self.assertEqual(snapshot.read_bytes(), original)
        finally:
            shutil.rmtree(private_dir)
        self._no_staging()

    def test_range_valid_and_invalid_are_both_cleaned(self):
        original = self.path.read_bytes()
        partial = self._get('bytes=0-15')
        self.assertEqual(partial.status_code, 206, partial.text[:100] if partial.status_code != 206 else '')
        self.assertEqual(partial.content, original[:16])
        self._no_staging()
        invalid = self._get('bytes=99999999-999999999')
        self.assertEqual(invalid.status_code, 416)
        self._no_staging()
        malformed = self._get('not-a-range')
        self.assertEqual(malformed.status_code, 400)
        self._no_staging()

    def test_http_download_keeps_snapshot_when_public_path_is_replaced(self):
        original = self.path.read_bytes()
        make_snapshot = system_routes_module.validated_download_snapshot

        def replace_after_validation(*args):
            snapshot = make_snapshot(*args)
            self.path.write_bytes(b"modified-after-validation")
            return snapshot

        with patch.object(system_routes_module, "validated_download_snapshot", replace_after_validation):
            response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, original)
        self.assertNotEqual(response.content, self.path.read_bytes())
        self._no_staging()

    def test_symlink_swap_before_fd_open_is_rejected(self):
        private = self.backups / "private-target.zip"
        private.write_bytes(self.path.read_bytes())
        original_open = os.open
        triggered = False

        def replace_before_open(name, flags, *args, **kwargs):
            nonlocal triggered
            if not triggered and str(name) == str(self.path):
                triggered = True
                self.path.unlink()
                self.path.symlink_to(private)
            return original_open(name, flags, *args, **kwargs)

        try:
            with patch("srw.runtime.backup_download.os.open", replace_before_open):
                response = self._get()
            self.assertTrue(triggered)
            self.assertGreaterEqual(response.status_code, 400)
            self._no_staging()
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable under this OS account")

    def test_concurrent_download_refuses_second_snapshot_and_recovers_slot(self):
        entered = threading.Event()
        proceed = threading.Event()
        original = system_routes_module.validated_download_snapshot

        def blocked(*args):
            entered.set()
            if not proceed.wait(12):
                raise TimeoutError("test semaphore was not released")
            return original(*args)

        with patch.object(system_routes_module, "validated_download_snapshot", blocked):
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(self._get)
                try:
                    self.assertTrue(entered.wait(5), "first download never started")
                    concurrent = self._get()
                    self.assertEqual(concurrent.status_code, 409)
                finally:
                    proceed.set()
                self.assertEqual(first.result(timeout=15).status_code, 200)
        self.assertEqual(self._get().status_code, 200)
        self._no_staging()

    def test_response_cleans_and_releases_slot_when_asgi_send_aborts(self):
        snapshot, private_dir = validated_download_snapshot(self.path, self.backups)
        releases = []
        response = VerifiedBackupFileResponse(
            snapshot, private_dir, filename=self.name,
            release_slot=lambda: releases.append(True),
        )

        async def fail_send(_message):
            raise OSError("synthetic client disconnect")

        async def receive():
            return {"type": "http.disconnect"}

        scope = {"type": "http", "method": "GET", "path": "/", "headers": [],
                 "http_version": "1.1", "asgi": {"version": "3.0"}}
        with self.assertRaises(OSError):
            asyncio.run(response(scope, receive, fail_send))
        self.assertEqual(releases, [True])
        self._no_staging()

    def test_pathsend_extension_never_escapes_ephemeral_snapshot(self):
        # pathsend queues a *path* for the server; __call__ may return before
        # the server opens it. Our finally would then delete it too early.
        original = self.path.read_bytes()
        snapshot, private_dir = validated_download_snapshot(self.path, self.backups)
        messages = []
        releases = []
        response = VerifiedBackupFileResponse(
            snapshot, private_dir, filename=self.name,
            release_slot=lambda: releases.append(True),
        )

        async def send(message):
            messages.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {"type": "http", "method": "GET", "path": "/", "headers": [],
                 "http_version": "1.1", "asgi": {"version": "3.0"},
                 "extensions": {"http.response.pathsend": {}, "other": {}}}
        asyncio.run(response(scope, receive, send))
        self.assertFalse(any(m["type"] == "http.response.pathsend" for m in messages),
                         "pathsend cannot own a snapshot that is cleaned on return")
        self.assertEqual(b"".join(m.get("body", b"") for m in messages), original)
        self.assertEqual(releases, [True])
        self._no_staging()

    def test_oversized_zip_is_rejected_before_copying_or_serving(self):
        with patch("srw.runtime.backup_download.MAX_COMPRESSED_BYTES", 512):
            response = self._get()
        self.assertEqual(response.status_code, 409)
        self._no_staging()

    def test_abandoned_hidden_snapshot_is_reclaimed_without_user_file_loss(self):
        abandoned = self.backups / '.backup-download-orphan'
        abandoned.mkdir()
        (abandoned / 'snapshot.zip').write_bytes(b'synthetic')
        preserved = self.backups / 'operator.zip'
        preserved.write_bytes(b'operator content')
        cleanup_stale_backup_artifacts(self.data)
        self.assertFalse(abandoned.exists())
        self.assertEqual(preserved.read_bytes(), b'operator content')


if __name__ == '__main__':
    unittest.main()
