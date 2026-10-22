from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.kernel.clock import utc_now
from srw.modules.candidate.models import Candidate, MaterialRevision, Claim, Source
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.recruiting.operations_models import CandidateActionPlan
from srw.modules.recruiting.models import OfferRecord
from srw.modules.fullworkbench import RecruitmentEvent, ReevaluationDraft
from srw.modules.identity.models import CandidateIdentityReview
from srw.modules.calibration.models import JudgmentReviewItem
from srw.modules.work.models import WorkItem
from srw.surfaces.daily_queue import local_day_end_utc
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]


def frontend_js() -> str:
    """Concatenated source of every module index.html loads (ADR-0002 split).

    UI-structure assertions describe the frontend as a product surface, not one file;
    after the domain split the code lives across shared/app/pages/jobsetup/protocol/
    candidates/events modules plus the convergence shims.
    """
    dist = ROOT / "frontend" / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")
    parts = []
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        parts.append((dist / src.rsplit("/", 1)[-1]).read_text(encoding="utf-8"))
    return "\n".join(parts)



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
                today_candidate = Candidate(project_id=project.id, display_name="今日联系候选人")
                feedback_candidate = Candidate(project_id=project.id, display_name="待反馈候选人")
                session.add_all([contact_candidate, today_candidate, feedback_candidate])
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
                today_plan = CandidateActionPlan(
                    project_id=project.id,
                    candidate_id=today_candidate.id,
                    priority="today",
                    owner="TA",
                    contact_status="to_contact",
                    next_contact_at=utc_now() + min(timedelta(minutes=1), (local_day_end_utc(utc_now()) - utc_now()) / 2),
                    reason="今日首次联系",
                )
                event = RecruitmentEvent(
                    candidate_id=feedback_candidate.id,
                    event_type="interview",
                    title="业务面试",
                    event_state="completed",
                    outcome="proceed",
                )
                session.add_all([plan, today_plan, event])
                session.flush()
                project_id = project.id
                contact_candidate_id = contact_candidate.id
                today_candidate_id = today_candidate.id
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
        self.assertIn("today_contact", by_kind)
        self.assertIn("pending_interview_feedback", by_kind)
        self.assertEqual(queue["total"], 3)
        self.assertEqual(by_kind["overdue_contact"]["project_id"], project_id)
        self.assertEqual(by_kind["overdue_contact"]["candidate_id"], contact_candidate_id)
        self.assertEqual(by_kind["today_contact"]["candidate_id"], today_candidate_id)
        self.assertEqual(by_kind["pending_interview_feedback"]["candidate_id"], feedback_candidate_id)
        self.assertEqual(by_kind["pending_interview_feedback"]["event_id"], event_id)

    def test_dashboard_active_funnel_offer_and_upcoming_exclude_archived_work(self):
        """Archiving a project must remove its candidates/Offers from active KPIs.

        Historical Offer, event and reevaluation rows remain persisted; only
        the *active operational* dashboard aggregation changes.  The same
        filtering applies to an individually archived candidate in an open
        project.  Avoid silently over-reporting the live recruiting funnel.
        """
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        create_v1_schema(engine)
        factory = create_v1_session_factory(engine)
        try:
            with factory.begin() as session:
                active = Project(title="进行中职位", status="open")
                archived = Project(title="历史归档职位", status="archived")
                session.add_all([active, archived])
                session.flush()
                current = Candidate(project_id=active.id, display_name="当前候选人", pipeline_stage="interview")
                historical = Candidate(project_id=archived.id, display_name="历史候选人", pipeline_stage="hired")
                excluded = Candidate(project_id=active.id, display_name="已归档候选人", archived=True, pipeline_stage="hired")
                session.add_all([current, historical, excluded])
                session.flush()
                for project, candidate in ((active, current), (archived, historical), (active, excluded)):
                    session.add(OfferRecord(project_id=project.id, candidate_id=candidate.id, status="draft", title="合成 Offer"))
                    session.add(RecruitmentEvent(candidate_id=candidate.id, event_type="interview", title="待进行面试", event_state="scheduled", scheduled_at=utc_now() + timedelta(days=1)))
                    session.add(ReevaluationDraft(candidate_id=candidate.id, state="stale", summary="历史复核任务"))
        finally:
            engine.dispose()

        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        dashboard = response.json()
        self.assertEqual(dashboard["metrics"]["projects"], 1)
        self.assertEqual(dashboard["metrics"]["candidates"], 1)
        self.assertEqual(dashboard["candidates_by_stage"]["interview"], 1)
        self.assertEqual(dashboard["candidates_by_stage"]["hired"], 0)
        self.assertEqual(dashboard["offers_by_status"]["draft"], 1)
        self.assertEqual(dashboard["upcoming_interviews"], 1)
        self.assertEqual(dashboard["operational_todos"]["stale_reevaluations"], 1)

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
                identity_id = identity.id
                judgment_id = judgment.id
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
        self.assertEqual(by_kind["identity_review"]["review_id"], identity_id)
        self.assertEqual(by_kind["judgment_review"]["review_id"], judgment_id)
        self.assertNotIn("历史候选人", json.dumps(queue, ensure_ascii=False))

    def test_project_pipeline_returns_operator_next_action(self):
        project_id, _candidate_id, _work_item_id = self._seed_work_item()
        with TestClient(self._app()) as client:
            active = client.get(f"/api/v1/projects/{project_id}/pipeline")
            self.assertEqual(active.status_code, 200, active.text)
            workflow = active.json()["workflow_summary"]
            self.assertTrue(workflow["criteria_published"])
            self.assertEqual(workflow["candidate_count"], 1)
            self.assertEqual(workflow["candidates_without_material"], 0)
            self.assertEqual(workflow["decision_work_candidates"], 1)
            self.assertEqual(workflow["next_action"]["key"], "review_evidence")
            self.assertEqual(workflow["next_action"]["tab"], "cockpit")

            created = client.post(
                "/api/v1/projects",
                json={"title":"空项目","role_title":"数据分析师","brief_summary":""},
            )
            self.assertEqual(created.status_code, 200, created.text)
            draft_project_id = created.json()["project_id"]
            draft = client.get(f"/api/v1/projects/{draft_project_id}/pipeline")
            self.assertEqual(draft.status_code, 200, draft.text)
            draft_workflow = draft.json()["workflow_summary"]
            self.assertFalse(draft_workflow["criteria_published"])
            self.assertEqual(draft_workflow["next_action"]["key"], "publish_criteria")
            self.assertEqual(draft_workflow["next_action"]["tab"], "criteria")

    def test_judgment_review_can_be_completed_from_product_api(self):
        project_id, candidate_id, _work_item_id = self._seed_work_item()
        with TestClient(self._app()) as client:
            created = client.post(
                f"/api/v1/projects/{project_id}/calibration/reviews",
                json={
                    "trigger":"human_override",
                    "criterion_key":"experience",
                    "before":"partial",
                    "after":"met",
                    "reason":"evidence_error",
                    "actor":"reviewer",
                    "candidate_id":candidate_id,
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            review_id = created.json()["review_id"]

            listed = client.get(f"/api/v1/projects/{project_id}/calibration/reviews?state=open")
            self.assertEqual(listed.status_code, 200, listed.text)
            rows = listed.json()["reviews"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["review_id"], review_id)
            self.assertEqual(rows[0]["candidate_name"], "候选人甲")

            resolved = client.post(
                f"/api/v1/calibration/reviews/{review_id}/resolve",
                json={"actor":"reviewer2","note":"已核对证据并完成纠错"},
            )
            self.assertEqual(resolved.status_code, 200, resolved.text)
            self.assertEqual(resolved.json()["state"], "resolved")

            open_rows = client.get(f"/api/v1/projects/{project_id}/calibration/reviews?state=open")
            self.assertEqual(open_rows.status_code, 200, open_rows.text)
            self.assertEqual(open_rows.json()["reviews"], [])

    def test_candidate_workspace_is_full_page_product_surface(self):
        app_js = frontend_js()
        styles = (ROOT / "frontend" / "dist" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("candidate-workspace-page", app_js)
        self.assertIn("candidate-workspace-tabs", app_js)
        self.assertIn("证据与判断", app_js)
        self.assertIn("流程与跟进", app_js)
        self.assertIn("closeCandidateWorkspace", app_js)
        self.assertIn("setCandidateSection", app_js)
        self.assertIn("candidate-workspace-page", styles)
        self.assertIn("candidate-workspace-head", styles)

    def test_candidate_process_workspace_contains_interview_and_reevaluation_actions(self):
        app_js = frontend_js()
        self.assertIn("candidateEventsHtml", app_js)
        self.assertIn("candidateReevaluationHtml", app_js)
        self.assertIn("电话筛选与面试", app_js)
        self.assertIn("复评与上下文变化", app_js)
        self.assertIn("独立 Scorecard", app_js)
        self.assertIn("完成并反馈", app_js)
        self.assertIn("＋ 复评草案", app_js)

    def test_job_setup_is_a_real_four_step_draft_wizard(self):
        app_js = frontend_js()
        styles = (ROOT / "frontend" / "dist" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("jobSetupProgress", app_js)
        self.assertIn("jobSetupMove", app_js)
        self.assertIn("岗位基本信息", app_js)
        self.assertIn("用工与计划", app_js)
        self.assertIn("责任人与业务背景", app_js)
        self.assertIn("确认建岗草案", app_js)
        self.assertIn("applyJobSetupSuggestions", app_js)
        self.assertIn("不会自动发布", app_js)
        self.assertIn("wizard-steps", styles)

    def test_protocol_draft_roundtrip_keeps_job_context_and_stage_semantics(self):
        with TestClient(self._app()) as client:
            created = client.post(
                "/api/v1/projects",
                json={"title":"语义保留项目","role_title":"产品经理","brief_summary":"负责增长产品"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            project_id = created.json()["project_id"]

            setup = client.patch(
                f"/api/v1/projects/{project_id}/job-setup",
                json={
                    "role_title":"高级产品经理",
                    "headcount":2,
                    "location":"上海",
                    "level":"Senior",
                    "employment_type":"full_time",
                    "compensation":"面议",
                    "target_start_date":"2027-01-15",
                    "recruiter_owner":"TA-A",
                    "hiring_manager":"HM-B",
                    "jd_text":"负责核心产品与跨团队协作",
                },
            )
            self.assertEqual(setup.status_code, 200, setup.text)

            workspace = client.get(f"/api/v1/projects/{project_id}/protocol-workspace")
            self.assertEqual(workspace.status_code, 200, workspace.text)
            draft = workspace.json()["draft"]
            revision_id = workspace.json()["draft_revision_id"]
            context = draft["recruitment_context"]
            self.assertEqual(context["headcount"], 2)
            self.assertEqual(context["hiring_manager"], "HM-B")

            payload = {
                "brief": dict(draft["brief"]),
                "criteria": [{
                    "criterion_key":"product_impact",
                    "name":"产品影响力",
                    "definition":"能够用可验证结果说明产品影响",
                    "weight":2.5,
                    "decision_critical":True,
                    "verification_required":True,
                    "verification_probes":["请说明一个有量化结果的产品案例"],
                    "custom_metadata":{"preserve":True},
                }],
                "assessment_stages":[
                    {"stage_key":"resume","name":"简历筛选","criteria":["product_impact"],"custom_stage_field":"keep"},
                    {"stage_key":"interview","name":"面试","criteria":["product_impact"]},
                ],
                "decision_policy":{"human_final":True,"custom_policy":"keep"},
                "recruitment_context":dict(context),
            }
            saved = client.patch(
                f"/api/v1/protocol-revisions/{revision_id}",
                json={"payload":payload,"provenance":{"ui":"test"}},
            )
            self.assertEqual(saved.status_code, 200, saved.text)

            reread = client.get(f"/api/v1/projects/{project_id}/protocol-workspace")
            self.assertEqual(reread.status_code, 200, reread.text)
            result = reread.json()["draft"]
            self.assertEqual(result["recruitment_context"]["location"], "上海")
            self.assertEqual(result["criteria"][0]["weight"], 2.5)
            self.assertTrue(result["criteria"][0]["custom_metadata"]["preserve"])
            self.assertEqual(result["assessment_stages"][0]["criteria"], ["product_impact"])
            self.assertEqual(result["assessment_stages"][0]["custom_stage_field"], "keep")
            self.assertEqual(result["decision_policy"]["custom_policy"], "keep")

    def test_criteria_editor_preserves_protocol_fields_instead_of_rebuilding_them(self):
        app_js = frontend_js()
        styles = (ROOT / "frontend" / "dist" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("criteriaOriginalByKey", app_js)
        self.assertIn("criteriaRecruitmentContext", app_js)
        self.assertIn("criteriaDecisionPolicy", app_js)
        self.assertIn("collectAssessmentStages", app_js)
        self.assertIn("recruitment_context:{...state.criteriaRecruitmentContext}", app_js)
        self.assertIn("decision_policy:{...state.criteriaDecisionPolicy,human_final:true}", app_js)
        self.assertIn("...(state.criteriaOriginalByKey[criterion_key]||{})", app_js)
        self.assertIn("标准定义 / 判断口径", app_js)
        self.assertIn("权重", app_js)
        self.assertIn("核实阶段", app_js)
        self.assertIn("criterion-card", styles)

    def test_calendar_today_ends_at_local_midnight_not_rolling_24_hours(self):
        # 23:45 in UTC+8 on Oct 17; only 15 minutes remain in the local day.
        local_zone = timezone(timedelta(hours=8))
        now = datetime(2026, 10, 17, 15, 45, tzinfo=timezone.utc)
        self.assertEqual(
            local_day_end_utc(now, zone=local_zone),
            datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc),
        )
        self.assertLess(local_day_end_utc(now, zone=local_zone) - now, timedelta(hours=1))
        self.assertEqual(
            local_day_end_utc(now, zone=timezone.utc),
            datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            local_day_end_utc(datetime(2026, 10, 17, 15, 45))

    def test_priority_queue_ranks_conflicts_and_ignores_archived_projects(self):
        project_id, candidate_id, _work_item_id = self._seed_work_item()
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        factory = create_v1_session_factory(engine)
        try:
            with factory.begin() as session:
                active_project = session.get(Project, project_id)
                conflict = Candidate(project_id=project_id, display_name="ZZZ 冲突候选人")
                session.add(conflict)
                session.flush()
                material = MaterialRevision(
                    candidate_id=conflict.id, revision=1, source_set_hash="b" * 64, provenance_json="{}"
                )
                session.add(material)
                session.flush()
                conflict.current_material_revision_id = material.id
                session.add(WorkItem(
                    project_id=project_id, candidate_id=conflict.id,
                    criterion_key="experience", criterion_name="相关经验",
                    protocol_revision_id=active_project.current_protocol_revision_id,
                    material_revision_id=material.id, type="RESOLVE_CONFLICT",
                    priority=10, reason="发现证据冲突", decision_context_hash="b" * 64, state="open",
                ))

                archived = Project(title="归档招聘项目", status="archived")
                session.add(archived)
                session.flush()
                protocol = ProtocolRevision(
                    project_id=archived.id, revision=1, state="published",
                    payload_json='{"criteria":[]}', provenance_json="{}", content_hash="a" * 64,
                )
                session.add(protocol)
                session.flush()
                archived.current_protocol_revision_id = protocol.id
                old_candidate = Candidate(project_id=archived.id, display_name="AAA 历史候选人")
                session.add(old_candidate)
                session.flush()
                old_material = MaterialRevision(
                    candidate_id=old_candidate.id, revision=1,
                    source_set_hash="a" * 64, provenance_json="{}",
                )
                session.add(old_material)
                session.flush()
                old_candidate.current_material_revision_id = old_material.id
                session.add(WorkItem(
                    project_id=archived.id, candidate_id=old_candidate.id,
                    criterion_key="old", criterion_name="归档判断",
                    protocol_revision_id=protocol.id, material_revision_id=old_material.id,
                    type="RESOLVE_CONFLICT", priority=0,
                    reason="不应出现在活动队列", decision_context_hash="a" * 64,
                    state="open",
                ))
        finally:
            engine.dispose()
        with TestClient(self._app()) as client:
            response = client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        wb = response.json()["decision_workbench"]
        self.assertEqual(wb["total"], 2)
        self.assertEqual(wb["conflict_count"], 1)
        self.assertEqual(wb["items"][0]["action_type"], "RESOLVE_CONFLICT")
        self.assertEqual(wb["items"][1]["candidate_id"], candidate_id)
        self.assertTrue(all(x["project_id"] == project_id for x in wb["items"]))

    def test_review_shortcuts_target_the_exact_record_not_just_the_page(self):
        app_js = frontend_js()
        styles = (ROOT / "frontend" / "dist" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("openReviewItem=async(kind,pid,cid,reviewId='',claimId='')", app_js)
        self.assertIn("'srw-review-'+reviewId", app_js)
        self.assertIn("'srw-claim-'+claimId", app_js)
        self.assertIn('id="srw-review-${esc(x.review_id)}"', app_js)
        self.assertIn('id="srw-claim-${esc(c.claim_id)}"', app_js)
        self.assertIn("review-item-focused", app_js)
        self.assertIn("review-item-focused", styles)

    def test_frontend_exposes_actionable_queue_and_safe_diagnostic_export(self):
        app_js = frontend_js()
        self.assertIn("今日业务队列", app_js)
        self.assertIn("openWorkbenchItem", app_js)
        self.assertIn("每位候选人只显示当前最高优先级动作", app_js)
        self.assertIn("运营执行队列", app_js)
        self.assertIn("openOperationalItem", app_js)
        self.assertIn("复核中心", app_js)
        self.assertIn("openReviewItem", app_js)
        self.assertIn("项目推进", app_js)
        self.assertIn("建岗与标准", app_js)
        self.assertIn("候选人收件", app_js)
        self.assertIn("筛选与决策", app_js)
        self.assertIn("完成复核", app_js)
        self.assertIn("resolveJudgmentReview", app_js)
        self.assertIn("证据错误", app_js)
        self.assertIn("candidateBriefHtml", app_js)
        self.assertIn("handoffHtml", app_js)
        self.assertIn("下载完整交接 JSON", app_js)
        self.assertIn("/api/v1/system/diagnostics/export", app_js)
        self.assertIn("导出隐私安全诊断包", app_js)


if __name__ == "__main__":
    unittest.main()
