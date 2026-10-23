from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.diagnostic_bundle import build_privacy_safe_diagnostic_bundle

ROOT = Path(__file__).resolve().parents[1]


class Convergence10DiagnosticBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")

    def _app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{(self.root/'test.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def test_bundle_is_deterministic_and_drops_arbitrary_sensitive_fields(self):
        diagnostics = {
            "overall_status": "warning",
            "local_only": True,
            "version": "test-release",
            "schema_revision": "v1_test",
            "checks": [
                {"name": "database_integrity", "status": "ok", "detail": "ok"},
                {"name": "data_directory", "status": "ok", "detail": r"C:\\Users\\Alice\\SRW\\data"},
                {"name": "background_tasks", "status": "warning", "detail": {"failed": 1, "queued": 2}},
            ],
            "counts": {"projects": 2, "candidates": 7},
            "database": {"quick_check": "ok", "size_bytes": 1234},
            "tasks": {"by_status": {"failed": 1}, "open": 1, "total": 3},
            "storage": {"data_bytes": 100, "blob_files": 5, "blob_bytes": 80, "missing_source_blobs": 0},
            "pending_restore": False,
            "knowledge": [{"name": "taxonomy", "available": True, "size_bytes": 50}],
            "paths": {"data": r"C:\\Users\\Alice\\SRW\\data"},
            "candidate_name": "Alice Candidate",
            "resume_text": "SECRET RESUME CONTENT",
            "api_key": "sk-super-secret",
        }
        release = {"version": "test-release", "schema_revision": "v1_test"}

        first = build_privacy_safe_diagnostic_bundle(diagnostics, release)
        second = build_privacy_safe_diagnostic_bundle(diagnostics, release)
        self.assertEqual(first, second)

        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(set(archive.namelist()), {"summary.json", "manifest.json"})
            summary_raw = archive.read("summary.json")
            summary = json.loads(summary_raw)
            manifest = json.loads(archive.read("manifest.json"))

        haystack = first.decode("latin1", errors="ignore")
        for forbidden in ("Alice Candidate", "SECRET RESUME CONTENT", "sk-super-secret", "Users\\\\Alice"):
            self.assertNotIn(forbidden, haystack)
        self.assertNotIn("paths", summary)
        self.assertTrue(all(item["detail"] is None for item in summary["checks"] if item["name"] == "data_directory"))
        self.assertEqual(
            manifest["files"]["summary.json"]["sha256"],
            hashlib.sha256(summary_raw).hexdigest(),
        )
        self.assertFalse(summary["privacy"]["contains_candidate_content"])
        self.assertFalse(summary["privacy"]["contains_provider_secrets"])
        self.assertFalse(summary["privacy"]["contains_local_paths"])

    def test_http_diagnostic_export_is_zip_and_no_store(self):
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / "provider_secrets.json").write_text(
            json.dumps({"provider_api_key": "sk-must-not-leak"}),
            encoding="utf-8",
        )
        with TestClient(self._app()) as client:
            response = client.get("/api/v1/system/diagnostics/export")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("attachment;", response.headers["content-disposition"])
        self.assertNotIn(b"sk-must-not-leak", response.content)
        self.assertNotIn(str(self.root).encode(), response.content)

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            summary = json.loads(archive.read("summary.json"))
        self.assertIn(summary["overall_status"], {"ok", "warning"})
        self.assertEqual(summary["release"]["schema_revision"], "v1_0015")
        self.assertTrue(summary["local_only"])

    def test_bundle_does_not_embed_database_or_blob_bytes(self):
        diagnostics = {
            "overall_status": "ok",
            "checks": [],
            "counts": {},
            "database": {"quick_check": "ok", "size_bytes": 999},
            "tasks": {"by_status": {}, "open": 0, "total": 0},
            "storage": {"data_bytes": 9999, "blob_files": 2, "blob_bytes": 8888, "missing_source_blobs": 0},
            "knowledge": [],
        }
        raw = build_privacy_safe_diagnostic_bundle(
            diagnostics, {"version": "x", "schema_revision": "v1_0015"}
        )
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            summary = json.loads(archive.read("summary.json"))
        self.assertEqual(summary["database"]["size_bytes"], 999)
        self.assertEqual(summary["storage"]["blob_bytes"], 8888)
        self.assertFalse(summary["privacy"]["contains_database_bytes"])
        self.assertFalse(summary["privacy"]["contains_source_blobs"])


if __name__ == "__main__":
    unittest.main()
