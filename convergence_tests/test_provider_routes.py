"""Provider settings endpoints after extraction (ADR-0002 R2, fifth slice).

Beyond route ownership, this file locks the credential contract: the HTTP surface
may report whether a provider key is configured, but must never echo the key, a
prefix of it, or its length. A leak here would be a real security regression, so
it is asserted against the serialised response body rather than a parsed field.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_PATHS = {
    ("GET", "/api/v1/settings/providers"),
    ("PATCH", "/api/v1/settings/providers/{name:str}"),
    ("POST", "/api/v1/settings/providers/{name:str}/test"),
}
SECRET = "sk-synthetic-must-never-leak-0123456789"


class ProviderRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-provider-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'srw_v1.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in PROVIDER_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), PROVIDER_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.providers"})

    def test_profiles_report_configuration_but_never_the_key(self):
        configured = self.client.patch("/api/v1/settings/providers/text_ai",
                                       json={"api_key": SECRET, "model": "synthetic-model"})
        self.assertEqual(configured.status_code, 200, configured.text)

        response = self.client.get("/api/v1/settings/providers")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertNotIn(SECRET, body, "the raw API key must never reach a client")
        self.assertNotIn(SECRET[:8], body, "even a key prefix narrows a brute-force search")

        payload = response.json()
        self.assertEqual(set(payload["profiles"]), {"text_ai", "ocr", "asr"})
        self.assertTrue(payload["profiles"]["text_ai"]["api_key_configured"])
        self.assertEqual(payload["profiles"]["text_ai"]["model"], "synthetic-model")
        self.assertNotIn("api_key", payload["profiles"]["text_ai"])
        self.assertFalse(payload["profiles"]["ocr"]["api_key_configured"])

    def test_update_rejects_unknown_provider_and_bad_field_types(self):
        self.assertEqual(
            self.client.patch("/api/v1/settings/providers/banana", json={}).status_code, 404)
        self.assertEqual(
            self.client.patch("/api/v1/settings/providers/text_ai",
                              json={"model": 123}).status_code, 409)

    def test_probe_without_a_key_reports_provider_not_ready(self):
        response = self.client.post("/api/v1/settings/providers/asr/test")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "provider_not_ready")
        self.assertIn("not configured", response.json()["detail"])

    def test_probe_failure_never_echoes_the_key(self):
        self.client.patch("/api/v1/settings/providers/text_ai",
                          json={"api_key": SECRET, "base_url": "http://127.0.0.1:9"})
        response = self.client.post("/api/v1/settings/providers/text_ai/test")
        self.assertIn(response.status_code, (502, 409))
        self.assertNotIn(SECRET, response.text)


if __name__ == "__main__":
    unittest.main()
