"""Interview/event endpoints after extraction into api/routes/interviews.py.

Transport-level regressions for the second domain moved out of
`api/fullworkbench.py` (ADR-0002 R2). Deeper lineage behaviour - Source
revisioning, supersede markers, decision invalidation - stays covered by
`test_event_source_revision.py` and `test_event_source_ownership.py`; this file
pins the HTTP contract and the ownership of the routes.
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
from srw.modules.candidate.models import Candidate, MaterialRevision, Source
from srw.modules.protocol.models import Project
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]
INTERVIEW_PATHS = {
    ("GET", "/api/v1/candidates/{candidate_id:str}/events"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/events"),
    ("PATCH", "/api/v1/events/{event_id:str}"),
    ("GET", "/api/v1/events/{event_id:str}/scorecards"),
    ("POST", "/api/v1/events/{event_id:str}/scorecards"),
}


class InterviewRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-interview-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(self.url)
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as session:
            project = Project(title="Synthetic interviews")
            session.add(project)
            session.flush()
            candidate = Candidate(project_id=project.id, display_name="Synthetic candidate",
                                  pipeline_stage="interview")
            session.add(candidate)
            session.flush()
            self.cid = candidate.id

        app = create_v1_app(
            self.url,
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.app = app
        self.client = self.enterContext(TestClient(app))

    def audit_count(self, event_type: str) -> int:
        with self.factory() as session:
            return len(session.scalars(select(AuditEvent).where(AuditEvent.event_type == event_type)).all())

    def add_event(self, **body):
        payload = {"event_type": "interview", "title": "Synthetic interview", **body}
        return self.client.post(f"/api/v1/candidates/{self.cid}/events", json=payload)

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            methods = getattr(route, "methods", None) or set()
            for method in methods:
                if (method, route.path) in INTERVIEW_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), INTERVIEW_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.interviews"},
                         "interview routes must stay extracted; re-inlining them would regress R2")

    def test_scheduled_event_round_trip(self):
        created = self.add_event(event_state="scheduled", scheduled_at="2026-11-01T09:00:00+00:00",
                                 interviewer="synthetic", duration_minutes=45)
        self.assertEqual(created.status_code, 200, created.text)
        event = created.json()
        self.assertEqual(event["event_state"], "scheduled")
        self.assertIsNone(event["source_id"], "a scheduled event must not publish evidence")
        self.assertEqual(self.audit_count("RECRUITMENT_EVENT_CREATED"), 1)

        listed = self.client.get(f"/api/v1/candidates/{self.cid}/events")
        self.assertEqual(listed.status_code, 200)
        rows = listed.json()["events"]
        self.assertEqual([row["event_id"] for row in rows], [event["event_id"]])
        self.assertFalse(rows[0]["editable_evidence_source"])

    def test_completed_structured_event_publishes_evidence(self):
        created = self.add_event(
            event_state="completed",
            metadata={"questions": [{"question": "Synthetic question", "criterion_key": ""}]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["source_id"], "completed structured events must publish a Source")
        with self.factory() as session:
            self.assertIsNotNone(session.get(Source, created.json()["source_id"]))
            revisions = session.scalars(select(MaterialRevision)).all()
        self.assertEqual(len(revisions), 1)

    def test_correction_supersedes_without_losing_history(self):
        created = self.add_event(
            event_state="completed",
            metadata={"questions": [{"question": "Original question", "criterion_key": ""}]},
        ).json()
        first_source = created["source_id"]

        patched = self.client.patch(f"/api/v1/events/{created['event_id']}",
                                    json={"metadata": {"questions": [{"question": "Corrected question",
                                                                      "criterion_key": ""}]}})
        self.assertEqual(patched.status_code, 200, patched.text)
        second_source = patched.json()["source_id"]
        self.assertNotEqual(first_source, second_source, "a text change must publish a new Source")

        with self.factory() as session:
            old = session.get(Source, first_source)
            new = session.get(Source, second_source)
            self.assertIsNotNone(old, "the superseded Source must remain immutable history")
            self.assertIn("supersedes_source_id", new.metadata_json)

        # An unchanged correction must stay idempotent and publish nothing new.
        again = self.client.patch(f"/api/v1/events/{created['event_id']}",
                                  json={"metadata": {"questions": [{"question": "Corrected question",
                                                                    "criterion_key": ""}]}})
        self.assertEqual(again.json()["source_id"], second_source)

    def test_unsupported_event_type_is_rejected_with_the_invariant_code(self):
        response = self.client.post(f"/api/v1/candidates/{self.cid}/events",
                                    json={"event_type": "banana", "title": "x"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invariant_conflict")
        self.assertEqual(self.audit_count("RECRUITMENT_EVENT_CREATED"), 0)

    def test_scorecard_round_trip_keeps_evaluators_independent(self):
        event = self.add_event(event_state="completed").json()
        path = f"/api/v1/events/{event['event_id']}/scorecards"
        self.assertEqual(self.client.get(path).status_code, 200)

        first = self.client.post(path, json={"evaluator": "alice", "submit": True,
                                            "feedback": [{"criterion_key": "c1", "rating": "strong"}]})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["state"], "submitted")

        second = self.client.post(path, json={"evaluator": "bob",
                                              "feedback": [{"criterion_key": "c1", "rating": "concern"}]})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["state"], "draft")
        self.assertEqual(self.client.get(path).json()["scorecards"].__len__(), 2)


if __name__ == "__main__":
    unittest.main()
