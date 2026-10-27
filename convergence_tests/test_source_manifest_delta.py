"""Synthetic tests: reviewer reporter covers all paths and never auto-heals."""
from __future__ import annotations

import unittest

from scripts.report_source_manifest_delta import (
    domain_counts, manifest_changes, parse_manifest_text, render_changes,
)


class SourceManifestDeltaTests(unittest.TestCase):
    def test_detects_roots_hidden_directories_and_windows_host_files(self):
        before = {
            ".github/workflows/ci.yml": "a" * 64,
            "desktop/host.cs": "b" * 64,
            "backend/core.py": "c" * 64,
            "VERSION": "d" * 64,
        }
        after = {
            ".github/workflows/ci.yml": "e" * 64,
            "desktop/host.cs": "b" * 64,
            "backend/core.py": "f" * 64,
            "frontend/dist/app.js": "1" * 64,
        }
        diff = manifest_changes(before, after)
        self.assertEqual(diff["added"], ["frontend/dist/app.js"])
        self.assertEqual(diff["deleted"], ["VERSION"])
        self.assertEqual(diff["changed"], [".github/workflows/ci.yml", "backend/core.py"])
        self.assertEqual(domain_counts(diff), {
            "(root)": 1, ".github": 1, "backend": 1, "frontend": 1,
        })
        self.assertIn("NOT SOURCE INTEGRITY PASS", render_changes(diff))

    def test_empty_diff_is_advisory_not_source_pass(self):
        same = {"desktop/host.cs": "b" * 64}
        printed = render_changes(manifest_changes(same, same))
        self.assertIn("ADVISORY", printed)
        self.assertIn("CHANGED: 0", printed)

    def test_rejects_duplicated_and_traversal_entries(self):
        good = "a" * 64 + "  docs/valid.md\n"
        self.assertEqual(parse_manifest_text(good), {"docs/valid.md": "a" * 64})
        with self.assertRaises(ValueError):
            parse_manifest_text(good + good)
        with self.assertRaises(ValueError):
            parse_manifest_text("a" * 64 + "  ../escape\n")

    def test_new_domain_and_unicode_are_not_omitted(self):
        before = {"docs/经验.md": "c" * 64}
        after = {"docs/经验.md": "c" * 64, "new-module/配置.json": "d" * 64}
        self.assertEqual(manifest_changes(before, after)["added"], ["new-module/配置.json"])
        self.assertEqual(domain_counts(manifest_changes(before, after)), {"new-module": 1})


if __name__ == "__main__":
    unittest.main()
