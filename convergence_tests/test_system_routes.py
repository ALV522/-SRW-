"""System endpoints after extraction into api/routes/system.py (ADR-0002 R2).

Behavioural coverage of backups, restore scheduling and diagnostics already
exists in test_convergence08/09/10/11 and test_restore_schedule_integrity.py.
This file adds what those do not check: that the seven routes are actually
served by the extracted module, plus a thin transport round trip per surface.
"""
from __future__ import annotations

import tempfile
import unittest
import zipfile
import io
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PATHS = {
    ("POST", "/api/v1/system/backups"),
    ("GET", "/api/v1/system/backups"),
    ("GET", "/api/v1/system/backups/{filename:str}"),
    ("POST", "/api/v1/system/backups/{filename:str}/restore"),
    ("POST", "/api/v1/system/restore/cancel"),
    ("GET", "/api/v1/system/diagnostics"),
    ("GET", "/api/v1/system/diagnostics/export"),
}


class SystemRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-system-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.data = root / "data"
        self.data.mkdir()
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(self.data / 'srw_v1.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in SYSTEM_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), SYSTEM_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.system"})

    def test_backup_create_list_download_round_trip(self):
        created = self.client.post("/api/v1/system/backups")
        self.assertEqual(created.status_code, 200, created.text)
        name = created.json()["filename"]
        self.assertTrue(name.endswith(".zip"))
        self.assertGreater(created.json()["size_bytes"], 0)

        listed = self.client.get("/api/v1/system/backups").json()["backups"]
        self.assertEqual([row["filename"] for row in listed], [name])

        downloaded = self.client.get(f"/api/v1/system/backups/{name}")
        self.assertEqual(downloaded.status_code, 200)
        # FileResponse guesses the media type from the platform mimetypes DB
        # (Windows reports application/x-zip-compressed, Linux application/zip).
        self.assertIn("zip", downloaded.headers["content-type"])
        self.assertIn(name, downloaded.headers["content-disposition"])

        self.assertEqual(self.client.get("/api/v1/system/backups/missing.zip").status_code, 404)

    def test_restore_cancel_is_idempotent_and_reports_state(self):
        first = self.client.post("/api/v1/system/restore/cancel")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"scheduled": False})
        self.assertEqual(self.client.post("/api/v1/system/restore/cancel").json(), {"scheduled": False})
        self.assertFalse((self.data / "pending_restore.json").exists())

    def test_diagnostics_and_export_stay_privacy_safe(self):
        diag = self.client.get("/api/v1/system/diagnostics")
        self.assertEqual(diag.status_code, 200)
        payload = diag.json()
        self.assertIn("version", payload)

        export = self.client.get("/api/v1/system/diagnostics/export")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.headers["content-type"], "application/zip")
        self.assertEqual(export.headers.get("Cache-Control"), "no-store")
        with zipfile.ZipFile(io.BytesIO(export.content)) as bundle:
            self.assertTrue(bundle.namelist(), "diagnostic bundle must contain at least one member")


if __name__ == "__main__":
    unittest.main()
