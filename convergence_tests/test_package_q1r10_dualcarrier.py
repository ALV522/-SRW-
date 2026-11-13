"""Pilot package must fail closed on wrong inputs (CI uses synthetic files)."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_STORED
from scripts.package_q1r10_dualcarrier import build, add


class Q1R10PilotPackagingTests(unittest.TestCase):
    def test_wrong_native_archive_cannot_create_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.zip").write_bytes(b"not-a-Native-archive")
            output = root.parent / (root.name + "-blocked.zip")
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "Pinned original Native"):
                build(root, root / "bad.zip", output)
            self.assertFalse(output.exists())

    def test_packaging_never_writes_into_source_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.zip").write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "outside source tree"):
                build(root, root / "bad.zip", root / "release.zip")
            self.assertFalse((root / "release.zip").exists())


    def test_creator_platform_is_fixed_even_with_windows_zipinfo_default(self):
        # Simulate Windows ZipInfo defaults, without changing process-wide os.name.
        def windows_zipinfo(*args, **kwargs):
            entry = ZipInfo(*args, **kwargs)
            entry.create_system = 0
            return entry

        def make_archive(simulate_windows):
            out = BytesIO()
            if simulate_windows:
                with patch("scripts.package_q1r10_dualcarrier.ZipInfo", side_effect=windows_zipinfo):
                    with ZipFile(out, "w") as writer:
                        add(writer, "test.txt", b"fixed bytes", compression=ZIP_STORED)
            else:
                with ZipFile(out, "w") as writer:
                    add(writer, "test.txt", b"fixed bytes", compression=ZIP_STORED)
            return out.getvalue()

        posix_bytes = make_archive(False)
        windows_bytes = make_archive(True)
        self.assertEqual(windows_bytes, posix_bytes)
        with ZipFile(BytesIO(windows_bytes)) as archive:
            self.assertEqual(archive.infolist()[0].create_system, 3)

if __name__ == "__main__":
    unittest.main()
