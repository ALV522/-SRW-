from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.portable_input_preflight import DB_TABLES, audit


class PortableInputPreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "WINDOWS_NATIVE_HOST_STATUS.json").write_text(
            json.dumps({"binary_inheritance": {"required_sha256": hashlib.sha256(b"carrier").hexdigest()}}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_inputs(self):
        (self.root / "SRW_v0.8.8_Windows_Portable.zip").write_bytes(b"carrier")
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "python.exe").write_bytes(b"synthetic preflight input - not an executable")
        entries = []
        for name, table in DB_TABLES.items():
            folder = self.root / "knowledge" / "active" / name
            folder.mkdir(parents=True)
            db_path = folder / "knowledge.db"
            with sqlite3.connect(db_path) as db:
                db.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
            sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
            entries.append(f"{sha}  {name}/knowledge.db")
        (self.root / "PRODUCTION_KNOWLEDGE.sha256").write_text(
            "\n".join(entries) + "\n", encoding="utf-8"
        )

    def test_missing_external_inputs_are_reported_without_leaking_paths(self):
        result = audit(self.root)
        self.assertFalse(result["inputs_complete"])
        self.assertFalse(result["portable_built"])
        self.assertFalse(result["windows_gui_accepted"])
        self.assertEqual(
            {x["name"] for x in result["checks"]},
            {"windows_carrier", "embedded_runtime", "knowledge_manifest"},
        )
        self.assertTrue(all(x["status"] == "BLOCKED" for x in result["checks"]))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_exact_hash_inventory_and_sqlite_checks_fail_closed(self):
        self._seed_inputs()
        complete = audit(self.root)
        self.assertTrue(complete["inputs_complete"], complete)
        self.assertEqual(len(complete["checks"]), 8)
        self.assertFalse(complete["production_knowledge_provenance_verified"])
        self.assertFalse(complete["windows_gui_accepted"])

        bad = self.root / "knowledge" / "active" / "taxonomy" / "knowledge.db"
        bad.write_bytes(b"not a SQLite database")
        lines = (self.root / "PRODUCTION_KNOWLEDGE.sha256").read_text(encoding="utf-8").splitlines()
        updated = [
            (hashlib.sha256(bad.read_bytes()).hexdigest() + "  taxonomy/knowledge.db")
            if line.endswith("  taxonomy/knowledge.db") else line for line in lines
        ]
        (self.root / "PRODUCTION_KNOWLEDGE.sha256").write_text(
            "\n".join(updated) + "\n", encoding="utf-8"
        )
        blocked = audit(self.root)
        self.assertFalse(blocked["inputs_complete"])
        self.assertTrue(any(
            x["name"] == "taxonomy/knowledge.db" and x["status"] == "BLOCKED"
            for x in blocked["checks"]
        ))


if __name__ == "__main__":
    unittest.main()
