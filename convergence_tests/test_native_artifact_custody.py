"""Synthetic-only external Native artifact custody tests."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.audit_native_artifact_custody import CustodyError, audit_custody, main


class NativeArtifactCustodyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-artifact-custody-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.primary = self.root / "copy-one.zip"
        self.secondary = self.root / "copy-two.zip"
        with zipfile.ZipFile(self.primary, "w") as z:
            z.writestr("SYNTHETIC.txt", "no private data")
        self.secondary.write_bytes(self.primary.read_bytes())
        self.data = self.primary.read_bytes()
        self.sha = hashlib.sha256(self.data).hexdigest()

    def check(self, first=None, second=None):
        return audit_custody(first or self.primary, second or self.secondary,
                             expected_digest=self.sha, expected_size=len(self.data))

    def test_two_distinct_identical_copies_pass_without_recovery_claim(self):
        report = self.check()
        self.assertEqual(report["copies_verified"], 2)
        self.assertEqual(report["status"], "TWO_PINNED_COPIES_VERIFIED_RECOVERY_NOT_PROVEN")
        self.assertFalse(report["independent_failure_domains_verified"])
        self.assertFalse(report["clean_room_rebuild_verified"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_reject_modified_or_missing_copy(self):
        self.secondary.write_bytes(self.data + b"modified")
        with self.assertRaises(CustodyError):
            self.check()
        self.secondary.unlink()
        with self.assertRaises(CustodyError):
            self.check()

    def test_reject_same_file_or_hardlink_alias(self):
        with self.assertRaises(CustodyError):
            self.check(self.primary, self.primary)
        self.secondary.unlink()
        os.link(self.primary, self.secondary)
        with self.assertRaises(CustodyError):
            self.check()

    def test_reject_symlink_alias_when_supported(self):
        self.secondary.unlink()
        try:
            self.secondary.symlink_to(self.primary)
        except (OSError, NotImplementedError):
            self.skipTest("symlink privilege unavailable")
        with self.assertRaises(CustodyError):
            self.check()

    def test_production_cli_no_caller_supplied_digest_override(self):
        evidence = self.root / "safe-report.json"
        self.assertEqual(main(["--primary", str(self.primary),
                               "--secondary", str(self.secondary),
                               "--evidence", str(evidence)]), 2)
        self.assertFalse(evidence.exists())
        with self.assertRaises(SystemExit):
            main(["--primary", str(self.primary), "--secondary", str(self.secondary),
                  "--evidence", str(evidence), "--expected-sha256", self.sha])


if __name__ == "__main__":
    unittest.main()
