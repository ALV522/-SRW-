"""Runtime identity and lifecycle endpoints after extraction (ADR-0002 R2).

Three contracts matter here and none of them is cosmetic:

* readiness must report 503 with a machine-readable issue list when knowledge is
  missing, because a supervised host decides restarts from it;
* shutdown must refuse (409) when no host callback is registered, so a browser tab
  cannot stop an unsupervised Core;
* info/capabilities must keep their key names, because the desktop shell reads
  them to decide whether a feature exists in this build.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = {
    ("GET", "/api/v1/runtime/live"),
    ("GET", "/api/v1/runtime/ready"),
    ("GET", "/api/v1/runtime/info"),
    ("GET", "/api/v1/runtime/capabilities"),
    ("POST", "/api/v1/runtime/shutdown"),
}


class RuntimeRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-runtime-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'runtime.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in RUNTIME_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), RUNTIME_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.runtime"})

    def test_live_reports_identity(self):
        response = self.client.get("/api/v1/runtime/live")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "live")
        self.assertEqual(body["product"], "SRW")
        self.assertIn("instanceId", body)
        self.assertIn("sessionId", body)

    def test_ready_reports_database_and_knowledge_state(self):
        response = self.client.get("/api/v1/runtime/ready")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertTrue(body["databaseReady"])
        self.assertTrue(body["knowledgeReady"])
        self.assertEqual(body["issues"], [])
        self.assertIn("schemaVersion", body)

    def test_info_and_capabilities_keep_the_desktop_contract(self):
        info = self.client.get("/api/v1/runtime/info").json()
        self.assertEqual(info["apiVersion"], "v1")
        self.assertIn("instanceId", info)
        self.assertIn("dataScopeId", info)
        self.assertIn("capabilities", info)
        self.assertIn("frontend", info)
        self.assertEqual(info["frontend"]["mode"], "static_dist")

        caps = self.client.get("/api/v1/runtime/capabilities").json()
        for key in ("runtime", "edition", "desktop", "clipboard", "downloads",
                    "externalNavigation", "gracefulShutdown", "lifecycleSessionTokenRequired"):
            self.assertIn(key, caps)

    def test_shutdown_refuses_without_a_host_callback(self):
        response = self.client.post("/api/v1/runtime/shutdown")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Host", response.json()["detail"])
        # Refusing must not take the process down.
        self.assertEqual(self.client.get("/api/v1/runtime/live").status_code, 200)

    def test_ready_reports_503_when_knowledge_is_missing(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-runtime-degraded-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        degraded = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'degraded.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=root / "knowledge" / "active",  # intentionally empty
            frontend_dist=ROOT / "frontend" / "dist",
        )
        with TestClient(degraded) as client:
            response = client.get("/api/v1/runtime/ready")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        self.assertFalse(body["knowledgeReady"])
        self.assertIn("knowledge_not_ready", body["issues"])


if __name__ == "__main__":
    unittest.main()
