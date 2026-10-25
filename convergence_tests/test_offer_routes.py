"""Offer endpoints after extraction into api/routes/offers.py (ADR-0002 R2).

These are transport-level regressions for the first domain moved out of
`api/fullworkbench.py`. They assert the observable contract is unchanged:
same paths, same status codes, same audit effects, same invariant rejections.
They are not Chromium or Windows acceptance.
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
from srw.modules.protocol.models import Project
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]


class OfferRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-offer-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(self.url)
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        factory = create_v1_session_factory(engine)
        with factory.begin() as session:
            project = Project(title="Synthetic offers")
            session.add(project)
            session.flush()
            ready = Candidate(project_id=project.id, display_name="Ready", pipeline_stage="interview")
            new = Candidate(project_id=project.id, display_name="Too early", pipeline_stage="new")
            session.add_all([ready, new])
            session.flush()
            self.project_id = project.id
            self.ready_id = ready.id
            self.too_early_id = new.id

        app = create_v1_app(
            self.url,
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(app))
        self.factory = factory

    def audit_events(self, event_type: str) -> list[AuditEvent]:
        with self.factory() as session:
            return session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == event_type)
            ).all()

    def create_offer(self, candidate_id: str, **body):
        payload = {"title": "Synthetic offer", **body}
        return self.client.post(f"/api/v1/candidates/{candidate_id}/offers", json=payload)

    def test_create_read_and_transition_keep_their_contract(self):
        created = self.create_offer(self.ready_id, compensation_note="synthetic")
        self.assertEqual(created.status_code, 200, created.text)
        offer = created.json()
        self.assertEqual(offer["status"], "draft")
        self.assertEqual(offer["candidate_id"], self.ready_id)
        self.assertTrue(self.audit_events("OFFER_CREATED"), "creation must stay audited")

        listed = self.client.get(f"/api/v1/candidates/{self.ready_id}/offers")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["offer_id"] for row in listed.json()["offers"]], [offer["offer_id"]])

        moved = self.client.post(f"/api/v1/offers/{offer['offer_id']}/status",
                                 json={"status": "approved", "reason": "synthetic"})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["status"], "approved")
        events = self.audit_events("OFFER_STATUS_CHANGED")
        self.assertEqual(len(events), 1)
        self.assertIn("draft", events[0].payload_json)
        self.assertIn("approved", events[0].payload_json)

    def test_stage_invariant_is_enforced_by_the_core_not_the_client(self):
        response = self.create_offer(self.too_early_id)
        # Preserved behaviour: V1InvariantError maps to 409 invariant_conflict.
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invariant_conflict")
        self.assertEqual(self.audit_events("OFFER_CREATED"), [])

    def test_missing_title_still_returns_the_standard_envelope(self):
        response = self.client.post(f"/api/v1/candidates/{self.ready_id}/offers", json={})
        # Known semantic wart, preserved by this move: a missing input field
        # surfaces as 409 invariant_conflict here, while /api/v1/projects
        # reports the same class of mistake as 422 invalid_request.
        # Unifying them is a client-visible contract change and needs its own PR.
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invariant_conflict")
        self.assertIn("title", response.json()["detail"])

    def test_illegal_transition_is_rejected(self):
        offer = self.create_offer(self.ready_id).json()
        response = self.client.post(f"/api/v1/offers/{offer['offer_id']}/status",
                                    json={"status": "accepted"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("not allowed", response.json()["detail"])

    def test_stale_offer_status_cas_rejects_write_without_changing_audit(self):
        """Two stale local clients cannot silently advance the same Offer twice."""
        offer = self.create_offer(self.ready_id).json()
        oid = offer["offer_id"]
        endpoint = f"/api/v1/offers/{oid}/status"
        first = self.client.post(endpoint, json={"expected_status": "draft", "status": "approved", "actor": "human"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "approved")

        # Another UI still displaying `draft` must refresh, not send a second
        # transition that rewrites this offer and pollutes its audit history.
        stale = self.client.post(endpoint, json={"expected_status": "draft", "status": "sent", "actor": "human"})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["error"]["code"], "invariant_conflict")
        self.assertEqual(self.client.get(f"/api/v1/candidates/{self.ready_id}/offers").json()["offers"][0]["status"], "approved")
        self.assertEqual(len(self.audit_events("OFFER_STATUS_CHANGED")), 1)

        current = self.client.post(endpoint, json={"expected_status": "approved", "status": "sent", "actor": "human"})
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["status"], "sent")
        self.assertEqual(len(self.audit_events("OFFER_STATUS_CHANGED")), 2)

    def test_expected_status_is_checked_even_for_noop_and_invalid_values(self):
        offer = self.create_offer(self.ready_id).json()
        endpoint = f"/api/v1/offers/{offer['offer_id']}/status"
        for expected in ("sent", "INVALID", ""):
            with self.subTest(expected=expected):
                response = self.client.post(endpoint, json={"expected_status": expected, "status": "draft"})
                self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.audit_events("OFFER_STATUS_CHANGED"), [])
        noop = self.client.post(endpoint, json={"expected_status": "draft", "status": "draft"})
        self.assertEqual(noop.status_code, 200, noop.text)
        self.assertEqual(self.audit_events("OFFER_STATUS_CHANGED"), [])

    def test_archived_candidate_rejects_new_offer_without_audit_or_row(self):
        archived = self.client.post(f"/api/v1/candidates/{self.ready_id}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        denied = self.create_offer(self.ready_id)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["error"]["code"], "invariant_conflict")
        self.assertEqual(self.client.get(f"/api/v1/candidates/{self.ready_id}/offers").json()["offers"], [])
        self.assertEqual(self.audit_events("OFFER_CREATED"), [])
        restored = self.client.post(f"/api/v1/candidates/{self.ready_id}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(self.create_offer(self.ready_id).status_code, 200)

    def test_archived_project_rejects_new_offer_and_restoration_allows_it(self):
        response = self.client.post(f"/api/v1/projects/{self.project_id}/archive")
        self.assertEqual(response.status_code, 200, response.text)
        denied = self.create_offer(self.ready_id)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(self.audit_events("OFFER_CREATED"), [])
        restored = self.client.post(f"/api/v1/projects/{self.project_id}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(self.create_offer(self.ready_id).status_code, 200)

    def test_archiving_blocks_existing_offer_transition_but_preserves_history(self):
        offer = self.create_offer(self.ready_id).json()
        oid = offer["offer_id"]
        archived = self.client.post(f"/api/v1/candidates/{self.ready_id}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        denied = self.client.post(f"/api/v1/offers/{oid}/status", json={
            "expected_status": "draft", "status": "approved", "reason": "synthetic"})
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(self.audit_events("OFFER_STATUS_CHANGED"), [])
        listed = self.client.get(f"/api/v1/candidates/{self.ready_id}/offers").json()["offers"]
        self.assertEqual([row["status"] for row in listed], ["draft"])
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.ready_id}/restore").status_code, 200)
        accepted = self.client.post(f"/api/v1/offers/{oid}/status", json={
            "expected_status": "draft", "status": "approved", "reason": "synthetic"})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(len(self.audit_events("OFFER_STATUS_CHANGED")), 1)

    def test_archived_project_freezes_existing_offer_without_false_audit(self):
        offer = self.create_offer(self.ready_id).json()
        oid = offer["offer_id"]
        archived = self.client.post(f"/api/v1/projects/{self.project_id}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        rejected = self.client.post(f"/api/v1/offers/{oid}/status", json={
            "expected_status": "draft", "status": "approved"})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(self.audit_events("OFFER_STATUS_CHANGED"), [])
        self.assertEqual(self.client.get(f"/api/v1/candidates/{self.ready_id}/offers")
                         .json()["offers"][0]["status"], "draft")
        self.assertEqual(self.client.post(f"/api/v1/projects/{self.project_id}/restore").status_code, 200)
        advanced = self.client.post(f"/api/v1/offers/{oid}/status", json={
            "expected_status": "draft", "status": "approved"})
        self.assertEqual(advanced.status_code, 200, advanced.text)
        self.assertEqual(len(self.audit_events("OFFER_STATUS_CHANGED")), 1)

    def test_merged_source_candidate_cannot_issue_offer(self):
        with self.factory.begin() as session:
            row = session.get(Candidate, self.ready_id)
            row.merged_into_candidate_id = self.too_early_id
            row.archived = True
        denied = self.create_offer(self.ready_id)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(self.audit_events("OFFER_CREATED"), [])

    def test_unknown_ids_return_not_found(self):
        self.assertEqual(self.client.get("/api/v1/candidates/missing/offers").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/offers/missing/status",
                                          json={"status": "approved"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
