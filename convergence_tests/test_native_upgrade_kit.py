"""Regression tests for the GitHub C11 source+Host Windows assembly kit.

All binaries are tiny *synthetic bytes*, not a runnable product. They are used
to assert identity binding, exact member allowlists, and no accidental data
embedding in the distributed kit.
"""
from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.native_payload import PayloadError, sha256_file
from scripts.package_native_upgrade_kit import package, STATUS
from scripts.rebuild_native_from_prepared import _source_sha


class NativeSourceKitTests(unittest.TestCase):
    COMMIT="a1b2c3d4"*5

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="srw-native-kit-test-")
        self.base=Path(self.temp.name)
        self.source=self.base/"source"
        self.source.mkdir()
        self.host=self.base/"host"
        self.host.mkdir()
        files={
            "VERSION":b"1.0.0-alpha.11\n",
            "README.md":b"Fake test project, no user data\n",
            "requirements-ci.txt":b"sqlalchemy==2.0.43\n",
            "SOURCE_RECOVERY_MANIFEST.sha256":b"",
            "scripts/rebuild_native_from_prepared.py":b"# fake runner bytes\n",
        }
        for name,content in files.items():
            path=self.source/name
            path.parent.mkdir(exist_ok=True,parents=True)
            path.write_bytes(content)
        manifest="".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name,data in sorted(files.items())
        )
        (self.source/"SOURCE_MANIFEST.sha256").write_text(manifest,encoding="utf-8")
        exe=self.host/"SmartRecruitmentWorkbench.exe"
        exe.write_bytes(b"FAKE-EXE-FOR-TESTS")
        exe_sha=sha256_file(exe)
        (self.host/"HOST_BUILD_CANDIDATE.json").write_text(json.dumps({
            "git_sha":self.COMMIT,"host_sha256":exe_sha,
            "status":"COMPILED_ONLY_UNVERIFIED_GUI",
            "gui_accepted":False,
            "runtime_included":False,
            "knowledge_included":False,
        }))
        (self.host/"DOTNET_BUILD_TRUTH.json").write_text(json.dumps({
            "source_git_sha":self.COMMIT,
            "outputs":{"executable_sha256":exe_sha},
        }))

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_deterministic_hash_bound_source_host_kit_without_runtime(self):
        dest=self.base/"kit.zip"
        info=package(self.source,self.host,dest,self.COMMIT,enforce_git=False)
        self.assertEqual(info["status"],STATUS)
        self.assertFalse(info["runtime_included"])
        self.assertFalse(info["knowledge_included"])
        self.assertFalse(info["gui_accepted"])
        self.assertEqual(info["source_files"],5)
        with zipfile.ZipFile(dest) as z:
            files=set(z.namelist())
            self.assertIn("BUILD_C11_CANDIDATE.cmd",files)
            self.assertIn("SOURCE_KIT_PROVENANCE.json",files)
            self.assertIn("windows-host/SmartRecruitmentWorkbench.exe",files)
            self.assertNotIn("runtime/python.exe",files)
            self.assertNotIn("knowledge/active/taxonomy/knowledge.db",files)
            cmd=z.read("BUILD_C11_CANDIDATE.cmd")
            self.assertIn(b"\r\n",cmd)
            self.assertNotIn(b"\r\r\n",cmd)
            destination=self.base/"unpacked"
            z.extractall(destination)
        self.assertEqual(_source_sha(destination),self.COMMIT)
        self.assertEqual(sha256_file(dest),info["zip_sha256"])

    def test_rejects_unexpected_git_commit_without_creating_zip(self):
        dest=self.base/"bad.zip"
        with self.assertRaisesRegex(PayloadError,"mismatch"):
            package(self.source,self.host,dest,"d"*40,enforce_git=False)
        self.assertFalse(dest.exists())

    def test_rejects_overwrite_without_mutating_existing(self):
        dest=self.base/"existing.zip"
        dest.write_bytes(b"DO NOT OVERWRITE")
        with self.assertRaisesRegex(PayloadError,"new"):
            package(self.source,self.host,dest,self.COMMIT,enforce_git=False)
        self.assertEqual(dest.read_bytes(),b"DO NOT OVERWRITE")

    def test_rejects_hash_changed_sources_and_partial_edit(self):
        (self.source/"README.md").write_bytes(b"UNLISTED CHANGES")
        with self.assertRaisesRegex(PayloadError,"source manifest failed"):
            package(self.source,self.host,self.base/"bad.zip",self.COMMIT,
                    enforce_git=False)

    def test_rejects_unverifiable_extracted_kit_tampering(self):
        dest=self.base/"kit.zip"
        package(self.source,self.host,dest,self.COMMIT,enforce_git=False)
        with zipfile.ZipFile(dest) as z:
            z.extractall(self.base/"unpacked")
        root=self.base/"unpacked"
        (root/"README.md").write_bytes(b"TAMPERED")
        with self.assertRaisesRegex(PayloadError,"source kit manifest validation failed"):
            _source_sha(root)

    def test_rejects_malicious_host_symlink(self):
        dest=self.base/"bad.zip"
        try:
            (self.host/"other.dll").symlink_to(self.host/"SmartRecruitmentWorkbench.exe")
        except (OSError, NotImplementedError):
            self.skipTest("runner cannot create symlinks (common on Windows)")
        with self.assertRaisesRegex(PayloadError,"symlink"):
            package(self.source,self.host,dest,self.COMMIT,enforce_git=False)


if __name__=="__main__":
    unittest.main()
