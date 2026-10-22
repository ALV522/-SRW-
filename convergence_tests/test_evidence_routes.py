"""Evidence and source endpoints after extraction (ADR-0002 R2).

The move relocated two request-parsing helpers into `api/request_fields.py`. The
most important assertion here is therefore the validation envelope: a missing
required field must still come back as 422 `invalid_request`, not as the 409
`invariant_conflict` used by `api/http_utils`. If those two contracts ever merge
by accident, this test fails.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATHS = {
    ("POST", "/api/v1/candidates/{candidate_id:str}/sources/text"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/evidence/extract"),
    ("GET", "/api/v1/sources/{source_id:str}/content"),
    ("GET", "/api/v1/sources/{source_id:str}/file"),
    ("GET", "/api/v1/sources/{source_id:str}/page/{page_number:int}"),
    ("GET", "/api/v1/sources/{source_id:str}/scoring-view"),
    ("GET", "/api/v1/claims/{claim_id:str}/grounding"),
    ("POST", "/api/v1/claims/{claim_id:str}/review"),
}
SAMPLE_TEXT = "Synthetic candidate shipped a payment service for 4 years."


class EvidenceRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-evidence-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.data = root / "data"
        self.data.mkdir(parents=True)
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(self.data / 'evidence.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))
        project = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic evidence", "role_title": "Backend"})
        self.assertEqual(project.status_code, 200, project.text)
        self.pid = project.json()["project_id"]
        candidate = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                     json={"display_name": "Synthetic Candidate"})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        self.cid = candidate.json()["candidate_id"]

    def add_source(self, **overrides):
        payload = {"text_content": SAMPLE_TEXT, "filename": "note.txt", "source_kind": "note",
                   "media_type": "text/plain", **overrides}
        return self.client.post(f"/api/v1/candidates/{self.cid}/sources/text", json=payload)

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in EVIDENCE_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), EVIDENCE_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.evidence"})

    def test_text_source_intake_and_content_round_trip(self):
        created = self.add_source()
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertEqual(body["candidate_id"], self.cid)
        self.assertEqual(body["source_kind"], "note")
        self.assertIsNone(body["material_revision_id"], "publish_material defaults to false")

        content = self.client.get(f"/api/v1/sources/{body['source_id']}/content")
        self.assertEqual(content.status_code, 200, content.text)
        payload = content.json()
        self.assertEqual(payload["text_content"], SAMPLE_TEXT)
        self.assertTrue(payload["has_text"])
        self.assertFalse(payload["has_blob"])
        self.assertIsNone(payload["file_url"])
        self.assertEqual(payload["filename"], "note.txt")

    def test_missing_required_field_keeps_the_422_envelope(self):
        response = self.client.post(f"/api/v1/candidates/{self.cid}/sources/text", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertIn("text_content", response.json()["detail"])

    def test_malformed_json_is_422_not_500(self):
        response = self.client.post(
            f"/api/v1/candidates/{self.cid}/sources/text",
            content=b"{not json", headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 422)

    def test_scoring_view_is_privacy_projected(self):
        source_id = self.add_source().json()["source_id"]
        view = self.client.get(f"/api/v1/sources/{source_id}/scoring-view")
        self.assertEqual(view.status_code, 200, view.text)
        payload = view.json()
        self.assertTrue(payload["remote_provider_safe"])
        self.assertIn("redaction_counts", payload)
        self.assertIn("redaction_spans", payload)
        self.assertIn("length_preserved", payload)

    def test_binary_endpoints_reject_sources_without_blobs(self):
        source_id = self.add_source().json()["source_id"]
        self.assertEqual(self.client.get(f"/api/v1/sources/{source_id}/file").status_code, 404)
        page = self.client.get(f"/api/v1/sources/{source_id}/page/1")
        self.assertEqual(page.status_code, 409)
        self.assertIn("PDF", page.json()["detail"])

    def test_unknown_ids_are_not_found(self):
        self.assertEqual(self.client.get("/api/v1/sources/missing/content").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/sources/missing/scoring-view").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/claims/missing/grounding").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/claims/missing/review",
                                          json={"accepted": True}).status_code, 404)

    def test_claim_review_validates_boolean_before_touching_state(self):
        response = self.client.post("/api/v1/claims/anything/review", json={"accepted": "yes"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("accepted", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
