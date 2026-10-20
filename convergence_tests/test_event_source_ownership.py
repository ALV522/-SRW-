"""Recruitment records may only cite an existing Source of their candidate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select
from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.audit.models import AuditEvent
from srw.modules.candidate.models import Candidate, MaterialRevision, Source
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory


class EventSourceOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
        self.engine = create_v1_engine(url)
        self.addCleanup(self.engine.dispose)
        create_v1_schema(self.engine)
        self.factory = create_v1_session_factory(self.engine)
        with self.factory.begin() as session:
            projects = [Project(title="Synthetic A"), Project(title="Synthetic B")]
            session.add_all(projects)
            session.flush()
            candidates = [Candidate(project_id=projects[i].id, display_name=f"Synthetic {n}")
                          for n, i in enumerate((0, 0, 1))]
            session.add_all(candidates)
            session.flush()
            sources = [Source(candidate_id=c.id, source_kind="interview_record",
                              content_hash=str(i) * 64, text_content=f"Private synthetic record {i}")
                       for i, c in enumerate(candidates)]
            session.add_all(sources)
            session.flush()
            self.cid = candidates[0].id
            self.source_ids = [source.id for source in sources]
        app = create_v1_app(url, data_dir=root / "data",
                            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                            frontend_dist=Path(__file__).resolve().parents[1] / "frontend" / "dist")
        self.client = self.enterContext(TestClient(app))

    def snapshot(self):
        with self.factory() as session:
            return tuple(session.scalar(select(func.count()).select_from(model))
                         for model in (RecruitmentEvent, AuditEvent, Source, MaterialRevision))

    def create_event(self, **changes):
        payload = {"event_type": "interview", "title": "Synthetic interview",
                   "event_state": "completed", **changes}
        return self.client.post(f"/api/v1/candidates/{self.cid}/events", json=payload)

    def test_foreign_source_is_rejected_with_no_event_or_audit(self):
        for source_id in self.source_ids[1:]:
            with self.subTest(source_id=source_id):
                before = self.snapshot()
                response = self.create_event(source_id=source_id)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(self.snapshot(), before)
                self.assertNotIn("Private synthetic record", response.text)

    def test_nonexistent_source_is_rejected_without_dangling_reference(self):
        before = self.snapshot()
        response = self.create_event(source_id="missing-synthetic-source")
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.snapshot(), before)

    def test_own_source_is_preserved_and_audited(self):
        response = self.create_event(source_id=self.source_ids[0])
        self.assertEqual(response.status_code, 200, response.text)
        event_id = response.json()["event_id"]
        with self.factory() as session:
            event = session.get(RecruitmentEvent, event_id)
            self.assertEqual(event.source_id, self.source_ids[0])
            audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == event_id))
            self.assertEqual(json.loads(audit.payload_json)["source_id"], self.source_ids[0])
        events = self.client.get(f"/api/v1/candidates/{self.cid}/events").json()["events"]
        self.assertEqual(events[0]["source_id"], self.source_ids[0])

    def test_no_source_still_allows_scheduling(self):
        response = self.create_event(event_state="scheduled", scheduled_at="2026-12-01T09:00:00Z")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["source_id"])

    def test_structured_completion_still_generates_owned_source(self):
        response = self.create_event(metadata={"questions": [{"question": "Synthetic question", "answer": "Synthetic answer"}]})
        self.assertEqual(response.status_code, 200, response.text)
        with self.factory() as session:
            source = session.get(Source, response.json()["source_id"])
            self.assertEqual(source.candidate_id, self.cid)
            self.assertIn("Synthetic answer", source.text_content)
            self.assertIsNotNone(session.get(Candidate, self.cid).current_material_revision_id)
