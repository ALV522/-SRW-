from __future__ import annotations

import hashlib
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.recover_archived_external_inputs import (
    DATABASES, R2_PREFIX, TABLES, recover,
)
from scripts.check_embedded_runtime_compatibility import check


class RecoveredLegacyInputsTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)

    def make_archives(self):
        runtime = self.root / "alpha.zip"
        knowledge = self.root / "r2.zip"
        with zipfile.ZipFile(runtime, "w") as z:
            z.writestr("runtime/python.exe", b"synthetic executable bytes")
            z.writestr("runtime/python312.dll", b"synthetic DLL bytes")
            z.writestr("runtime/Lib/site-packages/certifi/cacert.pem", b"public CA data")
        db = self.root / "fixture.db"
        with closing(sqlite3.connect(db)) as connection:
            for table in TABLES:
                connection.execute(f"CREATE TABLE {table} (id INTEGER)")
            connection.commit()
        with zipfile.ZipFile(knowledge, "w") as z:
            for name in DATABASES:
                z.write(db, R2_PREFIX + name + "/knowledge.db")
        cat = self.root / "catalog.json"
        entries = [
            {"archive_id": "legacy-alpha10-web-portable", "bytes": runtime.stat().st_size,
             "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest()},
            {"archive_id": "legacy-0812-r2-source", "bytes": knowledge.stat().st_size,
             "sha256": hashlib.sha256(knowledge.read_bytes()).hexdigest()},
        ]
        cat.write_text(json.dumps({"schema": "srw.legacy-archive-catalog.v1", "archives": entries}))
        return runtime, knowledge, cat

    def test_recovers_five_integrity_checked_databases_and_public_ca_without_executing(self):
        runtime, knowledge, cat = self.make_archives()
        dest = self.root / "recovered"
        result = recover(runtime, knowledge, dest, cat)
        self.assertEqual(result["recovery"], "PASS")
        self.assertEqual(result["runtime_files_recovered"], 3)
        self.assertEqual(len(result["knowledge_databases"]), 5)
        self.assertFalse(result["c11_python_dependencies_verified"])
        self.assertFalse(result["windows_host_verified"])
        self.assertEqual(
            (dest / "runtime/Lib/site-packages/certifi/cacert.pem").read_bytes(),
            b"public CA data",
        )
        self.assertEqual(len((dest / "PRODUCTION_KNOWLEDGE.sha256").read_text().splitlines()), 5)

    def test_rejects_changed_historical_archive_before_extraction(self):
        runtime, knowledge, cat = self.make_archives()
        with zipfile.ZipFile(runtime, "a") as z:
            z.writestr("runtime/extra.txt", b"unreviewed")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            recover(runtime, knowledge, self.root / "blocked", cat)
        self.assertFalse((self.root / "blocked").exists())

    def test_recovery_never_overwrites_existing_workspace(self):
        runtime, knowledge, cat = self.make_archives()
        output = self.root / "existing"
        output.mkdir()
        (output / "data.db").write_bytes(b"private")
        with self.assertRaisesRegex(ValueError, "empty"):
            recover(runtime, knowledge, output, cat)
        self.assertEqual((output / "data.db").read_bytes(), b"private")

    def test_runtime_compatibility_checks_metadata_without_python_execution(self):
        site = self.root / "runtime/Lib/site-packages/pymupdf-1.28.2.dist-info"
        site.mkdir(parents=True)
        (site / "METADATA").write_text("Name: PyMuPDF\nVersion: 1.28.2\n\n")
        (self.root / "runtime/python.exe").write_bytes(b"synthetic")
        (self.root / "runtime/python312.dll").write_bytes(b"synthetic")
        lock = self.root / "requirements.txt"
        lock.write_text("PyMuPDF==1.28.2\npsutil==7.2.2\n")
        report = check(self.root / "runtime", lock)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["status"], "C11_DEPENDENCIES_NOT_READY")
        self.assertFalse(report["c11_runtime_smoke_passed"])

    def test_native_assembler_requires_pinned_runtime_before_preflight(self):
        script = (Path(__file__).resolve().parents[1] / "scripts" /
                  "build_windows_native_from_v088.ps1").read_text(encoding="utf-8")
        self.assertIn("check_embedded_runtime_compatibility.py", script)
        self.assertLess(
            script.index("check_embedded_runtime_compatibility.py"),
            script.index("portable_input_preflight.py"),
        )

    def test_windows_host_candidate_never_claims_gui_acceptance(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
                    "windows-host-candidate.yml").read_text(encoding="utf-8")
        self.assertIn("RestoreLockedMode=true", workflow)
        self.assertIn("COMPILED_ONLY_UNVERIFIED_GUI", workflow)
        self.assertIn("gui_accepted = $false", workflow)
        self.assertIn("runtime_included = $false", workflow)

    def test_runtime_compatibility_passes_only_exact_metadata(self):
        site = self.root / "runtime/Lib/site-packages/psutil-7.2.2.dist-info"
        site.mkdir(parents=True)
        (site / "METADATA").write_text("Name: psutil\nVersion: 7.2.2\n\n")
        (self.root / "runtime/python.exe").write_bytes(b"synthetic")
        (self.root / "runtime/python312.dll").write_bytes(b"synthetic")
        lock = self.root / "requirements.txt"
        lock.write_text("psutil==7.2.2\n")
        result = check(self.root / "runtime", lock)
        self.assertEqual(result["status"], "PINNED_METADATA_MATCH")
        self.assertFalse(result["windows_runtime_executed"])


if __name__ == "__main__":
    unittest.main()
