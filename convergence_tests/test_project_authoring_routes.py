"""Project and protocol authoring endpoints after extraction (ADR-0002 R2).

The authoring path is where a malformed protocol would do the most damage, so the
tests concentrate on what the transport must not let through: a non-object payload
must fail as 422 before the repository sees it, and publishing must refuse a draft
that has not been given a valid payload.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
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
        self.db_path = root / "data" / "authoring.db"
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{self.db_path.as_posix()}",
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

    def save_publishable_draft(self, revision, criteria=None, stages=None):
        criteria = criteria if criteria is not None else [
            {"criterion_key": "verified", "name": "Evidence verified"}
        ]
        stages = stages if stages is not None else [
            {"stage_key": "resume", "name": "Resume", "criteria": ["verified"]}
        ]
        saved = self.client.patch(f"/api/v1/protocol-revisions/{revision}", json={
            "payload": {"criteria": criteria, "assessment_stages": stages}
        })
        self.assertEqual(saved.status_code, 200, saved.text)

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
        self.save_publishable_draft(revision)
        published = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["state"], "published")

        again = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(again.status_code, 409, "a published revision must not be republished")

        edit = self.client.patch(f"/api/v1/protocol-revisions/{revision}", json={"payload": {}})
        self.assertEqual(edit.status_code, 409, "a published revision must not be edited in place")

    def test_empty_draft_cannot_publish_or_mutate_project(self):
        revision = self.revision_id()
        refused = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(refused.status_code, 409, refused.text)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT state, published_at FROM protocol_revision WHERE id=?", (revision,)
            ).fetchone(), ("draft", None))
            self.assertEqual(db.execute(
                "SELECT status, current_protocol_revision_id FROM project WHERE id=?", (self.pid,)
            ).fetchone(), ("draft", None))

    def test_blank_name_and_unassigned_criterion_cannot_publish(self):
        revision = self.revision_id()
        self.save_publishable_draft(revision, criteria=[
            {"criterion_key": "verified", "name": "   "}
        ])
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{revision}/publish").status_code, 409)
        self.save_publishable_draft(revision, stages=[
            {"stage_key": "resume", "name": "Resume", "criteria": []}
        ])
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{revision}/publish").status_code, 409)
        self.save_publishable_draft(revision, stages=[
            {"stage_key": "", "name": "Unnamed", "criteria": ["verified"]}
        ])
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{revision}/publish").status_code, 409)
        self.save_publishable_draft(revision)
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{revision}/publish").status_code, 200)

    def test_unknown_stage_reference_rejected_without_publication(self):
        revision = self.revision_id()
        bad = self.client.patch(f"/api/v1/protocol-revisions/{revision}", json={
            "payload": {"criteria": [{"criterion_key": "verified", "name": "Valid"}],
                        "assessment_stages": [{"stage_key": "resume", "criteria": ["missing"]}]}
        })
        self.assertEqual(bad.status_code, 409, bad.text)
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{revision}/publish").status_code, 409)

    def test_failed_republication_keeps_prior_published_pointer(self):
        first = self.revision_id()
        self.save_publishable_draft(first)
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{first}/publish").status_code, 200)
        fork = self.client.post(f"/api/v1/projects/{self.pid}/protocol-drafts")
        self.assertEqual(fork.status_code, 200, fork.text)
        second = fork.json()["revision_id"]
        self.assertNotEqual(first, second)
        empty = self.client.patch(f"/api/v1/protocol-revisions/{second}", json={
            "payload": {"criteria": [], "assessment_stages": []}
        })
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{second}/publish").status_code, 409)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT current_protocol_revision_id FROM project WHERE id=?", (self.pid,)
            ).fetchone()[0], first)
            self.assertEqual(db.execute(
                "SELECT state FROM protocol_revision WHERE id=?", (first,)
            ).fetchone()[0], "published")
            self.assertEqual(db.execute(
                "SELECT state FROM protocol_revision WHERE id=?", (second,)
            ).fetchone()[0], "draft")

    def test_legacy_empty_published_is_readable_and_forkable(self):
        legacy = self.revision_id()
        # Simulate a pre-fix persisted legacy revision; do not rewrite its bytes.
        with closing(sqlite3.connect(self.db_path)) as db:
            before = db.execute(
                "SELECT payload_json FROM protocol_revision WHERE id=?", (legacy,)
            ).fetchone()[0]
            db.execute("UPDATE protocol_revision SET state='published' WHERE id=?", (legacy,))
            db.execute(
                "UPDATE project SET status='open', current_protocol_revision_id=? WHERE id=?",
                (legacy, self.pid))
            db.commit()
        workspace = self.client.get(f"/api/v1/projects/{self.pid}/protocol-workspace")
        self.assertEqual(workspace.status_code, 200, workspace.text)
        self.assertEqual(workspace.json()["current"]["criteria"], [])
        fork = self.client.post(f"/api/v1/projects/{self.pid}/protocol-drafts")
        self.assertEqual(fork.status_code, 200, fork.text)
        replacement = fork.json()["revision_id"]
        self.save_publishable_draft(replacement)
        self.assertEqual(self.client.post(
            f"/api/v1/protocol-revisions/{replacement}/publish").status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT payload_json FROM protocol_revision WHERE id=?", (legacy,)
            ).fetchone()[0], before)
            self.assertEqual(db.execute(
                "SELECT state FROM protocol_revision WHERE id=?", (legacy,)
            ).fetchone()[0], "superseded")

    def test_corrupt_persisted_draft_fails_closed_before_state_change(self):
        revision = self.revision_id()
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE protocol_revision SET payload_json='{' WHERE id=?", (revision,))
            db.commit()
        refused = self.client.post(f"/api/v1/protocol-revisions/{revision}/publish")
        self.assertEqual(refused.status_code, 409, refused.text)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM protocol_revision WHERE id=?", (revision,)
            ).fetchone()[0], "draft")
            self.assertIsNone(db.execute(
                "SELECT current_protocol_revision_id FROM project WHERE id=?", (self.pid,)
            ).fetchone()[0])

    def test_unknown_ids_are_not_found(self):
        self.assertEqual(
            self.client.post("/api/v1/projects/missing/protocol-drafts").status_code, 404)
        self.assertEqual(
            self.client.get("/api/v1/projects/missing/protocol-workspace").status_code, 404)


if __name__ == "__main__":
    unittest.main()
