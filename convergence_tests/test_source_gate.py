import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_source_integrity, check_release_truth, resource_probe


class SourceIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'module.py').write_bytes(b'current code\n')
        old = hashlib.sha256(b'old code\n').hexdigest()
        self.line = hashlib.sha256(b'current code\n').hexdigest() + '  module.py\n'
        (self.root / 'SOURCE_RECOVERY_MANIFEST.sha256').write_text(old + '  module.py\n')
        self.manifest = self.root / 'SOURCE_MANIFEST.sha256'
        self.manifest.write_text(self.line)

    def test_current_manifest_accepts_reviewed_change_without_rewriting_history(self):
        self.assertEqual(check_source_integrity.validate(self.root), [])

    def test_changed_source_is_rejected(self):
        (self.root / 'module.py').write_bytes(b'tampered')
        self.assertTrue(check_source_integrity.validate(self.root))

    def test_missing_source_is_rejected(self):
        (self.root / 'module.py').unlink()
        self.assertTrue(check_source_integrity.validate(self.root))

    def test_dropping_historical_source_from_manifest_is_rejected(self):
        self.manifest.write_text('')
        self.assertTrue(check_source_integrity.validate(self.root))

    def test_duplicate_or_unsafe_paths_are_rejected(self):
        for text in (self.line * 2, '0' * 64 + '  ../outside.py\n'):
            with self.subTest(text=text):
                self.manifest.write_text(text)
                self.assertTrue(check_source_integrity.validate(self.root))

    def test_tracked_file_missing_from_manifest_is_rejected(self):
        self.assertTrue(check_source_integrity.validate(self.root, {'module.py', 'new_module.py'}))


class ReleaseBindingTest(unittest.TestCase):
    def test_verification_inventory_version_mismatch_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for relative in ('VERSION', 'BUILD_INFO.json', 'backend/srw/release_state.json',
                             'PORTABLE_MANIFEST.json', 'VERIFICATION_TRUTH.json',
                             'VERIFICATION_INVENTORY.json', 'WINDOWS_NATIVE_HOST_STATUS.json',
                             'backend/srw/runtime/db/schema.py'):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((root / relative).read_bytes())
            path = target / 'VERIFICATION_INVENTORY.json'
            inventory = json.loads(path.read_text())
            inventory['release'] = 'wrong-release'
            path.write_text(json.dumps(inventory))
            with patch.object(check_release_truth, 'ROOT', target):
                self.assertTrue(check_release_truth.validate())


class ResourceProbeTest(unittest.TestCase):
    def test_sqlite_open_file_detected_without_proc_and_disappears_on_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'held.sqlite3'
            conn = sqlite3.connect(path)
            try:
                conn.execute('CREATE TABLE sample (id INTEGER)')
                conn.commit()
                with patch('scripts.resource_probe.Path') as probe_path:
                    probe_path.return_value.is_dir.return_value = False
                    held = resource_probe.resource_snapshot()['sqlite_open_files']
                self.assertIn(os.path.normcase(str(path.resolve())),
                              [os.path.normcase(p) for p in held])
            finally:
                conn.close()
            self.assertNotIn(os.path.normcase(str(path.resolve())),
                             [os.path.normcase(p) for p in resource_probe.resource_snapshot()['sqlite_open_files']])
