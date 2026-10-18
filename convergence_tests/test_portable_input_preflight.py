from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

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
        fake = b"synthetic preflight input - not an executable"
        (runtime / "python.exe").write_bytes(fake)
        (self.root / "PRODUCTION_RUNTIME.sha256").write_text(
            hashlib.sha256(fake).hexdigest() + "  python.exe\n", encoding="utf-8"
        )
        entries = []
        for name, table in DB_TABLES.items():
            folder = self.root / "knowledge" / "active" / name
            folder.mkdir(parents=True)
            db_path = folder / "knowledge.db"
            with closing(sqlite3.connect(db_path)) as db:
                db.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
                db.commit()
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
            {"windows_carrier", "embedded_runtime", "runtime_manifest", "knowledge_manifest"},
        )
        self.assertTrue(all(x["status"] == "BLOCKED" for x in result["checks"]))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_preflight_cli_runs_standalone_from_an_unrelated_directory(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "portable_input_preflight.py"),
             "--root", str(self.root)],
            cwd=self.root, capture_output=True, text=True, timeout=20, check=False,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["inputs_complete"])
        self.assertTrue(any(item["name"] == "runtime_manifest" for item in report["checks"]))

    def test_exact_hash_inventory_and_sqlite_checks_fail_closed(self):
        self._seed_inputs()
        complete = audit(self.root)
        self.assertTrue(complete["inputs_complete"], complete)
        self.assertEqual(len(complete["checks"]), 9)
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


    def test_native_assembler_stages_only_reviewed_inputs(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "build_windows_native_from_v088.ps1"
        content = script.read_text(encoding="utf-8")
        self.assertIn("CopyReviewedSources $Root $stage", content)
        self.assertIn("SOURCE_MANIFEST.sha256", content)
        self.assertIn("portable_input_preflight.py", content)
        self.assertIn("PRODUCTION_KNOWLEDGE.sha256", content)
        self.assertIn("PRODUCTION_RUNTIME.sha256", content)
        self.assertIn("stage-runtime", content)
        self.assertIn("audit-zip", content)
        self.assertIn("_Windows_Native_UNVERIFIED.zip", content)
        self.assertIn("$hostExe", content)
        self.assertNotIn("Copy-Item -Path (Join-Path $Root '*')", content)
        self.assertNotIn("$host = Join-Path", content)

        # Parse, but never execute, the PowerShell assembly script on Windows CI.
        if sys.platform == "win32" and shutil.which("powershell"):
            escaped_path = str(script).replace("'", "''")
            cmd = (
                "$t=$null;$e=$null;"
                "[void][System.Management.Automation.Language.Parser]::ParseFile('"
                + escaped_path
                + "',[ref]$t,[ref]$e);"
                "if($e.Count -ne 0){$e|Out-String|Write-Error;exit 1}"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
