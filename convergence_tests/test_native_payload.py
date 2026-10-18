from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from scripts.native_payload import PayloadError, audit_runtime, audit_zip, read_manifest, stage_runtime


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class NativePayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        (self.runtime / "python.exe").write_bytes(b"synthetic-exe")
        (self.runtime / "python312.dll").write_bytes(b"synthetic-dll")
        self.runtime_manifest = self.root / "PRODUCTION_RUNTIME.sha256"
        self.runtime_manifest.write_text(
            f"{digest(b'synthetic-exe')}  python.exe\n"
            f"{digest(b'synthetic-dll')}  python312.dll\n", encoding="utf-8"
        )

    def test_powershell_never_executes_runtime_before_hash_staging(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "build_windows_native_from_v088.ps1").read_text(encoding="utf-8")
        self.assertIn("CopyAuditedRuntime", script)
        self.assertIn("CopyReviewedSources $Root $stage", script)
        self.assertIn("audit-zip", script)
        verified = script.index("  CopyAuditedRuntime (Join-Path $Root 'runtime')")
        execute = script.index("  & $RuntimePython (Join-Path $stage 'scripts\\portable_input_preflight.py')")
        self.assertLess(verified, execute)
        self.assertNotIn("& $RuntimePython (Join-Path $Root 'scripts\\portable_input_preflight.py')", script)

    def test_portable_launcher_help_does_not_create_user_data(self):
        # Import/CLI dispatch must not write into a future Native ZIP stage.
        source = Path(__file__).resolve().parents[1] / "scripts" / "launch_alpha10.py"
        shadow = self.root / "shadow"
        scripts = shadow / "scripts"
        scripts.mkdir(parents=True)
        shutil.copyfile(source, scripts / "launch_alpha10.py")
        (shadow / "VERSION").write_text("synthetic", encoding="utf-8")
        runtime_stub = shadow / "backend" / "srw" / "runtime"
        runtime_stub.mkdir(parents=True)
        (runtime_stub / "backup_truth.py").write_text(
            "def extract_validated_backup(*args, **kwargs): pass\n"
            "def write_backup_archive(*args, **kwargs): pass\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(scripts / "launch_alpha10.py"), "--help"],
            cwd=shadow, env={**os.environ, "PYTHONPATH": ""},
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((shadow / "data").exists())

    def test_stage_excludes_unlisted_secret_and_candidate_data(self):
        (self.runtime / "provider_secrets.json").write_text('{"key":"private"}')
        (self.runtime / "backups").mkdir()
        (self.runtime / "backups" / "candidate.zip").write_bytes(b"private")
        dest = self.root / "out" / "runtime"
        result = stage_runtime(self.runtime, self.runtime_manifest, dest)
        self.assertEqual(result["files"], 2)
        self.assertEqual(sorted(x.name for x in dest.iterdir()), ["python.exe", "python312.dll"])

    def test_runtime_binary_tampering_blocks_staging(self):
        (self.runtime / "python.exe").write_bytes(b"changed")
        with self.assertRaises(PayloadError):
            stage_runtime(self.runtime, self.runtime_manifest, self.root / "out")

    def test_missing_runtime_manifest_blocks(self):
        self.runtime_manifest.unlink()
        with self.assertRaises(PayloadError):
            audit_runtime(self.runtime, self.runtime_manifest)

    def test_unsafe_inventory_paths_and_case_collisions_block(self):
        examples = [
            f"{'0'*64}  ../python.exe\n",
            f"{'0'*64}  python.exe\n{'0'*64}  Python.EXE\n",
            f"{'0'*64}  C:/secrets.json\n",
            f"{'0'*64}  secrets.json\n{'0'*64}  python.exe\n",
        ]
        for text in examples:
            with self.subTest(text=text):
                self.runtime_manifest.write_text(text, encoding="utf-8")
                with self.assertRaises(PayloadError):
                    read_manifest(self.runtime_manifest, runtime=True)

    def test_runtime_symlink_rejected(self):
        target = self.root / "external"
        target.write_bytes(b"synthetic-exe")
        (self.runtime / "python.exe").unlink()
        try:
            (self.runtime / "python.exe").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this runner")
        with self.assertRaises(PayloadError):
            audit_runtime(self.runtime, self.runtime_manifest)

    def make_zip(self, *, extra=None, changed=None, status="UNVERIFIED_GUI"):
        source = self.root / "src"
        source.mkdir(exist_ok=True)
        (source / "VERSION").write_bytes(b"test-v\n")
        (source / "START.bat").write_bytes(b"starter")
        source_manifest = (
            f"{digest(b'test-v' + bytes([10]))}  VERSION\n"
            f"{digest(b'starter')}  START.bat\n"
        ).encode()
        (source / "SOURCE_MANIFEST.sha256").write_bytes(source_manifest)
        (source / "PRODUCTION_RUNTIME.sha256").write_bytes(self.runtime_manifest.read_bytes())
        knowledge_bytes = {name: name.encode() for name in
                           ("taxonomy", "job_info", "competency", "market_reference", "reference")}
        knowledge_manifest = "".join(
            f"{digest(data)}  {name}/knowledge.db\n"
            for name, data in knowledge_bytes.items()
        ).encode()
        (source / "PRODUCTION_KNOWLEDGE.sha256").write_bytes(knowledge_manifest)
        host = self.root / "host"
        host.mkdir(exist_ok=True)
        (host / "SmartRecruitmentWorkbench.exe").write_bytes(b"synthetic-host")
        (host / "DOTNET_BUILD_TRUTH.json").write_bytes(b"{}")
        contents = {
            "VERSION": b"test-v\n", "START.bat": b"starter",
            "SOURCE_MANIFEST.sha256": source_manifest,
            "PRODUCTION_RUNTIME.sha256": self.runtime_manifest.read_bytes(),
            "PRODUCTION_KNOWLEDGE.sha256": knowledge_manifest,
            "runtime/python.exe": b"synthetic-exe",
            "runtime/python312.dll": b"synthetic-dll",
            "windows-host/SmartRecruitmentWorkbench.exe": b"synthetic-host",
            "windows-host/DOTNET_BUILD_TRUTH.json": b"{}",
        }
        for name, data in knowledge_bytes.items():
            contents[f"knowledge/active/{name}/knowledge.db"] = data
        contents["verification/INHERITED_WINDOWS_HOST_PROVENANCE.json"] = json.dumps({
            "target_version": "test-v",
            "artifact_status": status,
            "source_manifest_sha256": digest(source_manifest),
            "runtime_manifest_sha256": digest(self.runtime_manifest.read_bytes()),
            "host_executable_sha256": digest(b"synthetic-host"),
        }).encode()
        contents.update(extra or {})
        contents.update(changed or {})
        archive = self.root / "candidate.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for name, body in contents.items():
                z.writestr(name, body)
        return archive, source, host

    def test_clean_synthetic_zip_audit_reports_unverified_gui(self):
        archive, source, host = self.make_zip()
        result = audit_zip(archive, source, host)
        self.assertEqual(result["files_verified"], 15)
        self.assertEqual(result["artifact_status"], "UNVERIFIED_GUI")
        self.assertFalse(result["gui_accepted"])

    def test_final_zip_rejects_private_extra(self):
        archive, source, host = self.make_zip(extra={"data/resume.db": b"private"})
        with self.assertRaisesRegex(PayloadError, "allowlist"):
            audit_zip(archive, source, host)

    def test_final_zip_rejects_tampered_runtime_binary(self):
        archive, source, host = self.make_zip(changed={"runtime/python.exe": b"bad"})
        with self.assertRaisesRegex(PayloadError, "hash mismatch"):
            audit_zip(archive, source, host)

    def test_final_zip_refuses_fake_gui_acceptance(self):
        archive, source, host = self.make_zip(status="GUI_ACCEPTED")
        with self.assertRaisesRegex(PayloadError, "provenance mismatch"):
            audit_zip(archive, source, host)

    def test_final_zip_rejects_duplicate_entry(self):
        archive, source, host = self.make_zip()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "a") as z:
                z.writestr("VERSION", b"duplicate")
        with self.assertRaisesRegex(PayloadError, "duplicate"):
            audit_zip(archive, source, host)


if __name__ == "__main__":
    unittest.main()
