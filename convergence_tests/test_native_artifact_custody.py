"""Synthetic-only external Native artifact custody tests."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

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

    def test_path_open_race_cannot_hash_another_file_under_a_valid_name(self):
        # The selected primary is incorrect but has the same length as the pin.
        # Simulate a path replacement between the metadata precheck and open:
        # a file handle for the intact secondary arrives instead. Old code
        # hashed that handle and then re-statted the unchanged, corrupt primary,
        # reporting both copies as valid. The verified descriptor must be the
        # same file object that the path check selected.
        self.primary.write_bytes(bytes([self.data[0] ^ 0x01]) + self.data[1:])
        real_fd_open = os.open
        real_path_open = Path.open

        def substituted_fd(path, flags, *args, **kwargs):
            selected = self.secondary if Path(path) == self.primary else path
            return real_fd_open(selected, flags, *args, **kwargs)

        def substituted_path_open(path, mode="r", *args, **kwargs):
            selected = self.secondary if path == self.primary else path
            return real_path_open(selected, mode, *args, **kwargs)

        # Both implementations receive the identical wrong-but-pinned bytes
        # through the opened handle while the original path remains corrupt.
        # Old Path.open implementation wrongly reports PASS; new code fails
        # the descriptor-vs-path identity comparison before digesting anything.
        with patch("scripts.audit_native_artifact_custody.os.open", side_effect=substituted_fd), \
             patch.object(Path, "open", substituted_path_open):
            with self.assertRaisesRegex(CustodyError, "archive file identity changed before reading"):
                self.check()

    def test_open_race_or_antivirus_lock_is_a_safe_custody_denial(self):
        # The CLI already catches OSError, but direct library callers must not
        # see a path-bearing OS error or a traceback on a raced open. No private
        # local archive name belongs in a rejection reason.
        for error in (errno.EACCES, errno.ELOOP):
            with self.subTest(errno=error):
                with patch("scripts.audit_native_artifact_custody.os.open",
                           side_effect=OSError(error, "synthetic host failure", str(self.primary))):
                    with self.assertRaises(CustodyError) as denial:
                        self.check()
                self.assertEqual(str(denial.exception),
                                 "archive could not be opened for verification")
                self.assertNotIn(str(self.root), str(denial.exception))
                self.assertTrue(self.primary.is_file())
                self.assertTrue(self.secondary.is_file())

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
