from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.kernel.clock import utc_now
from srw.modules.candidate.models import Candidate, MaterialRevision, Claim, Source
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.recruiting.operations_models import CandidateActionPlan
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.identity.models import CandidateIdentityReview
from srw.modules.calibration.models import JudgmentReviewItem
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

    def test_dashboard_operational_queue_links_execution_work(self):
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        create_v1_schema(engine)
        factory = create_v1_session_factory(engine)
        try:
            with factory.begin() as session:
                project = Project(title="运营招聘", status="open")
                session.add(project)
                session.flush()
                contact_candidate = Candidate(project_id=project.id, display_name="待联系候选人")
                feedback_candidate = Candidate(project_id=project.id, display_name="待反馈候选人")
                session.add_all([contact_candidate, feedback_candidate])
                session.flush()
                plan = CandidateActionPlan(
                    project_id=project.id,
                    candidate_id=contact_candidate.id,
                    priority="today",
                    owner="TA",
                    contact_status="callback",
                    next_contact_at=utc_now() - timedelta(days=1),
                    reason="候选人要求回拨",
                )
                event = RecruitmentEvent(
                    candidate_id=feedback_candidate.id,
                    event_type="interview",
                    title="业务面试",
                    event_state="completed",
                    outcome="proceed",
                )
                session.add_all([plan, event])
                session.flush()
                project_id = project.id
                contact_candidate_id = contact_candidate.id
                feedback_candidate_id = feedback_candidate.id
                event_id = event.id
        finally:
            engine.dispose()

        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        queue = response.json()["operational_queue"]
        by_kind = {item["kind"]: item for item in queue["items"]}
        self.assertIn("overdue_contact", by_kind)
        self.assertIn("pending_interview_feedback", by_kind)
        self.assertEqual(by_kind["overdue_contact"]["project_id"], project_id)
        self.assertEqual(by_kind["overdue_contact"]["candidate_id"], contact_candidate_id)
        self.assertEqual(by_kind["pending_interview_feedback"]["candidate_id"], feedback_candidate_id)
        self.assertEqual(by_kind["pending_interview_feedback"]["event_id"], event_id)

    def test_dashboard_review_center_links_identity_judgment_and_claim_review(self):
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        create_v1_schema(engine)
        factory = create_v1_session_factory(engine)
        try:
            with factory.begin() as session:
                project = Project(title="复核招聘", status="open")
                archived_project = Project(title="已归档招聘", status="archived")
                session.add_all([project, archived_project])
                session.flush()

                candidate_a = Candidate(project_id=project.id, display_name="候选人甲")
                candidate_b = Candidate(project_id=project.id, display_name="候选人乙")
                archived_candidate = Candidate(project_id=archived_project.id, display_name="历史候选人")
                session.add_all([candidate_a, candidate_b, archived_candidate])
                session.flush()

                identity = CandidateIdentityReview(
                    project_id=project.id,
                    candidate_a_id=candidate_a.id,
                    candidate_b_id=candidate_b.id,
                    match_reason="exact_email",
                    match_value_hash="i" * 64,
                    source="deterministic_contact",
                    status="pending",
                )
                judgment = JudgmentReviewItem(
                    project_id=project.id,
                    candidate_id=candidate_a.id,
                    trigger="human_override",
                    criterion_key="experience",
                    before="partial",
                    after="met",
                    reason="evidence_error",
                    error_class="evidence_error",
                    actor="reviewer",
                    state="open",
                )
                source = Source(
                    candidate_id=candidate_a.id,
                    source_kind="resume",
                    content_hash="c" * 64,
                    media_type="text/plain",
                    text_content="负责招聘项目并完成交付。",
                    metadata_json="{}",
                )
                archived_source = Source(
                    candidate_id=archived_candidate.id,
                    source_kind="resume",
                    content_hash="a" * 64,
                    media_type="text/plain",
                    text_content="历史材料",
                    metadata_json="{}",
                )
                session.add_all([identity, judgment, source, archived_source])
                session.flush()
                claim = Claim(
                    candidate_id=candidate_a.id,
                    source_id=source.id,
                    normalized_text="负责招聘项目并完成交付",
                    claim_hash="d" * 64,
                    source_locator_json="{}",
                    proposal_metadata_json="{}",
                    authority="source",
                    confirmation_state="unreviewed",
                )
                archived_claim = Claim(
                    candidate_id=archived_candidate.id,
                    source_id=archived_source.id,
                    normalized_text="不应进入当前复核中心",
                    claim_hash="e" * 64,
                    source_locator_json="{}",
                    proposal_metadata_json="{}",
                    authority="source",
                    confirmation_state="unreviewed",
                )
                session.add_all([claim, archived_claim])
                session.flush()
                project_id = project.id
                candidate_id = candidate_a.id
                claim_id = claim.id
        finally:
            engine.dispose()

        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        queue = payload["review_queue"]
        self.assertEqual(queue["identity_count"], 1)
        self.assertEqual(queue["judgment_count"], 1)
        self.assertEqual(queue["claim_count"], 1)
        self.assertEqual(queue["total"], 3)
        self.assertEqual(payload["evidence_review_backlog"], 1)
        by_kind = {item["kind"]: item for item in queue["items"]}
        self.assertEqual(set(by_kind), {"identity_review", "judgment_review", "unreviewed_claim"})
        self.assertEqual(by_kind["unreviewed_claim"]["project_id"], project_id)
        self.assertEqual(by_kind["unreviewed_claim"]["candidate_id"], candidate_id)
        self.assertEqual(by_kind["unreviewed_claim"]["claim_id"], claim_id)
        self.assertNotIn("历史候选人", json.dumps(queue, ensure_ascii=False))

    def test_frontend_exposes_actionable_queue_and_safe_diagnostic_export(self):
        app_js = (ROOT / "frontend" / "dist" / "app.js").read_text(encoding="utf-8")
        self.assertIn("今日业务队列", app_js)
        self.assertIn("openWorkbenchItem", app_js)
        self.assertIn("每位候选人只显示当前最高优先级动作", app_js)
        self.assertIn("运营执行队列", app_js)
        self.assertIn("openOperationalItem", app_js)
        self.assertIn("复核中心", app_js)
        self.assertIn("openReviewItem", app_js)
        self.assertIn("/api/v1/system/diagnostics/export", app_js)
        self.assertIn("导出隐私安全诊断包", app_js)


if __name__ == "__main__":
    unittest.main()
