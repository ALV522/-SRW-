"""Candidate CRUD and contact endpoints after extraction (ADR-0002 R2).

Covers the entity lifecycle a recruiter actually performs and the two rules that
are easy to break in a move: a merged source identity cannot be un-archived, and
a contact update must write the confirmed-field set plus one audit event.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.audit.models import AuditEvent
from srw.modules.candidate.models import Candidate
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATHS = {
    ("GET", "/api/v1/projects/{project_id:str}/candidates"),
    ("POST", "/api/v1/projects/{project_id:str}/candidates"),
    ("GET", "/api/v1/candidates/{candidate_id:str}/summary"),
    ("GET", "/api/v1/projects/{project_id:str}/candidate-search"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/archive"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/restore"),
    ("GET", "/api/v1/candidates/{candidate_id:str}/contact"),
    ("PATCH", "/api/v1/candidates/{candidate_id:str}/contact"),
}


class CandidateRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-candidate-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.url = f"sqlite+pysqlite:///{(root / 'data' / 'cands.db').as_posix()}"
        engine = create_v1_engine(self.url)
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        self.factory = create_v1_session_factory(engine)
        self.app = create_v1_app(
            self.url, data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        project = self.client.post("/api/v1/projects", json={"title": "Synthetic project", "role_title": "Synthetic role"})
        self.assertEqual(project.status_code, 200, project.text)
        self.pid = project.json()["project_id"]

    def add(self, name: str) -> str:
        response = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                    json={"display_name": name})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["candidate_id"]

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in CANDIDATE_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), CANDIDATE_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.candidates"})

    def test_create_list_search_and_summary(self):
        cid = self.add("Synthetic Candidate A")
        self.add("Synthetic Candidate B")

        listing = self.client.get(f"/api/v1/projects/{self.pid}/candidates").json()
        self.assertEqual(listing["total"], 2)
        self.assertEqual({row["display_name"] for row in listing["candidates"]},
                         {"Synthetic Candidate A", "Synthetic Candidate B"})

        filtered = self.client.get(f"/api/v1/projects/{self.pid}/candidates",
                                   params={"q": "candidate a"}).json()
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["candidates"][0]["candidate_id"], cid)

        search = self.client.get(f"/api/v1/projects/{self.pid}/candidate-search",
                                 params={"q": "candidate b"}).json()
        self.assertEqual([row["display_name"] for row in search["candidates"]],
                         ["Synthetic Candidate B"])

        summary = self.client.get(f"/api/v1/candidates/{cid}/summary").json()
        self.assertEqual(summary["candidate_id"], cid)
        self.assertEqual(summary["pipeline_stage"], "new")
        self.assertFalse(summary["has_material"])

    def test_list_rejects_unknown_filter_values(self):
        base = f"/api/v1/projects/{self.pid}/candidates"
        self.assertEqual(self.client.get(base, params={"archived": "nope"}).status_code, 409)
        self.assertEqual(self.client.get(base, params={"stage": "nope"}).status_code, 409)
        self.assertEqual(self.client.get(base, params={"limit": "nope"}).status_code, 409)

    def test_archive_and_restore_round_trip(self):
        cid = self.add("Synthetic Archive")
        archived = self.client.post(f"/api/v1/candidates/{cid}/archive")
        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["archived"])

        active = self.client.get(f"/api/v1/projects/{self.pid}/candidates",
                                 params={"archived": "active"}).json()
        self.assertEqual(active["total"], 0)

        restored = self.client.post(f"/api/v1/candidates/{cid}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.json()["archived"])

    def test_merged_identity_cannot_be_restored(self):
        canonical = self.add("Synthetic Canonical")
        cid = self.add("Synthetic Merged")
        with self.factory.begin() as session:
            candidate = session.get(Candidate, cid)
            candidate.archived = True
            candidate.merged_into_candidate_id = canonical
        response = self.client.post(f"/api/v1/candidates/{cid}/restore")
        self.assertEqual(response.status_code, 409)
        self.assertIn("merged", response.json()["detail"])

    def test_contact_update_records_fields_and_audit(self):
        cid = self.add("Synthetic Contact")
        empty = self.client.get(f"/api/v1/candidates/{cid}/contact").json()
        self.assertEqual(empty["phone"], "")
        self.assertEqual(empty["confirmed_fields"], [])

        updated = self.client.patch(f"/api/v1/candidates/{cid}/contact",
                                    json={"phone": "13800000000", "email": "a@example.test",
                                          "user_confirmed": True, "display_name": "Renamed"})
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["phone"], "13800000000")
        self.assertTrue(body["user_confirmed"])
        self.assertEqual(sorted(body["confirmed_fields"]), ["display_name", "email", "phone"])
        self.assertEqual(body["display_name"], "Renamed")

        with self.factory() as session:
            events = session.scalars(select(AuditEvent).where(
                AuditEvent.event_type == "CANDIDATE_CONTACT_UPDATED")).all()
            self.assertEqual(len(events), 1)
            self.assertEqual(session.get(Candidate, cid).display_name, "Renamed")

        # An unconfirmed edit must clear the confirmed set rather than keep stale claims.
        unconfirmed = self.client.patch(f"/api/v1/candidates/{cid}/contact",
                                        json={"phone": "", "user_confirmed": False})
        self.assertEqual(unconfirmed.status_code, 200)
        self.assertEqual(unconfirmed.json()["confirmed_fields"], [])


if __name__ == "__main__":
    unittest.main()
