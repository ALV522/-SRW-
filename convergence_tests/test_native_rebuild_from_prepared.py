"""Synthetic-only tests for exact-predecessor Native candidate input extraction.

No real Windows EXE, user resume, production Knowledge, or historical payload
is used. These tests check that the upgrade utility will fail closed *before*
any release status can be claimed.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import sqlite3
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.rebuild_native_from_prepared import (
    BASE_PREPARED_ZIP_SHA256, _members, stage_attested_inputs, upgrade,
)
from scripts.native_payload import KNOWLEDGE, PayloadError, sha256_file
from scripts.portable_input_preflight import DB_TABLES


class NativeCandidateUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="srw-native-upgrade-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def synthetic_archive(self, *, tamper=False, duplicate=False, symlink=False):
        """Build only a tiny, fake Runtime and tiny synthetic SQLite databases."""
        runtime = {
            "python.exe": b"NOT AN ACTUAL PYTHON INTERPRETER",
            "python312.dll": b"NOT AN ACTUAL WINDOWS DLL",
        }
        files = {}
        for name, blob in runtime.items():
            files["runtime/" + name] = blob
        for name in KNOWLEDGE:
            db = self.root / (name + ".db")
            with closing(sqlite3.connect(db)) as conn:
                conn.execute(f"CREATE TABLE {DB_TABLES[name]} (name TEXT)")
                conn.commit()
            files[f"knowledge/active/{name}/knowledge.db"] = db.read_bytes()
        runtime_manifest = "".join(
            f"{hashlib.sha256(blob).hexdigest()}  {name}\n"
            for name, blob in sorted(runtime.items())
        ).encode()
        knowledge_manifest = "".join(
            f"{hashlib.sha256(files[f'knowledge/active/{name}/knowledge.db']).hexdigest()}  {name}/knowledge.db\n"
            for name in KNOWLEDGE
        ).encode()
        files["PRODUCTION_RUNTIME.sha256"] = runtime_manifest
        files["PRODUCTION_KNOWLEDGE.sha256"] = knowledge_manifest
        if tamper:
            files["runtime/python.exe"] = b"altered runtime binary"
        path = self.root / "synthetic-prepared.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, blob in files.items():
                archive.writestr(name, blob)
            if duplicate:
                archive.writestr("runtime/python.exe", files["runtime/python.exe"])
            if symlink:
                member = zipfile.ZipInfo("runtime/untrusted.py")
                member.create_system = 3
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(member, b"/tmp/exfiltrate")
        return path, sha256_file(path)

    def test_known_external_sha_is_immutable(self):
        self.assertEqual(
            BASE_PREPARED_ZIP_SHA256,
            "27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb",
        )

    def test_refuses_incorrect_historical_archive_without_extraction(self):
        path, _ = self.synthetic_archive()
        stage = self.root / "blocked"
        with self.assertRaisesRegex(PayloadError, "SHA-256 mismatch"):
            stage_attested_inputs(path, stage)
        self.assertFalse(stage.exists())

    def test_selective_verified_extraction_uses_only_runtime_and_five_knowledge(self):
        path, digest = self.synthetic_archive()
        stage = self.root / "stage"
        result = stage_attested_inputs(path, stage, required_sha256=digest)
        self.assertEqual(result["runtime_files"], 2)
        self.assertEqual(result["knowledge_databases"], 5)
        self.assertTrue((stage / "runtime/python.exe").is_file())
        self.assertEqual(len(list((stage / "knowledge/active").rglob("knowledge.db"))), 5)
        self.assertFalse((stage / "data").exists())
        self.assertEqual(sha256_file(path), digest)

    def test_rejects_modified_runtime_bytes(self):
        path, digest = self.synthetic_archive(tamper=True)
        with self.assertRaisesRegex(PayloadError, "file hash mismatch"):
            stage_attested_inputs(path, self.root / "stage", required_sha256=digest)

    def test_rejects_duplicate_member(self):
        path, digest = self.synthetic_archive(duplicate=True)
        with self.assertRaisesRegex(PayloadError, "duplicate"):
            stage_attested_inputs(path, self.root / "stage", required_sha256=digest)

    def test_rejects_symlink_member(self):
        path, digest = self.synthetic_archive(symlink=True)
        with self.assertRaisesRegex(PayloadError, "symlink"):
            stage_attested_inputs(path, self.root / "stage", required_sha256=digest)

    def test_rejects_nonempty_existing_target_without_deleting_it(self):
        path, digest = self.synthetic_archive()
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "KEEP.txt").write_text("do not overwrite")
        with self.assertRaisesRegex(PayloadError, "overwrit"):
            stage_attested_inputs(path, stage, required_sha256=digest)
        self.assertEqual((stage / "KEEP.txt").read_text(), "do not overwrite")

    def test_verify_only_does_not_reject_or_modify_an_existing_output_filename(self):
        """A read-only preflight must not depend on a stale output path."""
        existing = self.root / "previous-candidate.zip"
        existing.write_bytes(b"EXISTING CANDIDATE - NEVER OVERWRITE")
        host = self.root / "host"
        host.mkdir()
        source = self.root / "source"
        source.mkdir()
        with patch("scripts.rebuild_native_from_prepared._source_sha", return_value="a" * 40), \
             patch("scripts.rebuild_native_from_prepared._verify_host", return_value={}), \
             patch("scripts.rebuild_native_from_prepared.stage_attested_inputs", return_value={"runtime_files": 2332, "knowledge_databases": 5}), \
             patch("scripts.rebuild_native_from_prepared.check", return_value={"status": "PINNED_METADATA_MATCH"}):
            report = upgrade(source, self.root / "pinned.zip", host, existing, verify_only=True)
        self.assertEqual(report["status"], "INPUTS_VERIFIED_ONLY")
        self.assertFalse(report["assembled"])
        self.assertEqual(existing.read_bytes(), b"EXISTING CANDIDATE - NEVER OVERWRITE")

    def test_cli_has_no_user_hash_override(self):
        from scripts.rebuild_native_from_prepared import main
        import sys
        original = sys.argv
        try:
            sys.argv = ["upgrade", "--base-zip", "synthetic.zip", "--verify-only", "--expected-sha", "0" * 64]
            with self.assertRaises(SystemExit) as thrown:
                main()
            self.assertEqual(thrown.exception.code, 2)
        finally:
            sys.argv = original


if __name__ == "__main__":
    unittest.main()
