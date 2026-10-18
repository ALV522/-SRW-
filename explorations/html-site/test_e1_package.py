"""Source demo package regression tests: integrity, isolation, launcher layout."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("package_demo", HERE / "package_demo.py")
assert SPEC and SPEC.loader
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


class E1PackageTests(unittest.TestCase):
    def test_build_layout_and_verify_without_user_data(self):
        with tempfile.TemporaryDirectory(prefix="srw-e1-bundle-") as td:
            dest = Path(td) / "srw-e1-source-demo"
            pack.build(dest)
            self.assertTrue((dest / "START_HERE.cmd").is_file())
            for item in pack.COPY_DIRS + pack.COPY_FILES:
                self.assertTrue((dest / item).exists(), item)
            self.assertFalse((dest / "data").exists())
            self.assertFalse((dest / "knowledge").exists())
            self.assertFalse((dest / "runtime").exists())
            self.assertFalse((dest / ".git").exists())
            self.assertFalse((dest / "explorations/html-site/.e1-demo-venv").exists())
            pack.verify(dest)
            manifest = json.loads((dest / "PACKAGE_MANIFEST.sha256.json").read_text(encoding="utf-8"))
            self.assertGreater(len(manifest["files"]), 20)
            self.assertIn("explorations/html-site/run_e1_demo_windows.cmd", manifest["files"])

    def test_detects_tampered_demo_entrypoint(self):
        with tempfile.TemporaryDirectory(prefix="srw-e1-bundle-") as td:
            dest = Path(td) / "srw-e1-source-demo"
            pack.build(dest)
            demo = dest / "explorations/html-site/e1-live.html"
            demo.write_text(demo.read_text(encoding="utf-8") + "\n<!-- tampered -->", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                pack.verify(dest)

    def test_rejects_unexpected_source_output_content(self):
        with tempfile.TemporaryDirectory(prefix="srw-e1-bundle-") as td:
            dest = Path(td) / "srw-e1-source-demo"
            dest.mkdir()
            (dest / "existing-database.sqlite").write_text("do not delete", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already contain"):
                pack.build(dest)


if __name__ == "__main__":
    unittest.main()
