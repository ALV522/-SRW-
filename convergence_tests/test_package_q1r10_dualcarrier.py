"""Pilot package must fail closed on wrong inputs (CI uses synthetic files)."""
from pathlib import Path
import tempfile
import unittest
from scripts.package_q1r10_dualcarrier import build


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


if __name__ == "__main__":
    unittest.main()
