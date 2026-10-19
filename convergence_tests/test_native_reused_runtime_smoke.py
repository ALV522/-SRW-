"""Regression tests for exact-prepared Native Runtime reuse audit repair.

No real user data or historical binary is used by this test. A genuine Windows
3.12 embedded Python smoke is required during actual candidate assembly.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.native_payload import PayloadError
from scripts.build_native_from_source_host import _validate_embedded_smoke_audit
from scripts.rebuild_native_from_prepared import (
    BASE_PREPARED_ZIP_SHA256, _validate_embedded_import_output,
    _resmoke_embedded_python,
)
from scripts.verify_prepared_native import REQUIRED_IMPORTS


class ReusedRuntimeSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-runtime-reuse-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.req = self.root / "requirements-ci.txt"
        self.req.write_bytes(b"sqlalchemy==2.0.43\n")
        self.manifest = self.root / "PRODUCTION_RUNTIME.sha256"
        self.manifest.write_bytes(b"0" * 64 + b"  python.exe\n")

    def valid_report(self):
        return {
            "schema": "srw.c11-runtime-reuse-smoke.v1",
            "status": "C11_REUSED_RUNTIME_SMOKE_PASS",
            "embedded_python_smoke": True,
            "source_runtime_unmodified": True,
            "gui_accepted": False,
            "requirements_sha256": hashlib.sha256(self.req.read_bytes()).hexdigest(),
            "runtime_manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "base_prepared_sha256": BASE_PREPARED_ZIP_SHA256,
            "imported_module_count": 13,
            "python": "3.12.10",
            "bytecode_disabled": True,
        }

    def test_valid_actual_reuse_smoke_evidence_has_separate_schema(self):
        _validate_embedded_smoke_audit(
            self.valid_report(), runtime_manifest=self.manifest, requirements=self.req
        )

    def test_old_overlay_rebuild_report_remains_compatible(self):
        evidence = self.valid_report()
        evidence["schema"] = "srw.c11-runtime-overlay-build.v1"
        evidence["status"] = "C11_RUNTIME_SMOKE_PASS"
        _validate_embedded_smoke_audit(
            evidence, runtime_manifest=self.manifest, requirements=self.req
        )

    def test_missing_or_metadata_only_smoke_rejected(self):
        for field, value in [
            ("embedded_python_smoke", False),
            ("source_runtime_unmodified", False),
            ("status", "METADATA_ONLY"),
            ("requirements_sha256", "0" * 64),
            ("runtime_manifest_sha256", "0" * 64),
            ("base_prepared_sha256", "0" * 64),
            ("imported_module_count", 12),
            ("bytecode_disabled", False),
            ("gui_accepted", True),
        ]:
            with self.subTest(field=field):
                bad = self.valid_report()
                bad[field] = value
                with self.assertRaises(PayloadError):
                    _validate_embedded_smoke_audit(
                        bad, runtime_manifest=self.manifest, requirements=self.req
                    )

    def test_rejects_imports_from_external_system_python(self):
        paths = {
            name: str(self.runtime / ("inside-" + name + ".py"))
            for name in REQUIRED_IMPORTS
        }
        paths["httpx"] = str(self.root / "outside" / "httpx.py")
        with self.assertRaisesRegex(PayloadError, "outside staged Runtime"):
            _validate_embedded_import_output(
                json.dumps({"python": "3.12.10", "paths": paths}), self.runtime
            )

    def test_rejects_missing_imports_wrong_version_or_invalid_json(self):
        paths = {
            name: str(self.runtime / ("inside-" + name + ".py"))
            for name in REQUIRED_IMPORTS
        }
        for text in [
            "{}",
            json.dumps({"python": "3.13.0", "paths": paths}),
            json.dumps({"python": "3.12.10", "paths": {"httpx": paths["httpx"]}}),
            "not JSON",
        ]:
            with self.subTest(text=text[:50]), self.assertRaises(PayloadError):
                _validate_embedded_import_output(text, self.runtime)

    def test_valid_relative_boundary_and_module_count(self):
        paths = {
            name: str(self.runtime / (name + ".py"))
            for name in REQUIRED_IMPORTS
        }
        actual = _validate_embedded_import_output(
            json.dumps({"python": "3.12.10", "paths": paths}), self.runtime
        )
        self.assertEqual(actual, {"python": "3.12.10", "modules": 13})

    def test_linux_does_not_claim_windows_executable_smoke(self):
        import os
        if os.name == "nt":
            self.skipTest("this safety gate is Linux-specific")
        with self.assertRaisesRegex(PayloadError, "requires Windows"):
            _resmoke_embedded_python(self.root, self.req)


if __name__ == "__main__":
    unittest.main()
