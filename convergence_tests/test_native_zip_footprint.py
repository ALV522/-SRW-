"""Synthetic, offline tests for the read-only Native ZIP footprint reporter."""
from __future__ import annotations

import hashlib
import stat
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from scripts.report_native_zip_footprint import compare, profile_zip


class NativeZipFootprintTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-footprint-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def make_zip(self, path: Path, *, extra: bytes = b"") -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("runtime/python.exe", b"python" * 150)
            z.writestr("knowledge/active/gold/knowledge.db", b"synthetic" * 90)
            z.writestr("windows-host/SmartRecruitmentWorkbench.exe", b"host" * 30)
            z.writestr("backend/srw/api/app.py", b"source" * 30 + extra)
            z.writestr("SOURCE_MANIFEST.sha256", b"synthetic manifest")

    def test_read_only_size_and_categories(self):
        path = self.root / "candidate.zip"
        self.make_zip(path)
        before = path.read_bytes()
        report = profile_zip(path)
        self.assertEqual(path.read_bytes(), before, "no mutation or extraction")
        self.assertEqual(report["zip_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(report["file_count"], 5)
        self.assertEqual(report["groups"]["runtime"]["files"], 1)
        self.assertEqual(report["groups"]["knowledge"]["files"], 1)
        self.assertEqual(report["groups"]["windows-host"]["files"], 1)
        self.assertEqual(report["groups"]["source"]["files"], 1)
        self.assertEqual(report["groups"]["governance"]["files"], 1)
        self.assertEqual(report["groups"]["other"]["files"], 0)
        self.assertEqual(report["archive_bytes"], path.stat().st_size)
        self.assertEqual(report["archive_bytes"],
                         report["payload_compressed_bytes"] + report["zip_container_overhead_bytes"])
        self.assertEqual(report["uncompressed_bytes"],
                         sum(x["uncompressed_bytes"] for x in report["groups"].values()))
        self.assertFalse(report["integrity_verified"])
        self.assertFalse(report["payload_extracted"])
        self.assertNotIn("python.exe", str(report), "no member names in summary")

    def test_compare_and_duplicate_rejection(self):
        old, new = self.root / "old.zip", self.root / "new.zip"
        self.make_zip(old)
        self.make_zip(new, extra=b"new source data" * 20)
        first, second = profile_zip(old), profile_zip(new)
        delta = compare(first, second)
        self.assertEqual(delta["after_minus_before"]["archive_bytes"],
                         new.stat().st_size - old.stat().st_size)
        self.assertEqual(delta["after_minus_before"]["file_count"], 0)
        self.assertGreater(delta["after_minus_before"]["uncompressed_bytes"], 0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(new, "a") as z:
                z.writestr("runtime/python.exe", b"duplicate")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            profile_zip(new)


    def test_directory_traversal_and_symlink_labels_fail_closed(self):
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as out:
            out.writestr("runtime/../private-data", b"synthetic")
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            profile_zip(traversal)

        linked = self.root / "symlink.zip"
        with zipfile.ZipFile(linked, "w") as out:
            info = zipfile.ZipInfo("runtime/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            out.writestr(info, b"synthetic target")
        with self.assertRaisesRegex(ValueError, "symbolic-link"):
            profile_zip(linked)

    def test_path_handle_identity_must_match_without_private_path_leaks(self):
        # Deterministically simulate a replacement between Path.stat() checks.
        # Works on Windows even when real rename over an open file is blocked.
        path = self.root / "candidate.zip"
        self.make_zip(path)
        original_stat = Path.stat
        probes = [0]

        def changed_identity(candidate, *args, **kwargs):
            st = original_stat(candidate, *args, **kwargs)
            if candidate == path:
                probes[0] += 1
                if probes[0] >= 2:
                    return SimpleNamespace(
                        st_mode=st.st_mode, st_dev=st.st_dev,
                        st_ino=st.st_ino + 1, st_size=st.st_size,
                        st_mtime_ns=st.st_mtime_ns,
                    )
            return st

        with patch.object(Path, "stat", changed_identity):
            with self.assertRaisesRegex(ValueError, "identity changed") as result:
                profile_zip(path)
        self.assertGreaterEqual(probes[0], 2)
        self.assertNotIn(str(path), str(result.exception))


if __name__ == "__main__":
    unittest.main()
