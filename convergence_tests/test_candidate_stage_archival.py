"""Archived/merged recruitment identities cannot be advanced by stale clients."""
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


class CandidateStageArchiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="srw-stage-archive-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        database = root / "test.db"
        self.url = f"sqlite+pysqlite:///{database.as_posix()}"
        engine = create_v1_engine(self.url)
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as s:
            project = Project(title="Synthetic stage archive", status="open")
            s.add(project)
            s.flush()
            active = Candidate(project_id=project.id, display_name="Active", pipeline_stage="new")
            past = Candidate(project_id=project.id, display_name="Archived", pipeline_stage="new", archived=True)
            s.add_all([active, past])
            s.flush()
            self.pid = project.id
            self.active_id = active.id
            self.past_id = past.id
        app = create_v1_app(
            self.url, data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(app))

    def stage(self, cid, stage):
        return self.client.post(f"/api/v1/candidates/{cid}/stage", json={"stage": stage, "actor": "human"})

    def history(self, cid):
        return self.client.get(f"/api/v1/candidates/{cid}/pipeline").json()

    def audit_count(self):
        with self.factory() as session:
            return len(session.scalars(select(AuditEvent).where(AuditEvent.event_type == "CANDIDATE_STAGE_CHANGED")).all())

    def test_archived_candidate_is_not_advanced_until_explicit_restore(self):
        denied = self.stage(self.past_id, "shortlisted")
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(self.history(self.past_id)["transitions"], [])
        self.assertEqual(self.audit_count(), 0)
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.past_id}/restore").status_code, 200)
        allowed = self.stage(self.past_id, "shortlisted")
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(len(self.history(self.past_id)["transitions"]), 1)

    def test_archived_project_prevents_stage_change_until_restore(self):
        self.assertEqual(self.client.post(f"/api/v1/projects/{self.pid}/archive").status_code, 200)
        denied = self.stage(self.active_id, "shortlisted")
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(self.audit_count(), 0)
        self.assertEqual(self.history(self.active_id)["transitions"], [])
        self.assertEqual(self.client.post(f"/api/v1/projects/{self.pid}/restore").status_code, 200)
        self.assertEqual(self.stage(self.active_id, "shortlisted").status_code, 200)

    def test_batch_reports_failed_archived_candidate_and_advances_active_only(self):
        response = self.client.post(f"/api/v1/projects/{self.pid}/candidates/stage", json={
            "candidate_ids": [self.past_id, self.active_id], "stage": "shortlisted", "actor": "human"})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["updated"], result["failed"]), (1, 1))
        self.assertEqual(self.history(self.past_id)["transitions"], [])
        self.assertEqual(self.history(self.active_id)["current_stage"], "shortlisted")
        self.assertEqual(self.audit_count(), 1)

    def test_merged_source_identity_cannot_advance_pipeline(self):
        with self.factory.begin() as session:
            row = session.get(Candidate, self.past_id)
            row.merged_into_candidate_id = self.active_id
        rejected = self.stage(self.past_id, "shortlisted")
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(self.history(self.past_id)["transitions"], [])
        self.assertEqual(self.audit_count(), 0)


if __name__ == "__main__":
    unittest.main()
