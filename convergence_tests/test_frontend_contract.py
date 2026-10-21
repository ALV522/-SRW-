"""Frontend contract: every inline-handler reference must resolve to a window assignment.

Mirrors scripts/check_frontend_contract.py inside the source gate. Inline onclick/onchange
attributes run in global scope, so a handler naming a module-scoped function throws
ReferenceError only at click time; this check makes that break class fail CI instead.
Static guard only - it does not replace real Chromium acceptance.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_frontend_contract as frontend  # noqa: E402


class FrontendContractTests(unittest.TestCase):
    def test_current_tree_passes(self):
        self.assertEqual(frontend.main(), 0)

    def test_detects_unassigned_handler_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text(
                '<script type="module" src="/v1/app.js"></script>', encoding="utf-8"
            )
            (dist / "app.js").write_text(
                "async function page(){}\n"
                'document.body.innerHTML=`<button onclick="page()">x</button>`;\n',
                encoding="utf-8",
            )
            inventory = Path(tmp) / "inventory.txt"
            inventory.write_text("# empty\n", encoding="utf-8")
            self.assertEqual(frontend.main(dist=dist, inventory=inventory), 1)

    def test_detects_unregistered_api_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text(
                '<script type="module" src="/v1/app.js"></script>', encoding="utf-8"
            )
            (dist / "app.js").write_text(
                "window.go=()=>{};\n"
                "fetch('/api/v1/does-not-exist');\n",
                encoding="utf-8",
            )
            inventory = Path(tmp) / "inventory.txt"
            inventory.write_text("GET /api/v1/real\n", encoding="utf-8")
            self.assertEqual(frontend.main(dist=dist, inventory=inventory), 1)

    def test_template_expressions_are_not_handler_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text(
                '<script type="module" src="/v1/app.js"></script>', encoding="utf-8"
            )
            (dist / "app.js").write_text(
                "const esc=s=>s;\n"
                "window.act=()=>{};\n"
                "document.body.innerHTML=`<button onclick=\"act('${esc(1)}')\">x</button>`;\n",
                encoding="utf-8",
            )
            inventory = Path(tmp) / "inventory.txt"
            inventory.write_text("# empty\n", encoding="utf-8")
            self.assertEqual(frontend.main(dist=dist, inventory=inventory), 0)


if __name__ == "__main__":
    unittest.main()
