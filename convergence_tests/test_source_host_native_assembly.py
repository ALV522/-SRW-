from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from scripts.build_native_from_source_host import assemble
from scripts.native_payload import PayloadError


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SourceBuiltHostPackagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "source"
        self.root.mkdir()
        self.inputs = base / "inputs"
        self.inputs.mkdir()
        self.host = base / "host"
        self.host.mkdir()
        self.out = base / "candidate.zip"
        self.commit = "1" * 40
        for name, body in [("VERSION", b"synthetic-C11\n"),
                           ("requirements-ci.txt", b"psutil==7.2.2\n"),
                           ("START.bat", b"echo example\n")]:
            (self.root / name).write_bytes(body)
        (self.root / "SOURCE_MANIFEST.sha256").write_text(
            "".join(f"{digest((self.root / n).read_bytes())}  {n}\n"
                    for n in ("VERSION", "requirements-ci.txt", "START.bat")),
            encoding="utf-8",
        )
        runtime = self.inputs / "runtime"
        runtime.mkdir()
        (runtime / "python.exe").write_bytes(b"synthetic exe")
        (runtime / "python312.dll").write_bytes(b"synthetic dll")
        site = runtime / "Lib/site-packages/psutil-7.2.2.dist-info"
        site.mkdir(parents=True)
        (site / "METADATA").write_text("Name: psutil\nVersion: 7.2.2\n\n", encoding="utf-8")
        paths = sorted(p for p in runtime.rglob("*") if p.is_file())
        (self.inputs / "PRODUCTION_RUNTIME.sha256").write_text(
            "".join(f"{digest(p.read_bytes())}  {p.relative_to(runtime).as_posix()}\n" for p in paths)
        )
        knowledge = self.inputs / "knowledge" / "active"
        required = [
            ("taxonomy", "alias_fts"), ("job_info", "profile_fts"),
            ("competency", "competency_fts"),
            ("market_reference", "beijing_core_field"),
            ("reference", "reference_entity_fts"),
        ]
        hashes = []
        for name, table in required:
            db_path = knowledge / name / "knowledge.db"
            db_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(db_path)) as con:
                con.execute(f"CREATE TABLE {table} (id INTEGER)")
                con.commit()
            hashes.append(f"{digest(db_path.read_bytes())}  {name}/knowledge.db")
        (self.inputs / "PRODUCTION_KNOWLEDGE.sha256").write_text("\n".join(hashes) + "\n")
        exe = b"synthetic host exe"
        (self.host / "SmartRecruitmentWorkbench.exe").write_bytes(exe)
        self.metadata = {
            "git_sha": self.commit, "host_sha256": digest(exe),
            "status": "COMPILED_ONLY_UNVERIFIED_GUI",
            "gui_accepted": False, "runtime_included": False,
            "knowledge_included": False,
        }
        self._write_host()

    def _write_host(self):
        (self.host / "HOST_BUILD_CANDIDATE.json").write_text(json.dumps(self.metadata))
        (self.host / "DOTNET_BUILD_TRUTH.json").write_text(json.dumps({
            "source_git_sha": self.commit,
            "outputs": {"executable_sha256": digest(b"synthetic host exe")},
        }))

    def _assemble(self):
        return assemble(self.root, self.inputs, self.host, self.out,
                        expected_git_sha=self.commit,
                        requirements=self.root / "requirements-ci.txt")

    def test_exact_synthetic_host_runtime_knowledge_produces_unverified_zip(self):
        report = self._assemble()
        self.assertEqual(report["status"], "CANDIDATE_UNVERIFIED_GUI")
        self.assertFalse(report["windows_gui_accepted"])
        with zipfile.ZipFile(self.out) as z:
            self.assertIsNone(z.testzip())
            names = set(z.namelist())
            self.assertIn("windows-host/SmartRecruitmentWorkbench.exe", names)
            self.assertIn("runtime/python.exe", names)
            self.assertIn("knowledge/active/reference/knowledge.db", names)
            p = json.loads(z.read("verification/INHERITED_WINDOWS_HOST_PROVENANCE.json"))
            self.assertEqual(p["host_origin"], "source_rebuild_not_legacy_carrier")
            self.assertFalse(p["windows_gui_accepted"])

    def test_runtime_version_mismatch_blocks_without_output(self):
        (self.root / "requirements-ci.txt").write_text("psutil==99.99.99\n")
        # Keep source manifest consistent so only Runtime compatibility is at issue.
        self._refresh_source_lock()
        with self.assertRaisesRegex(PayloadError, "not compatible"):
            self._assemble()
        self.assertFalse(self.out.exists())

    def _refresh_source_lock(self):
        m = self.root / "SOURCE_MANIFEST.sha256"
        rows = m.read_text().splitlines()
        rows = [digest((self.root / "requirements-ci.txt").read_bytes()) +
                "  requirements-ci.txt" if row.endswith("  requirements-ci.txt")
                else row for row in rows]
        m.write_text("\n".join(rows) + "\n")

    def test_c11_overlay_requires_actual_embedded_runtime_smoke_audit(self):
        runtime = self.inputs / "runtime"
        (runtime / "python312._pth").write_text(
            "python312.zip\nLib\\c11-overlay\nLib\\site-packages\nimport site\n",
            encoding="utf-8",
        )
        overlay = runtime / "Lib" / "c11-overlay" / "psutil-7.2.2.dist-info"
        overlay.mkdir(parents=True)
        (overlay / "METADATA").write_text("Name: psutil\nVersion: 7.2.2\n\n")
        files = sorted(p for p in runtime.rglob("*") if p.is_file())
        (self.inputs / "PRODUCTION_RUNTIME.sha256").write_text(
            "".join(f"{digest(p.read_bytes())}  {p.relative_to(runtime).as_posix()}\n" for p in files)
        )
        with self.assertRaisesRegex(PayloadError, "smoke audit"):
            self._assemble()
        self.assertFalse(self.out.exists())

    def test_wrong_host_commit_refused(self):
        self.metadata["git_sha"] = "2" * 40
        self._write_host()
        with self.assertRaisesRegex(PayloadError, "identity/status"):
            self._assemble()
        self.assertFalse(self.out.exists())

    def test_host_private_database_never_shipped(self):
        private = self.host / "data"
        private.mkdir()
        (private / "candidate.db").write_bytes(b"private")
        with self.assertRaisesRegex(PayloadError, "private"):
            self._assemble()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
