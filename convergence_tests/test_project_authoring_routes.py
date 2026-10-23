"""Project and protocol authoring endpoints after extraction (ADR-0002 R2).

The authoring path is where a malformed protocol would do the most damage, so the
tests concentrate on what the transport must not let through: a non-object payload
must fail as 422 before the repository sees it, and publishing must refuse a draft
that has not been given a valid payload.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
AUTHORING_PATHS = {
    ("GET", "/api/v1/projects"),
    ("POST", "/api/v1/projects"),
    ("POST", "/api/v1/projects/{project_id:str}/protocol-drafts"),
    ("GET", "/api/v1/projects/{project_id:str}/protocol-workspace"),
    ("PATCH", "/api/v1/protocol-revisions/{revision_id:str}"),
    ("POST", "/api/v1/protocol-revisions/{revision_id:str}/publish"),
}


class ProjectAuthoringTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-authoring-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'authoring.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        created = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic authoring", "role_title": "Backend"})
        self.assertEqual(created.status_code, 200, created.text)
        self.project = created.json()
        self.pid = self.project["project_id"]

    def revision_id(self) -> str:
        workspace = self.client.get(f"/api/v1/projects/{self.pid}/protocol-workspace")
        self.assertEqual(workspace.status_code, 200, workspace.text)
        body = workspace.json()
        revision = body.get("draft_revision_id")
        self.assertTrue(revision, f"workspace has no draft revision: {sorted(body)}")
        return revision

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in AUTHORING_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), AUTHORING_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.project_authoring"})

    def test_create_and_list_projects(self):
        listing = self.client.get("/api/v1/projects")
        self.assertEqual(listing.status_code, 200)
        ids = [row["project_id"] for row in listing.json()["projects"]]
        self.assertIn(self.pid, ids)

    def test_create_project_requires_title_and_role(self):
        missing = self.client.post("/api/v1/projects", json={"title": "only a title"})
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()["error"]["code"], "invalid_request")

    def test_protocol_workspace_and_draft_fork_are_idempotent(self):
        revision = self.revision_id()
        first = self.client.post(f"/api/v1/projects/{self.pid}/protocol-drafts")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["state"], "draft")
        second = self.client.post(f"/api/v1/projects/{self.pid}/protocol-drafts")
        self.assertEqual(second.status_code, 200)
        # Forking twice must reuse the open draft instead of stacking revisions.
        self.assertEqual(first.json()["revision_id"], second.json()["revision_id"])
        self.assertEqual(first.json()["revision_id"], revision)

    def test_update_rejects_non_object_payload_with_422(self):
        revision = self.revision_id()
        response = self.client.patch(f"/api/v1/protocol-revisions/{revision}",
                                     json={"payload": []})
        self.assertEqual(response.status_code, 422)
        self.assertIn("payload", response.json()["detail"])

    def test_publish_is_one_way_and_locks_the_revision(self):
        revision = self.revision_id()
        published = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["state"], "published")

        again = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(again.status_code, 409, "a published revision must not be republished")

        edit = self.client.patch(f"/api/v1/protocol-revisions/{revision}", json={"payload": {}})
        self.assertEqual(edit.status_code, 409, "a published revision must not be edited in place")

    def test_unknown_ids_are_not_found(self):
        self.assertEqual(
            self.client.post("/api/v1/projects/missing/protocol-drafts").status_code, 404)
        self.assertEqual(
            self.client.get("/api/v1/projects/missing/protocol-workspace").status_code, 404)


if __name__ == "__main__":
    unittest.main()
