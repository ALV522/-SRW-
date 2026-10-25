"""All Native custody verifier tests use tiny synthetic ZIPs, never production data."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.audit_native_input_custody import CustodyError, audit_two_copies


class NativeInputCustodyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="srw-native-custody-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("PRODUCTION_RUNTIME.sha256", "a" * 64 + "  python.exe\n")
            z.writestr("PRODUCTION_KNOWLEDGE.sha256", "b" * 64 + "  taxonomy/knowledge.db\n")
        self.raw = stream.getvalue()
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.a = self.root / "one.zip"
        self.b = self.root / "two.zip"
        self.a.write_bytes(self.raw)
        self.b.write_bytes(self.raw)

    def verify(self, a=None, b=None):
        return audit_two_copies(a or self.a, b or self.b, expected_digest=self.sha,
                                expected_bytes=len(self.raw), runtime_count=1, knowledge_count=1)

    def test_two_distinct_exact_copies_count_but_do_not_prove_failure_domain(self):
        data = self.verify()
        self.assertEqual(data["copy_count_verified"], 2)
        self.assertFalse(data["different_physical_failure_domains_verified"])
        self.assertFalse(data["independent_upstream_rebuild_verified"])
        self.assertFalse(data["windows_gui_accepted"])
        self.assertNotIn(str(self.root), json.dumps(data))

    def test_same_file_and_hardlink_rejected(self):
        with self.assertRaisesRegex(CustodyError, "SAME_FILE"):
            self.verify(self.a, self.a)
        hardlink = self.root / "linked.zip"
        hardlink.hardlink_to(self.a)
        with self.assertRaisesRegex(CustodyError, "SAME_FILE"):
            self.verify(self.a, hardlink)

    def test_replaced_bytes_and_size_fail_closed(self):
        self.b.write_bytes(self.raw + b"corrupt")
        with self.assertRaisesRegex(CustodyError, "BYTE_SIZE_MISMATCH"):
            self.verify()
        self.b.write_bytes(self.raw[:-1] + b"0")
        with self.assertRaisesRegex(CustodyError, "SHA256_MISMATCH"):
            self.verify()

    def test_symlink_fails_if_platform_supports_it(self):
        link = self.root / "alias.zip"
        try:
            link.symlink_to(self.a)
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit symlink creation")
        with self.assertRaisesRegex(CustodyError, "SYMLINK"):
            self.verify(self.a, link)

    def test_missing_manifest_and_incorrect_inventory_fail(self):
        with self.assertRaisesRegex(CustodyError, "INVENTORY_COUNT"):
            audit_two_copies(self.a, self.b, expected_digest=self.sha, expected_bytes=len(self.raw),
                             runtime_count=2, knowledge_count=1)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("unrelated.txt", "synthetic only")
        bad = stream.getvalue()
        self.a.write_bytes(bad)
        self.b.write_bytes(bad)
        with self.assertRaisesRegex(CustodyError, "MANIFEST_MISSING"):
            audit_two_copies(self.a, self.b, expected_digest=hashlib.sha256(bad).hexdigest(),
                             expected_bytes=len(bad), runtime_count=1, knowledge_count=1)

    def test_undisclosed_absolute_paths_do_not_escape_in_errors(self):
        self.a.unlink()
        with self.assertRaises(CustodyError) as error:
            self.verify()
        self.assertNotIn(str(self.root), str(error.exception))


if __name__ == "__main__":
    unittest.main()
