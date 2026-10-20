"""Completed structured interview edits must preserve immutable Source lineage."""
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


class EventSourceRevisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(url)
        self.addCleanup(engine.dispose)
        create_v1_schema(engine)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as session:
            project = Project(title="Synthetic interview source revision")
            session.add(project)
            session.flush()
            candidate = Candidate(project_id=project.id, display_name="Synthetic person")
            session.add(candidate)
            session.flush()
            self.cid = candidate.id
        app = create_v1_app(url, data_dir=root / "data",
                            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                            frontend_dist=Path(__file__).resolve().parents[1] / "frontend" / "dist")
        self.client = self.enterContext(TestClient(app))

    def add_interview(self):
        response = self.client.post(f"/api/v1/candidates/{self.cid}/events", json={
            "event_type": "interview", "title": "Synthetic interview", "event_state": "completed",
            "notes": "First note", "metadata": {"questions": [{"question": "Why?", "answer": "Initial answer"}]},
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def snapshot(self):
        with self.factory() as session:
            return tuple(session.scalar(select(func.count()).select_from(model))
                         for model in (Source, MaterialRevision, AuditEvent))

    def test_completed_structured_edit_creates_new_source_and_material_revision(self):
        initial = self.add_interview()
        event_id, old_source_id = initial["event_id"], initial["source_id"]
        with self.factory() as session:
            old_text = session.get(Source, old_source_id).text_content
            first_revision = session.get(Candidate, self.cid).current_material_revision_id
        response = self.client.patch(f"/api/v1/events/{event_id}", json={
            "notes": "Corrected note", "metadata": {
                "questions": [{"question": "Why?", "answer": "Corrected answer"}]},
        })
        self.assertEqual(response.status_code, 200, response.text)
        new_source_id = response.json()["source_id"]
        self.assertNotEqual(new_source_id, old_source_id)
        with self.factory() as session:
            old_source = session.get(Source, old_source_id)
            new_source = session.get(Source, new_source_id)
            event = session.get(RecruitmentEvent, event_id)
            candidate = session.get(Candidate, self.cid)
            self.assertEqual(old_source.text_content, old_text)
            self.assertIn("Initial answer", old_source.text_content)
            self.assertIn("Corrected answer", new_source.text_content)
            self.assertIn("Corrected note", new_source.text_content)
            self.assertEqual(event.source_id, new_source_id)
            self.assertNotEqual(candidate.current_material_revision_id, first_revision)
            metadata = json.loads(new_source.metadata_json)
            self.assertEqual(metadata["event_id"], event_id)
            self.assertEqual(metadata["supersedes_source_id"], old_source_id)

    def test_noop_update_does_not_mint_evidence_or_revision(self):
        initial = self.add_interview()
        before = self.snapshot()
        response = self.client.patch(f"/api/v1/events/{initial['event_id']}", json={"event_state": "completed"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["source_id"], initial["source_id"])
        after = self.snapshot()
        self.assertEqual(after[:2], before[:2])  # An event update itself still has a genuine audit.
        self.assertEqual(after[2], before[2] + 1)

    def test_external_attached_source_is_not_replaced_on_event_edit(self):
        with self.factory.begin() as session:
            source = Source(candidate_id=self.cid, source_kind="resume",
                            content_hash="a" * 64, text_content="External synthetic note")
            session.add(source)
            session.flush()
            source_id = source.id
        response = self.client.post(f"/api/v1/candidates/{self.cid}/events", json={
            "event_type": "interview", "event_state": "completed", "source_id": source_id,
            "metadata": {"questions": [{"question": "Question", "answer": "Answer"}]},
        })
        self.assertEqual(response.status_code, 200, response.text)
        event_id = response.json()["event_id"]
        before = self.snapshot()
        updated = self.client.patch(f"/api/v1/events/{event_id}", json={"notes": "New event note"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["source_id"], source_id)
        self.assertEqual(self.snapshot()[:2], before[:2])

    def test_invalid_edit_rolls_back_before_any_evidence_mutation(self):
        initial = self.add_interview()
        before = self.snapshot()
        response = self.client.patch(f"/api/v1/events/{initial['event_id']}", json={
            "metadata": {"questions": [{"answer": "No question"}]},
        })
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.snapshot(), before)
