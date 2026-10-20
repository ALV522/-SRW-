"""Offline fail-closed regressions for the source-rebuilt Windows Native verifier.

Fixtures contain only fake Host and Runtime bytes, never customer SQLite/PII.
Actual 101 MB c8431ca7 candidate was separately tested outside GitHub.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.native_payload import PayloadError, PROVENANCE
from scripts.verify_rebuilt_native import (
    ORIGIN, SCHEMA, inspect_rebuilt, validate_rebuild_truth,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SourceRebuildVerifierTests(unittest.TestCase):
    SHA = "c8431ca7012070ff27fd88a219755ea4335cbd68"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="srw-source-rebuild-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "candidate"
        self.root.mkdir()
        source = {
            "VERSION": b"1.0.0-alpha10-convergence11\n",
            "requirements-ci.txt": b"sqlalchemy==2.0.43\n",
            "README.md": b"Synthetic source only\n",
        }
        for relative, data in source.items():
            (self.root / relative).write_bytes(data)
        self.write_manifest("SOURCE_MANIFEST.sha256", source)
        runtime = {"python.exe": b"FAKE-PYTHON-NOT-EXECUTABLE"}
        (self.root / "runtime").mkdir()
        for relative, data in runtime.items():
            (self.root / "runtime" / relative).write_bytes(data)
        self.write_manifest("PRODUCTION_RUNTIME.sha256", runtime)
        five = {
            f"{name}/knowledge.db": b"SYNTHETIC-NOT-A-DB"
            for name in ("taxonomy", "job_info", "competency", "market_reference", "reference")
        }
        for rel, data in five.items():
            target = self.root / "knowledge" / "active" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.write_manifest("PRODUCTION_KNOWLEDGE.sha256", five)
        self.host = self.root / "windows-host"
        self.host.mkdir()
        exe = b"FAKE-WPF-EXE"
        (self.host / "SmartRecruitmentWorkbench.exe").write_bytes(exe)
        self.host_sha = digest(exe)
        (self.host / "HOST_BUILD_CANDIDATE.json").write_text(json.dumps({
            "git_sha": self.SHA,
            "host_sha256": self.host_sha,
            "status": "COMPILED_ONLY_UNVERIFIED_GUI",
            "gui_accepted": False,
            "runtime_included": False,
            "knowledge_included": False,
        }))
        (self.host / "DOTNET_BUILD_TRUTH.json").write_text(json.dumps({
            "source_git_sha": self.SHA,
            "outputs": {"executable_sha256": self.host_sha},
        }))
        self.provenance = self.truth()
        p = self.root / PROVENANCE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.provenance))

    def write_manifest(self, path: str, entries: dict[str, bytes]) -> None:
        (self.root / path).write_text(
            "".join(f"{digest(data)}  {name}\n" for name, data in sorted(entries.items())),
            encoding="utf-8",
        )

    def truth(self) -> dict:
        return {
            "schema": SCHEMA,
            "artifact_status": "UNVERIFIED_GUI",
            "host_origin": ORIGIN,
            "host_source_git_sha": self.SHA,
            "host_executable_sha256": self.host_sha,
            "source_manifest_sha256": digest((self.root / "SOURCE_MANIFEST.sha256").read_bytes()),
            "runtime_manifest_sha256": digest((self.root / "PRODUCTION_RUNTIME.sha256").read_bytes()),
            "target_version": "1.0.0-alpha10-convergence11",
            "c11_pinned_dependency_metadata": "MATCH",
            "independent_legacy_origin_provenance_verified": False,
            "windows_gui_accepted": False,
        }

    def validate(self, item: dict):
        return validate_rebuild_truth(
            item, source_sha=self.SHA,
            source_hash=self.truth()["source_manifest_sha256"],
            runtime_hash=self.truth()["runtime_manifest_sha256"],
            host_hash=self.host_sha,
            version=self.truth()["target_version"],
        )

    def test_rebuilt_identity_contract(self):
        self.validate(self.provenance)

    def test_wrong_or_legacy_provenance_cannot_pass(self):
        changes = {
            "schema": "srw.legacy-inherited-host-provenance.v1",
            "artifact_status": "READY",
            "host_origin": "legacy",
            "host_source_git_sha": "0" * 40,
            "host_executable_sha256": "0" * 64,
            "source_manifest_sha256": "0" * 64,
            "runtime_manifest_sha256": "0" * 64,
            "target_version": "0.8.8",
            "c11_pinned_dependency_metadata": "MISMATCH",
            "independent_legacy_origin_provenance_verified": True,
            "windows_gui_accepted": True,
        }
        for field, wrong in changes.items():
            with self.subTest(field=field):
                candidate = dict(self.provenance)
                candidate[field] = wrong
                with self.assertRaisesRegex(PayloadError, field):
                    self.validate(candidate)

    def test_missing_boolean_cannot_be_replaced_with_integer(self):
        wrong = dict(self.provenance)
        wrong["windows_gui_accepted"] = 0  # bool / integer equality would otherwise pass
        with self.assertRaisesRegex(PayloadError, "windows_gui_accepted"):
            self.validate(wrong)

    def inspect(self, **options):
        # Five DBs are deliberately FAKE here; this mock isolates the source
        # /Host/manifest/allowlist gate. Real DB validation is exercised by
        # the actual c8431ca7 candidate and existing knowledge unit tests.
        with patch("scripts.verify_rebuilt_native.knowledge_checks", return_value=[
            {"status": "PASS"} for _ in range(6)
        ]), patch("scripts.verify_rebuilt_native.check", return_value={
            "status": "PINNED_METADATA_MATCH", "c11_overlay_on_path": True,
        }):
            return inspect_rebuilt(self.root, **options)

    def test_fake_payload_can_exercise_static_contract(self):
        r = self.inspect()
        self.assertEqual(r["source_files"], 3)
        self.assertEqual(r["runtime_files"], 1)
        self.assertEqual(r["knowledge_databases"], 5)
        self.assertEqual(r["source_git_sha"], self.SHA)
        self.assertFalse(r["wpf_webview2_gui_accepted"])
        self.assertEqual(r["embedded_backend_smoke"], "NOT_RUN")

    def test_unreviewed_payload_file_is_rejected(self):
        (self.root / "secrets.txt").write_bytes(b"NEVER-EXFILTRATE")
        with self.assertRaisesRegex(PayloadError, "allowlist"):
            self.inspect()

    def test_tampered_runtime_is_rejected(self):
        (self.root / "runtime" / "python.exe").write_bytes(b"ALTERED")
        with self.assertRaises(PayloadError):
            self.inspect()

    def test_tampered_host_binary_is_rejected(self):
        (self.host / "SmartRecruitmentWorkbench.exe").write_bytes(b"ALTERED")
        with self.assertRaisesRegex(PayloadError, "Host"):
            self.inspect()

    def test_tampered_source_is_rejected(self):
        (self.root / "README.md").write_bytes(b"ALTERED")
        with self.assertRaises(PayloadError):
            self.inspect()

    def test_hash_requires_zip_input(self):
        with self.assertRaisesRegex(PayloadError, "requires --zip"):
            self.inspect(expected_archive_sha256="0" * 64)

    def test_evidence_root_check_rejects_persisted_uploads(self):
        (self.root / "data").mkdir()
        (self.root / "data" / "srw_v1.db").write_bytes(b"SYNTHETIC")
        with self.assertRaisesRegex(PayloadError, "allowlist"):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
