"""Settings and capability-policy endpoints after extraction (ADR-0002 R2).

The settings surface is the one place that reports on provider credentials, so the
first assertion is that it never returns the key itself. The rest pin the policy
path: an unknown capability is 404, an invalid policy is 422, and disabling a
capability persists so a reloaded surface still reports `disabled`.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATHS = {
    ("GET", "/api/v1/settings"),
    ("PATCH", "/api/v1/settings/provider"),
    ("PATCH", "/api/v1/settings/capabilities/{name:str}"),
}
SECRET = "sk-settings-must-never-echo-this"


class SettingsRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-settings-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'settings.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def capabilities(self) -> dict[str, str]:
        body = self.client.get("/api/v1/settings").json()
        return {row["name"]: row.get("policy") for row in body["capabilities"]}

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in SETTINGS_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), SETTINGS_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.settings"})

    def test_settings_surface_reports_configuration_but_not_the_key(self):
        updated = self.client.patch("/api/v1/settings/provider",
                                    json={"provider_type": "deepseek", "api_key": SECRET})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertNotIn(SECRET, updated.text, "the key must never be echoed back")

        body = self.client.get("/api/v1/settings").json()
        self.assertIn("provider", body)
        self.assertIn("capabilities", body)
        self.assertTrue(body["provider"]["api_key_configured"])
        self.assertIn("secret_persistence", body["provider"])
        self.assertNotIn(SECRET, self.client.get("/api/v1/settings").text)

    def test_provider_rejects_an_unknown_provider_type(self):
        response = self.client.patch("/api/v1/settings/provider",
                                     json={"provider_type": "banana"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("provider_type", response.json()["detail"])

    def test_capability_policy_round_trip(self):
        self.assertEqual(self.capabilities(), {"ocr": "on_demand", "asr": "on_demand"})

        disabled = self.client.patch("/api/v1/settings/capabilities/ocr",
                                     json={"policy": "disabled"})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(self.capabilities()["ocr"], "disabled")

        enabled = self.client.patch("/api/v1/settings/capabilities/ocr",
                                    json={"policy": "on_demand"})
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(self.capabilities()["ocr"], "on_demand")

    def test_unknown_capability_and_bad_policy_are_refused(self):
        unknown = self.client.patch("/api/v1/settings/capabilities/banana",
                                    json={"policy": "disabled"})
        self.assertEqual(unknown.status_code, 404)
        self.assertIn("unknown capability", unknown.text)

        bad = self.client.patch("/api/v1/settings/capabilities/ocr", json={"policy": "nope"})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("policy", bad.json()["detail"])


if __name__ == "__main__":
    unittest.main()
