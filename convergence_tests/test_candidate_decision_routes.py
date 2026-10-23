"""Candidate decision surface after extraction (ADR-0002 R2).

The rule this surface encodes: a machine may propose, a human decides. The tests
therefore check the gates rather than the payload shape - a decision cannot be
recorded without a published material revision, an empty reason is refused at the
transport boundary, and every write returns the recomputed workspace.

Two behaviours were verified against the running app before being asserted, because
my first guesses were wrong: `verifications` accepts an arbitrary criterion key
(it records a note, not a protocol-bound judgement), and the decision label is not
echoed back in the workspace projection.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATHS = {
    ("GET", "/api/v1/candidates/{candidate_id:str}/workspace"),
    ("GET", "/api/v1/candidates/{candidate_id:str}/assessment"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/verifications"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/decision"),
}


class CandidateDecisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-candidate-decision-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "data").mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'data' / 'decision.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        project = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic decision", "role_title": "Backend"})
        self.assertEqual(project.status_code, 200, project.text)
        payload = project.json()
        self.pid = payload["project_id"]
        published = self.client.post(
            f"/api/v1/protocol-revisions/{payload['draft_revision_id']}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        candidate = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                     json={"display_name": "Synthetic Candidate"})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        self.cid = candidate.json()["candidate_id"]

    def publish_material(self):
        response = self.client.post(
            f"/api/v1/candidates/{self.cid}/sources/text",
            json={"text_content": "Six years of backend work.", "publish_material": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(response.json()["material_revision_id"])

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in DECISION_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), DECISION_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.candidate_decision"})

    def test_workspace_projection_exposes_the_decision_gate(self):
        workspace = self.client.get(f"/api/v1/candidates/{self.cid}/workspace")
        self.assertEqual(workspace.status_code, 200, workspace.text)
        body = workspace.json()
        self.assertEqual(body["candidate_id"], self.cid)
        for key in ("criteria", "blocking_count", "decision_ready", "decision_context_hash"):
            self.assertIn(key, body)
        self.assertFalse(body["decision_ready"], "no material yet, so the gate must stay closed")

    def test_assessment_is_refused_without_published_material(self):
        response = self.client.get(f"/api/v1/candidates/{self.cid}/assessment")
        self.assertEqual(response.status_code, 409)
        self.assertIn("material", response.json()["detail"])

    def test_decision_requires_a_reason_before_reaching_the_domain(self):
        missing_reason = self.client.post(
            f"/api/v1/candidates/{self.cid}/decision", json={"decision": "advance"})
        self.assertEqual(missing_reason.status_code, 422)
        self.assertIn("reason", missing_reason.json()["detail"])

        missing_decision = self.client.post(
            f"/api/v1/candidates/{self.cid}/decision", json={"reason": "synthetic"})
        self.assertEqual(missing_decision.status_code, 422)

    def test_decision_is_refused_without_published_material(self):
        response = self.client.post(
            f"/api/v1/candidates/{self.cid}/decision",
            json={"decision": "advance", "reason": "synthetic"})
        self.assertEqual(response.status_code, 409)

    def test_decision_records_and_returns_the_workspace(self):
        self.publish_material()
        assessment = self.client.get(f"/api/v1/candidates/{self.cid}/assessment")
        self.assertEqual(assessment.status_code, 200, assessment.text)

        decided = self.client.post(f"/api/v1/candidates/{self.cid}/decision",
                                   json={"decision": "advance", "reason": "synthetic evidence"})
        self.assertEqual(decided.status_code, 200, decided.text)
        body = decided.json()
        self.assertEqual(body["candidate_id"], self.cid)
        self.assertIn("criteria", body, "the route must return the recomputed workspace")

    def test_verification_note_returns_the_workspace(self):
        self.publish_material()
        response = self.client.post(f"/api/v1/candidates/{self.cid}/verifications", json={
            "criterion_key": "synthetic-key", "note": "checked by hand",
            "status": "met", "evidence_level": "strong", "reason": "synthetic"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("criteria", response.json())

    def test_missing_fields_are_422_not_409(self):
        response = self.client.post(f"/api/v1/candidates/{self.cid}/verifications",
                                    json={"note": "only a note"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_unknown_candidate_is_not_found(self):
        self.assertEqual(self.client.get("/api/v1/candidates/missing/workspace").status_code, 404)


if __name__ == "__main__":
    unittest.main()
