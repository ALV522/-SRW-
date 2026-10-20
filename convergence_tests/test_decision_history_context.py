"""P0 #41: historic human decisions must fail closed without an active context."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.candidate.models import Candidate, MaterialRevision
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.lineage import get_decision_history
from srw.modules.decision.models import HumanDecision
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory


class DecisionHistoryContextSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_v1_engine(
            f"sqlite+pysqlite:///{(Path(self.tmp.name) / 'synthetic.sqlite').as_posix()}"
        )
        self.addCleanup(self.engine.dispose)
        create_v1_schema(self.engine)
        self.factory = create_v1_session_factory(self.engine)
        with self.factory.begin() as session:
            self.project = Project(title="Synthetic context lifecycle", status="open")
            session.add(self.project)
            session.flush()
            self.protocol = ProtocolRevision(
                project_id=self.project.id, revision=1, state="published",
                payload_json=json.dumps({"criteria": [], "assessment_stages": [], "decision_policy": {}}),
                provenance_json="{}", content_hash="a" * 64,
            )
            session.add(self.protocol)
            session.flush()
            self.project.current_protocol_revision_id = self.protocol.id
            self.candidate = Candidate(project_id=self.project.id, display_name="Synthetic applicant")
            session.add(self.candidate)
            session.flush()
            self.material = MaterialRevision(
                candidate_id=self.candidate.id, revision=1,
                source_set_hash="b" * 64, provenance_json="{}",
            )
            session.add(self.material)
            session.flush()
            self.candidate.current_material_revision_id = self.material.id
            self.candidate_id = self.candidate.id
            self.project_id = self.project.id
            self.ctx_hash = get_current_decision_context(
                session, self.candidate_id, evaluation_policy_revision="default"
            ).hash
            session.add(HumanDecision(
                project_id=self.project_id, candidate_id=self.candidate_id,
                decision_context_hash=self.ctx_hash, decision="advance",
                reason="Human-reviewed synthetic evidence", actor="synthetic-human",
            ))

    def test_decision_is_current_only_with_active_published_context(self):
        with self.factory() as session:
            history = get_decision_history(session, self.candidate_id,
                                           evaluation_policy_revision="default")
            self.assertEqual(len(history), 1)
            self.assertTrue(history[0].is_current_context)
            self.assertFalse(history[0].stale)

    def test_no_active_protocol_marks_prior_decision_stale_not_ambiguous(self):
        with self.factory.begin() as session:
            session.get(Project, self.project_id).current_protocol_revision_id = None
        with self.factory() as session:
            history = get_decision_history(session, self.candidate_id,
                                           evaluation_policy_revision="default")
            self.assertEqual(len(history), 1)
            self.assertFalse(history[0].is_current_context)
            self.assertTrue(history[0].stale)
            self.assertEqual(history[0].decision_context_hash, self.ctx_hash)
            self.assertEqual(history[0].decision, "advance")

    def test_api_reports_stale_when_protocol_no_longer_current(self):
        with self.factory.begin() as session:
            session.get(Project, self.project_id).current_protocol_revision_id = None
        root = Path(self.tmp.name)
        knowledge = create_minimal_knowledge_tree(root / "knowledge" / "active")
        app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'synthetic.sqlite').as_posix()}",
            data_dir=root / "app-data", knowledge_dir=knowledge,
            frontend_dist=Path(__file__).resolve().parents[1] / "frontend" / "dist",
        )
        with TestClient(app) as client:
            response = client.get(f"/api/v1/candidates/{self.candidate_id}/decision-history")
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["decisions"][0]
        self.assertFalse(row["is_current_context"])
        self.assertTrue(row["stale"])
        self.assertEqual(row["decision"], "advance")

    def test_no_active_material_marks_prior_decision_stale(self):
        with self.factory.begin() as session:
            session.get(Candidate, self.candidate_id).current_material_revision_id = None
        with self.factory() as session:
            history = get_decision_history(session, self.candidate_id,
                                           evaluation_policy_revision="default")
            self.assertFalse(history[0].is_current_context)
            self.assertTrue(history[0].stale)


if __name__ == "__main__":
    unittest.main()
