from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.audit_legacy_archives import ArchiveAuditError, audit_catalog, inspect_archive


class LegacyArchiveAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _zip(self, name="legacy.zip", files=None):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for member, data in files or [("README.md", b"synthetic"), ("knowledge/active/taxonomy/knowledge.db", b"fixture")]:
                z.writestr(member, data)
        return path

    def test_readonly_inventory_never_misstates_publication_safety(self):
        path = self._zip()
        report = inspect_archive(path)
        self.assertEqual(report["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(report["database_files"], 1)
        self.assertFalse(report["safe_to_publish"])
        self.assertEqual(report["security_classification"], "UNREVIEWED_CONTENT")

    def test_zip_slip_blocks_before_extraction(self):
        for member in ("../private.txt", "/root/private", "C:/private", "data\\evil.db", "CON.txt"):
            with self.subTest(member=member):
                path = self._zip(files=[(member, b"synthetic")])
                with self.assertRaises(ArchiveAuditError):
                    inspect_archive(path)

    def test_case_collision_blocks(self):
        path = self._zip(files=[("README.md", b"1"), ("readme.MD", b"2")])
        with self.assertRaises(ArchiveAuditError):
            inspect_archive(path)

    def test_manifest_does_not_trust_same_filename_with_other_bytes(self):
        path = self._zip()
        catalog = self.root / "catalog.json"
        entry = {"archive_id": "synthetic", "filename": "legacy.zip",
                 "sha256": "0" * 64, "bytes": path.stat().st_size}
        catalog.write_text(json.dumps({"schema": "srw.legacy-archive-catalog.v1",
                                       "archives": [entry] * 4}), encoding="utf-8")
        with self.assertRaisesRegex(ArchiveAuditError, "checksum"):
            audit_catalog(catalog, self.root)


if __name__ == "__main__":
    unittest.main()
