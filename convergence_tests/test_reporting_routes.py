"""Reporting and read-model endpoints after extraction (ADR-0002 R2).

These six routes share ``_brief_payload`` and the assessment projection, which is
why they moved together. The tests pin the contract an operator reads: cockpit
counts, pipeline shape, brief/handoff payloads, CSV export and the comparison
guard that refuses to compare across protocols.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
REPORTING_PATHS = {
    ("GET", "/api/v1/projects/{project_id:str}/cockpit"),
    ("GET", "/api/v1/projects/{project_id:str}/pipeline"),
    ("GET", "/api/v1/projects/{project_id:str}/candidates.csv"),
    ("GET", "/api/v1/candidates/{candidate_id:str}/brief"),
    ("GET", "/api/v1/projects/{project_id:str}/handoff"),
    ("GET", "/api/v1/candidates/compare"),
}


class ReportingRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-reporting-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'reporting.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        created = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic reporting", "role_title": "Synthetic role"})
        self.assertEqual(created.status_code, 200, created.text)
        self.pid = created.json()["project_id"]
        self.cids = []
        for name in ("Alpha", "Beta"):
            response = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                        json={"display_name": name})
            self.assertEqual(response.status_code, 200, response.text)
            self.cids.append(response.json()["candidate_id"])

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in REPORTING_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), REPORTING_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.reporting"})

    def test_cockpit_lists_candidates_with_counts(self):
        response = self.client.get(f"/api/v1/projects/{self.pid}/cockpit")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual({row["display_name"] for row in body["candidates"]}, {"Alpha", "Beta"})
        row = body["candidates"][0]
        self.assertIn("confirmed_claims", row)
        self.assertIn("unreviewed_claims", row)
        self.assertFalse(row["has_material"])

    def test_pipeline_reports_the_funnel(self):
        response = self.client.get(f"/api/v1/projects/{self.pid}/pipeline")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["project_id"], self.pid)
        self.assertEqual(body["total_candidates"], 2)
        self.assertIn("stages", body)
        self.assertIn("offers_by_status", body)

    def test_brief_and_handoff_payloads(self):
        brief = self.client.get(f"/api/v1/candidates/{self.cids[0]}/brief")
        self.assertEqual(brief.status_code, 200, brief.text)
        payload = brief.json()
        self.assertEqual(payload["candidate_id"], self.cids[0])
        self.assertIn("version_context", payload)

        handoff = self.client.get(f"/api/v1/projects/{self.pid}/handoff")
        self.assertEqual(handoff.status_code, 200, handoff.text)
        body = handoff.json()
        self.assertEqual(body["project_id"], self.pid)
        self.assertEqual(len(body["candidates"]), 2)
        self.assertIn("generated_at", body)

        self.assertEqual(self.client.get("/api/v1/candidates/missing/brief").status_code, 404)

    def test_candidates_csv_export(self):
        response = self.client.get(f"/api/v1/projects/{self.pid}/candidates.csv")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("attachment", response.headers["content-disposition"])
        header = response.text.splitlines()[0]
        self.assertIn("candidate_id", header)
        self.assertIn("display_name", header)

    def test_compare_refuses_a_single_candidate(self):
        response = self.client.get("/api/v1/candidates/compare",
                                   params={"ids": self.cids[0]})
        self.assertEqual(response.status_code, 409)
        self.assertIn("2 to 5", response.json()["detail"])

    def test_compare_requires_a_published_protocol(self):
        response = self.client.get("/api/v1/candidates/compare",
                                   params={"ids": ",".join(self.cids)})
        # A freshly created project only has a draft, so comparison must refuse
        # rather than inventing criteria for the operator.
        self.assertEqual(response.status_code, 409)
        self.assertIn("published protocol", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
