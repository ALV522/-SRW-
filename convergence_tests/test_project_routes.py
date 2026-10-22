"""Project lifecycle, standards and contact-list endpoints (ADR-0002 R2).

Covers the transition rules that carry product meaning - restore must not claim
more progress than the project has - plus the audit timeline fallback and the CSV
formula neutralisation, which is the one place this slice touches operator safety.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.api.routes.projects import csv_safe_cell

ROOT = Path(__file__).resolve().parents[1]
PROJECT_PATHS = {
    ("POST", "/api/v1/projects/{project_id:str}/status"),
    ("POST", "/api/v1/projects/{project_id:str}/archive"),
    ("POST", "/api/v1/projects/{project_id:str}/restore"),
    ("PATCH", "/api/v1/projects/{project_id:str}/job-setup"),
    ("POST", "/api/v1/projects/{project_id:str}/job-setup/suggest"),
    ("GET", "/api/v1/projects/{project_id:str}/audit"),
    ("GET", "/api/v1/projects/{project_id:str}/contact-queue"),
    ("GET", "/api/v1/projects/{project_id:str}/contact-list.csv"),
}


class ProjectRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-project-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'projects.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        created = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic project", "role_title": "Synthetic role"})
        self.assertEqual(created.status_code, 200, created.text)
        self.pid = created.json()["project_id"]

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in PROJECT_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), PROJECT_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.projects"})

    def test_archive_and_restore_respect_protocol_presence(self):
        archived = self.client.post(f"/api/v1/projects/{self.pid}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(archived.json()["status"], "archived")

        restored = self.client.post(f"/api/v1/projects/{self.pid}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        # A freshly created project has a draft protocol but nothing published,
        # so restore must land on draft rather than claiming it is open.
        self.assertEqual(restored.json()["status"], "draft")

    def test_status_transition_validates_input(self):
        bad = self.client.post(f"/api/v1/projects/{self.pid}/status", json={"status": "banana"})
        self.assertIn(bad.status_code, (409, 422))
        missing = self.client.post(f"/api/v1/projects/{self.pid}/status", json={})
        self.assertEqual(missing.status_code, 409)

    def test_audit_timeline_records_transitions(self):
        self.client.post(f"/api/v1/projects/{self.pid}/archive")
        audit = self.client.get(f"/api/v1/projects/{self.pid}/audit")
        self.assertEqual(audit.status_code, 200)
        body = audit.json()
        self.assertIn("protocol_revisions", body)
        self.assertGreaterEqual(body["total"], 1)
        self.assertTrue(any("PROJECT" in event["event_type"] or "PROJECT" in event["entity_type"]
                            for event in body["audit_events"]),
                        "archiving must leave a project-scoped audit trail")

    def test_unknown_project_is_not_found(self):
        self.assertEqual(self.client.get("/api/v1/projects/missing/audit").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/projects/missing/restore").status_code, 404)

    def test_contact_queue_and_csv_export(self):
        queue = self.client.get(f"/api/v1/projects/{self.pid}/contact-queue")
        self.assertEqual(queue.status_code, 200)
        self.assertIn("candidates", queue.json())

        export = self.client.get(f"/api/v1/projects/{self.pid}/contact-list.csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export.headers["content-type"])
        self.assertIn("contact-list-", export.headers["content-disposition"])
        header = export.text.splitlines()[0]
        self.assertIn("candidate_id", header)
        self.assertIn("next_action", header)

    def test_csv_formula_prefixes_are_neutralised(self):
        self.assertEqual(csv_safe_cell("=1+1"), "'=1+1")
        self.assertEqual(csv_safe_cell("+cmd"), "'+cmd")
        self.assertEqual(csv_safe_cell("-2"), "'-2")
        self.assertEqual(csv_safe_cell("@sum"), "'@sum")
        self.assertEqual(csv_safe_cell("normal text"), "normal text")
        self.assertEqual(csv_safe_cell(None), "")


if __name__ == "__main__":
    unittest.main()
