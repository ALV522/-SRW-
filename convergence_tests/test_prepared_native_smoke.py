from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.native_payload import PayloadError, PROVENANCE
from scripts.verify_prepared_native import inspect_prepared, smoke_windows


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreparedNativeSmokeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="synthetic-prepared-native-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = {"VERSION": "synthetic-c11\n",
                  "requirements-ci.txt": "psutil==7.2.2\n",
                  "scripts/run_local.py": "# not executed here\n"}
        for rel, content in source.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (self.root / "SOURCE_MANIFEST.sha256").write_text(
            "".join(f"{sha(self.root / rel)}  {rel}\n" for rel in source))
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        (self.runtime / "python.exe").write_bytes(b"synthetic Windows interpreter")
        (self.runtime / "python312.dll").write_bytes(b"synthetic Windows DLL")
        (self.runtime / "python312._pth").write_text(
            "python312.zip\nLib\\c11-overlay\nLib\\site-packages\nimport site\n")
        (self.runtime / "Lib/site-packages").mkdir(parents=True)
        overlay = self.runtime / "Lib/c11-overlay/psutil-7.2.2.dist-info"
        overlay.mkdir(parents=True)
        (overlay / "METADATA").write_text("Name: psutil\nVersion: 7.2.2\n\n")
        (self.root / "PRODUCTION_RUNTIME.sha256").write_text(
            "".join(f"{sha(p)}  {p.relative_to(self.runtime).as_posix()}\n"
                    for p in sorted(self.runtime.rglob("*")) if p.is_file()))
        knowledge = self.root / "knowledge/active"
        table_names = [
            ("taxonomy", "alias_fts"),
            ("job_info", "profile_fts"),
            ("competency", "competency_fts"),
            ("market_reference", "beijing_core_field"),
            ("reference", "reference_entity_fts"),
        ]
        hashes = []
        for name, table in table_names:
            path = knowledge / name / "knowledge.db"
            path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(path)) as db:
                db.execute(f"CREATE TABLE {table} (id INTEGER)")
                db.commit()
            hashes.append(f"{sha(path)}  {name}/knowledge.db")
        (self.root / "PRODUCTION_KNOWLEDGE.sha256").write_text("\n".join(hashes) + "\n")
        host = self.root / "windows-host"
        host.mkdir()
        executable = host / "SmartRecruitmentWorkbench.exe"
        executable.write_bytes(b"synthetic WPF host")
        self.commit = "f" * 40
        (host / "HOST_BUILD_CANDIDATE.json").write_text(json.dumps({
            "git_sha": self.commit, "host_sha256": sha(executable),
            "status": "COMPILED_ONLY_UNVERIFIED_GUI", "gui_accepted": False,
        }))
        (host / "DOTNET_BUILD_TRUTH.json").write_text(json.dumps({
            "source_git_sha": self.commit,
            "outputs": {"executable_sha256": sha(executable)},
        }))
        path = self.root / PROVENANCE
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "artifact_status": "UNVERIFIED_GUI",
            "prepared_status": "OFFLINE_WHEELS_STAGED_NEEDS_WINDOWS_EMBEDDED_SMOKE",
            "host_source_git_sha": self.commit,
            "embedded_python_windows_smoke_passed": False,
            "windows_gui_accepted": False,
            "target_version": "synthetic-c11",
            "host_executable_sha256": sha(executable),
            "source_manifest_sha256": sha(self.root / "SOURCE_MANIFEST.sha256"),
            "runtime_manifest_sha256": sha(self.root / "PRODUCTION_RUNTIME.sha256"),
            "knowledge_manifest_sha256": sha(self.root / "PRODUCTION_KNOWLEDGE.sha256"),
        }))

    def test_prepared_static_sha_identity_and_knowledge_pass(self):
        outcome = inspect_prepared(self.root)
        self.assertEqual(outcome["status"], "PREPARED_STATIC_PASS_WINDOWS_SMOKE_NOT_YET_RUN")
        self.assertEqual(outcome["knowledge_databases"], 5)
        self.assertEqual(outcome["pinned_dependencies"], 1)

    def test_tampered_host_exe_blocks_before_python_execution(self):
        (self.root / "windows-host/SmartRecruitmentWorkbench.exe").write_bytes(b"changed")
        with self.assertRaises(PayloadError):
            inspect_prepared(self.root)

    def test_unconfigured_overlay_blocks_before_python_execution(self):
        (self.runtime / "python312._pth").write_text("Lib\\site-packages\n")
        self._rewrite_runtime_manifest()
        with self.assertRaises(ValueError):
            inspect_prepared(self.root)

    def test_modified_source_blocks_before_python_execution(self):
        (self.root / "scripts/run_local.py").write_text("different\n")
        with self.assertRaises(PayloadError):
            inspect_prepared(self.root)

    def _rewrite_runtime_manifest(self):
        (self.root / "PRODUCTION_RUNTIME.sha256").write_text(
            "".join(f"{sha(p)}  {p.relative_to(self.runtime).as_posix()}\n"
                    for p in sorted(self.runtime.rglob("*")) if p.is_file()))

    @unittest.skipIf(os.name == "nt", "Non-Windows negative assertion")
    def test_real_embedded_smoke_rejects_non_windows_os(self):
        with self.assertRaisesRegex(PayloadError, "real Windows"):
            smoke_windows(self.root)


if __name__ == "__main__":
    unittest.main()
