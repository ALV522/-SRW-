from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.candidate.models import Candidate, MaterialRevision
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.work.models import WorkItem
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]


class Convergence11BusinessWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "test.db"
        self.data = self.root / "data"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{self.db.as_posix()}",
            data_dir=self.data,
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def _seed_work_item(self):
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        create_v1_schema(engine)
        factory = create_v1_session_factory(engine)
        try:
            with factory.begin() as session:
                project = Project(title="产品招聘", status="open")
                session.add(project)
                session.flush()
                protocol = ProtocolRevision(
                    project_id=project.id,
                    revision=1,
                    state="published",
                    payload_json=json.dumps(
                        {
                            "brief": {"title": "产品经理", "summary": ""},
                            "criteria": [],
                            "assessment_stages": [],
                            "decision_policy": {},
                        },
                        ensure_ascii=False,
                    ),
                    provenance_json="{}",
                    content_hash="p" * 64,
                )
                session.add(protocol)
                session.flush()
                project.current_protocol_revision_id = protocol.id

                candidate = Candidate(project_id=project.id, display_name="候选人甲")
                session.add(candidate)
                session.flush()
                material = MaterialRevision(
                    candidate_id=candidate.id,
                    revision=1,
                    source_set_hash="m" * 64,
                    provenance_json="{}",
                )
                session.add(material)
                session.flush()
                candidate.current_material_revision_id = material.id

                item = WorkItem(
                    project_id=project.id,
                    candidate_id=candidate.id,
                    criterion_key="experience",
                    criterion_name="相关经验",
                    protocol_revision_id=protocol.id,
                    material_revision_id=material.id,
                    type="VERIFY_CRITERION",
                    priority=10,
                    reason="缺少可确认的项目证据",
                    decision_context_hash="d" * 64,
                    state="open",
                )
                session.add(item)
                session.flush()
                return project.id, candidate.id, item.id
        finally:
            engine.dispose()

    def test_dashboard_surfaces_prioritized_candidate_work_item(self):
        project_id, candidate_id, work_item_id = self._seed_work_item()
        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        workbench = response.json()["decision_workbench"]
        self.assertEqual(workbench["total"], 1)
        self.assertEqual(workbench["verify_count"], 1)
        self.assertEqual(workbench["conflict_count"], 0)
        self.assertEqual(workbench["ready_count"], 0)
        self.assertEqual(len(workbench["items"]), 1)
        item = workbench["items"][0]
        self.assertEqual(item["work_item_id"], work_item_id)
        self.assertEqual(item["project_id"], project_id)
        self.assertEqual(item["candidate_id"], candidate_id)
        self.assertEqual(item["candidate_name"], "候选人甲")
        self.assertEqual(item["criterion_name"], "相关经验")
        self.assertEqual(item["action_type"], "VERIFY_CRITERION")

    def test_dashboard_empty_workbench_is_stable_contract(self):
        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        workbench = response.json()["decision_workbench"]
        self.assertEqual(workbench["items"], [])
        self.assertEqual(workbench["total"], 0)
        self.assertEqual(workbench["conflict_count"], 0)
        self.assertEqual(workbench["verify_count"], 0)
        self.assertEqual(workbench["ready_count"], 0)

    def test_frontend_exposes_actionable_queue_and_safe_diagnostic_export(self):
        app_js = (ROOT / "frontend" / "dist" / "app.js").read_text(encoding="utf-8")
        self.assertIn("今日业务队列", app_js)
        self.assertIn("openWorkbenchItem", app_js)
        self.assertIn("每位候选人只显示当前最高优先级动作", app_js)
        self.assertIn("/api/v1/system/diagnostics/export", app_js)
        self.assertIn("导出隐私安全诊断包", app_js)


if __name__ == "__main__":
    unittest.main()
