"""Project pipeline read model: next-action derivation and the thin HTTP adapter.

Covers the extracted get_project_pipeline surface (ADR-0002 slice 3) with synthetic
SQLite workspaces; no knowledge DB files and no network are touched.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.kernel.hashing import content_hash
from srw.modules.candidate.commands import add_source, create_candidate
from srw.modules.candidate.repository import MaterialRepository
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
from srw.surfaces.project_pipeline import get_project_pipeline

_DRAFT_PAYLOAD = {
    "brief": {"title": "Synthetic role", "summary": ""},
    "recruitment_context": {"role_title": "Synthetic role", "location": "北京"},
    "criteria": [],
    "assessment_stages": [],
    "decision_policy": {"human_final": True},
}

_POLICY = "policy.v1"


class ProjectPipelineSurfaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        engine = create_v1_engine(f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}")
        self.addCleanup(engine.dispose)
        create_v1_schema(engine)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as session:
            project = Project(title="Synthetic role")
            session.add(project)
            session.flush()
            self.pid = project.id

    def _publish_protocol(self):
        with self.factory.begin() as session:
            repo = ProtocolRepository(session)
            draft = repo.create_draft(self.pid, dict(_DRAFT_PAYLOAD))
            repo.publish(draft.id)

    def _add_candidate(self, name="Synthetic person", *, with_material=False):
        with self.factory.begin() as session:
            candidate = create_candidate(session, self.pid, name)
            if with_material:
                source = add_source(
                    session,
                    candidate.id,
                    source_kind="resume",
                    content_hash=content_hash({"synthetic": name}),
                    text_content="Synthetic resume text",
                )
                MaterialRepository(session).publish_revision(
                    candidate.id, [source.id], {"origin": "synthetic-test"}
                )
            return candidate.id

    def _next_action(self):
        with self.factory() as session:
            return get_project_pipeline(
                session, project_id=self.pid, evaluation_policy_revision=_POLICY
            )["workflow_summary"]["next_action"]

    def test_next_action_asks_to_publish_criteria_first(self):
        action = self._next_action()
        self.assertEqual(action["key"], "publish_criteria")
        self.assertEqual(action["tab"], "criteria")

    def test_next_action_asks_for_candidates_after_publish(self):
        self._publish_protocol()
        action = self._next_action()
        self.assertEqual(action["key"], "intake_candidates")
        self.assertTrue(self._pipeline()["workflow_summary"]["criteria_published"])

    def test_next_action_asks_to_complete_materials(self):
        self._publish_protocol()
        self._add_candidate()
        action = self._next_action()
        self.assertEqual(action["key"], "complete_materials")
        self.assertEqual(self._pipeline()["workflow_summary"]["candidates_without_material"], 1)

    def test_next_action_continues_pipeline_when_nothing_blocks(self):
        self._publish_protocol()
        self._add_candidate(with_material=True)
        action = self._next_action()
        self.assertEqual(action["key"], "continue_pipeline")
        summary = self._pipeline()["workflow_summary"]
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["candidates_without_material"], 0)
        self.assertEqual(summary["decision_work_candidates"], 0)
        self.assertEqual(summary["unreviewed_claims"], 0)

    def test_pipeline_shape_is_preserved(self):
        self._publish_protocol()
        self._add_candidate(with_material=True)
        payload = self._pipeline()
        for key in (
            "stages",
            "project_status",
            "offers_by_status",
            "upcoming_interviews",
            "scheduled_events",
            "workflow_summary",
        ):
            self.assertIn(key, payload)
        self.assertEqual(set(payload["offers_by_status"]), {"draft", "approved", "sent", "accepted", "declined", "withdrawn"})
        self.assertEqual(payload["upcoming_interviews"], 0)
        self.assertEqual(payload["scheduled_events"], [])

    def _pipeline(self):
        with self.factory() as session:
            return get_project_pipeline(session, project_id=self.pid, evaluation_policy_revision=_POLICY)


class ProjectPipelineHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.url = f"sqlite+pysqlite:///{(self.root / 'synthetic.db').as_posix()}"
        app = create_v1_app(
            self.url,
            data_dir=self.root / "data",
            knowledge_dir=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
        )
        self.client = self.enterContext(TestClient(app))

    def _create_project(self):
        response = self.client.post(
            "/api/v1/projects", json={"title": "Synthetic role", "role_title": "Synthetic engineer"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["project_id"]

    def test_pipeline_route_returns_next_action(self):
        pid = self._create_project()
        response = self.client.get(f"/api/v1/projects/{pid}/pipeline")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["workflow_summary"]["next_action"]["key"], "publish_criteria")
        self.assertIn("stages", body)
        self.assertIn("offers_by_status", body)

    def test_pipeline_route_unknown_project_is_404(self):
        response = self.client.get("/api/v1/projects/no-such-project/pipeline")
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
