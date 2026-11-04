"""Interview/event endpoints after extraction into api/routes/interviews.py.

Transport-level regressions for the second domain moved out of
`api/fullworkbench.py` (ADR-0002 R2). Deeper lineage behaviour - Source
revisioning, supersede markers, decision invalidation - stays covered by
`test_event_source_revision.py` and `test_event_source_ownership.py`; this file
pins the HTTP contract and the ownership of the routes.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.audit.models import AuditEvent
from srw.modules.candidate.models import Candidate, MaterialRevision, Source
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.recruiting.operations_models import InterviewScorecardSubmission
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


    def test_pinned_interview_rejects_same_key_revision_drift_in_core(self):
        """Real HTTP/SQLite: R1 and R2 share a key but change its meaning."""
        def payload(definition):
            return {"criteria": [{"criterion_key": "comm", "name": "Communication",
                                  "definition": definition}],
                    "assessment_stages": [{"stage_key": "interview", "name": "Interview",
                                           "criteria": ["comm"]}]}

        with self.factory.begin() as session:
            project = session.get(Project, session.get(Candidate, self.cid).project_id)
            first = ProtocolRevision(project_id=project.id, revision=1, state="published",
                                     payload_json=json.dumps(payload("Cross-team communication")),
                                     content_hash="a" * 64)
            session.add(first)
            session.flush()
            project.current_protocol_revision_id = first.id
            r1 = first.id

        metadata = {"protocol_revision_id": r1,
                    "questions": [{"criterion_key": "comm", "question": "Give an example"}]}
        created = self.add_event(event_state="scheduled", metadata=metadata)
        self.assertEqual(created.status_code, 200, created.text)
        eid = created.json()["event_id"]
        path = f"/api/v1/events/{eid}/scorecards"
        accepted = self.client.post(path, json={
            "evaluator": "first", "submit": True,
            "feedback": [{"criterion_key": "comm", "rating": "strong"}]})
        self.assertEqual(accepted.status_code, 200, accepted.text)

        with self.factory.begin() as session:
            first = session.get(ProtocolRevision, r1)
            first.state = "superseded"
            second = ProtocolRevision(project_id=first.project_id, revision=2, state="published",
                                      payload_json=json.dumps(payload("Customer escalation")),
                                      content_hash="b" * 64)
            session.add(second)
            session.flush()
            session.get(Project, first.project_id).current_protocol_revision_id = second.id

        before_audit = (self.audit_count("RECRUITMENT_EVENT_UPDATED"),
                        self.audit_count("INTERVIEW_SCORECARD_SUBMITTED"))
        with self.factory() as session:
            before_metadata = session.get(RecruitmentEvent, eid).metadata_json

        stale_update = self.client.patch(f"/api/v1/events/{eid}", json={
            "event_state": "completed", "metadata": metadata})
        self.assertEqual(stale_update.status_code, 409, stale_update.text)
        stale_score = self.client.post(path, json={
            "evaluator": "second", "submit": True,
            "feedback": [{"criterion_key": "comm", "rating": "strong"}]})
        self.assertEqual(stale_score.status_code, 409, stale_score.text)
        stale_create = self.add_event(event_state="scheduled", metadata=metadata)
        self.assertEqual(stale_create.status_code, 409, stale_create.text)
        self.assertEqual(before_audit, (self.audit_count("RECRUITMENT_EVENT_UPDATED"),
                                        self.audit_count("INTERVIEW_SCORECARD_SUBMITTED")))
        with self.factory() as session:
            self.assertEqual(session.get(RecruitmentEvent, eid).metadata_json, before_metadata)
            self.assertEqual(len(session.scalars(select(InterviewScorecardSubmission)).all()), 1)
            self.assertEqual(len(session.scalars(select(RecruitmentEvent)).all()), 1)
            self.assertEqual(len(session.scalars(select(Source)).all()), 0)
        self.assertEqual(len(self.client.get(path).json()["scorecards"]), 1)

    def test_pinned_interview_rejects_pin_removal_and_foreign_scorecard_key(self):
        with self.factory.begin() as session:
            project = session.get(Project, session.get(Candidate, self.cid).project_id)
            protocol = ProtocolRevision(project_id=project.id, revision=1, state="published",
                                        payload_json=json.dumps({
                                            "criteria": [{"criterion_key": "comm"}],
                                            "assessment_stages": [{"stage_key": "interview",
                                                                   "criteria": ["comm"]}]}),
                                        content_hash="a" * 64)
            session.add(protocol)
            session.flush()
            project.current_protocol_revision_id = protocol.id
            revision_id = protocol.id

        metadata = {"protocol_revision_id": revision_id,
                    "questions": [{"criterion_key": "comm", "question": "Example?"}]}
        created = self.add_event(event_state="scheduled", metadata=metadata)
        self.assertEqual(created.status_code, 200, created.text)
        eid = created.json()["event_id"]
        removed = self.client.patch(f"/api/v1/events/{eid}", json={
            "metadata": {"questions": metadata["questions"]}})
        self.assertEqual(removed.status_code, 409, removed.text)
        wrong_key = self.client.post(f"/api/v1/events/{eid}/scorecards", json={
            "evaluator": "synthetic", "submit": True,
            "feedback": [{"criterion_key": "other", "rating": "strong"}]})
        self.assertEqual(wrong_key.status_code, 409, wrong_key.text)
        with self.factory() as session:
            self.assertEqual(json.loads(session.get(RecruitmentEvent, eid).metadata_json)
                             ["protocol_revision_id"], revision_id)
            self.assertEqual(len(session.scalars(select(InterviewScorecardSubmission)).all()), 0)

    def test_phone_screen_without_published_criteria_still_completes(self):
        """Non-structured phone follow-up is a preserved legacy operator action."""
        created = self.client.post(f"/api/v1/candidates/{self.cid}/events", json={
            "event_type": "phone_screen", "event_state": "scheduled",
            "title": "Synthetic call", "notes": "Awaiting callback"})
        self.assertEqual(created.status_code, 200, created.text)
        eid = created.json()["event_id"]
        completed = self.client.patch(f"/api/v1/events/{eid}", json={
            "event_state": "completed", "notes": "Reached candidate"})
        self.assertEqual(completed.status_code, 200, completed.text)
        with self.factory() as session:
            row = session.get(RecruitmentEvent, eid)
            self.assertEqual(row.event_state, "completed")
            self.assertEqual(row.notes, "Reached candidate")
            self.assertIsNone(row.source_id)



    def test_pinned_interview_rejects_out_of_stage_keys_and_forged_definitions(self):
        """Real HTTP+SQLite: a valid revision ID cannot launder a fake key or definition."""
        with self.factory.begin() as session:
            project = session.get(Project, session.get(Candidate, self.cid).project_id)
            protocol = ProtocolRevision(
                project_id=project.id, revision=1, state="published",
                payload_json=json.dumps({
                    "criteria": [
                        {"criterion_key": "comm", "name": "Communication", "definition": "Team alignment"},
                        {"criterion_key": "finance", "name": "Finance", "definition": "Finance expertise"},
                    ],
                    "assessment_stages": [{"stage_key": "interview", "criteria": ["comm"]}],
                }), content_hash="c" * 64,
            )
            session.add(protocol)
            session.flush()
            project.current_protocol_revision_id = protocol.id
            revision_id = protocol.id

        def write(key, snapshot=None):
            metadata = {
                "protocol_revision_id": revision_id,
                "questions": [{"criterion_key": key, "question": "Give one example"}],
            }
            if snapshot is not None:
                metadata["criteria_snapshot"] = snapshot
            return self.add_event(event_state="scheduled", metadata=metadata)

        wrong_stage = write("finance")
        self.assertEqual(wrong_stage.status_code, 409, wrong_stage.text)
        unknown = write("invented")
        self.assertEqual(unknown.status_code, 409, unknown.text)
        forged = write("comm", [{
            "criterion_key": "comm", "name": "Finance", "definition": "Invented meaning",
        }])
        self.assertEqual(forged.status_code, 409, forged.text)
        self.assertEqual(self.audit_count("RECRUITMENT_EVENT_CREATED"), 0)
        with self.factory() as session:
            self.assertEqual(len(session.scalars(select(RecruitmentEvent)).all()), 0)

        accepted = write("comm")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        with self.factory() as session:
            stored = json.loads(session.get(
                RecruitmentEvent, accepted.json()["event_id"]).metadata_json)
        self.assertEqual(stored["criteria_snapshot"], [{
            "criterion_key": "comm", "name": "Communication", "definition": "Team alignment",
        }])


if __name__ == "__main__":
    unittest.main()
