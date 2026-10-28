"""Conservative, non-authoritative partition invariants for #132."""
from __future__ import annotations

import hashlib
import unittest

from scripts.report_source_manifest_domains import domain_for, render_partition


class DomainManifestPilotTests(unittest.TestCase):
    def test_every_top_level_domain_and_unknown_path_has_one_owner(self):
        mapping = {
            "backend/srw/api/app.py": "backend",
            "frontend/dist/app.js": "frontend",
            "desktop/SRW.Desktop/App.xaml": "desktop",
            "convergence_tests/test_a.py": "tests",
            "browser_acceptance/test_a.py": "tests",
            "docs/OWNER_GUIDE.md": "docs",
            "scripts/check_source_integrity.py": "automation",
            ".github/workflows/ci.yml": "automation",
            ".cursor/rules/srw-governance.mdc": "automation",
            "verification/a.json": "automation",
            "build-lock/a.sha256": "automation",
            "中文目录/test.txt": "root-other",
            "VERSION": "root-other",
        }
        for path, expected in mapping.items():
            with self.subTest(path=path):
                self.assertEqual(domain_for(path), expected)

    def test_exact_union_and_canonical_bytes(self):
        sample = {
            ".github/workflows/ci.yml": "a" * 64,
            "backend/a.py": "b" * 64,
            "desktop/a.cs": "c" * 64,
            "VERSION": "d" * 64,
            "中文目录/z.txt": "e" * 64,
        }
        raw = "".join(f"{sample[p]}  {p}\n" for p in sorted(sample)).encode("utf-8")
        result = render_partition(sample, raw)
        self.assertEqual(result["entries"], len(sample))
        self.assertEqual(result["authority_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["coverage"], "EXACT_UNION_NO_OVERLAP")
        paths = [p for part in result["domains"].values() for p in part["paths"]]
        self.assertEqual(sorted(paths), sorted(sample))

    def test_reject_noncanonical_root_order_or_line_endings(self):
        sample = {"VERSION": "b" * 64, "backend/a.py": "a" * 64}
        lines = [f"{sample[p]}  {p}" for p in sorted(sample)]
        for raw in ("\n".join(reversed(lines)) + "\n", "\r\n".join(lines) + "\r\n",
                    "\n".join(lines), "\n".join(lines) + "\n\n"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ValueError):
                    render_partition(sample, raw.encode("utf-8"))

    def test_changed_manifest_digest_cannot_be_silently_rewritten(self):
        entries = {"backend/a.py": "a" * 64}
        raw = ("a" * 64 + "  backend/a.py\n").encode()
        self.assertEqual(render_partition(entries, raw)["domains"]["backend"]["count"], 1)
        with self.assertRaises(ValueError):
            render_partition(entries, raw.replace(b"a" * 64, b"b" * 64))


    def test_reject_unsafe_handcrafted_manifest_entries(self):
        for path in ("desktop\\a.cs", "../evil.py", "/absolute/a.py", "backend//a.py", "a/./b.py", "a:b", ""):
            with self.subTest(path=path):
                raw = ("a" * 64 + "  " + path + "\n").encode("utf-8")
                with self.assertRaises(ValueError):
                    render_partition({path: "a" * 64}, raw)
        with self.assertRaises(ValueError):
            render_partition({"backend/a.py": "not-a-sha"}, b"not-a-sha  backend/a.py\n")

    def test_unrecognized_root_prefixes_are_visible(self):
        sample = {"services/api/x.py": "a" * 64, "VERSION": "b" * 64}
        raw = "".join(f"{sample[p]}  {p}\n" for p in sorted(sample)).encode("utf-8")
        result = render_partition(sample, raw)
        self.assertEqual(result["domains"]["root-other"]["top_level_prefixes"],
                         ["(root files)", "services"])

if __name__ == "__main__":
    unittest.main()
