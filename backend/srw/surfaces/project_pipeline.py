"""Project pipeline read model: funnel, offers, upcoming interviews and the derived next action.

Extracted from the HTTP layer (ADR-0002 slice 3); aggregation semantics are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from srw.modules.candidate.models import Candidate, Claim
from srw.modules.protocol.models import Project
from srw.modules.recruiting.models import OfferRecord
from srw.modules.recruiting.operations_models import InterviewScorecardSubmission
from srw.modules.fullworkbench import RecruitmentEvent
from srw.recruiting.operations import OFFER_STATES, project_funnel
from srw.surfaces.workbench import get_workbench


def get_project_pipeline(session, *, project_id: str, evaluation_policy_revision: str) -> dict:
    base=project_funnel(session,project_id)
    project=session.get(Project,project_id)
    offer_rows=session.execute(select(OfferRecord.status,func.count(OfferRecord.id)).where(OfferRecord.project_id==project_id).group_by(OfferRecord.status)).all()
    offers={status:0 for status in OFFER_STATES}
    for status,count in offer_rows: offers[str(status)]=int(count)
    now=datetime.now(timezone.utc)
    event_rows=session.execute(
        select(RecruitmentEvent,Candidate.display_name)
        .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
        .where(Candidate.project_id==project_id,RecruitmentEvent.event_state=="scheduled",RecruitmentEvent.scheduled_at.is_not(None),RecruitmentEvent.scheduled_at>=now)
        .order_by(RecruitmentEvent.scheduled_at,RecruitmentEvent.id).limit(20)
    ).all()
    scheduled=[{
        "event_id":event.id,"candidate_id":event.candidate_id,"candidate_name":name,
        "event_type":event.event_type,"title":event.title,"scheduled_at":event.scheduled_at.isoformat() if event.scheduled_at else None,
        "duration_minutes":event.duration_minutes,"interviewer":event.interviewer,"location":event.location,"event_state":event.event_state
    } for event,name in event_rows]
    active_candidates=session.scalar(
        select(func.count(Candidate.id)).where(Candidate.project_id==project_id,Candidate.archived.is_(False))
    ) or 0
    candidates_without_material=session.scalar(
        select(func.count(Candidate.id)).where(
            Candidate.project_id==project_id,
            Candidate.archived.is_(False),
            Candidate.current_material_revision_id.is_(None),
        )
    ) or 0
    unreviewed_claims=session.scalar(
        select(func.count(Claim.id))
        .join(Candidate,Candidate.id==Claim.candidate_id)
        .where(Candidate.project_id==project_id,Candidate.archived.is_(False),Claim.confirmation_state=="unreviewed")
    ) or 0
    pending_feedback=session.scalar(
        select(func.count(RecruitmentEvent.id))
        .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
        .where(
            Candidate.project_id==project_id,
            Candidate.archived.is_(False),
            RecruitmentEvent.event_state=="completed",
            RecruitmentEvent.event_type=="interview",
            ~RecruitmentEvent.id.in_(select(InterviewScorecardSubmission.event_id).where(InterviewScorecardSubmission.state=="submitted")),
        )
    ) or 0
    project_workbench=get_workbench(session,evaluation_policy_revision=evaluation_policy_revision,project_id=project_id).items
    decision_work=len(project_workbench)
    offer_followups=sum(int(offers.get(status,0) or 0) for status in ("draft","approved","sent"))
    stages=base.get("stages") or {}
    interview_flow=int(stages.get("shortlisted",0) or 0)+int(stages.get("phone_screen",0) or 0)+int(stages.get("interview",0) or 0)
    if not project or not project.current_protocol_revision_id:
        next_action={"key":"publish_criteria","label":"完善并发布招聘标准","tab":"criteria","reason":"当前项目还没有已发布的招聘标准；先固定岗位要求和评价口径。"}
    elif int(active_candidates)==0:
        next_action={"key":"intake_candidates","label":"导入首批候选人","tab":"candidates","reason":"招聘标准已经发布，但项目还没有在库候选人。"}
    elif int(candidates_without_material)>0:
        next_action={"key":"complete_materials","label":"补齐候选人材料","tab":"candidates","reason":f"{int(candidates_without_material)} 位候选人尚无当前材料版本。"}
    elif decision_work>0 or int(unreviewed_claims)>0:
        next_action={"key":"review_evidence","label":"处理证据与判断","tab":"cockpit","reason":f"{decision_work} 位候选人存在当前决策待办，{int(unreviewed_claims)} 条事实等待人工确认。"}
    elif int(pending_feedback)>0:
        next_action={"key":"submit_feedback","label":"提交面试反馈","tab":"flow","reason":f"{int(pending_feedback)} 场已完成面试仍缺少已提交 Scorecard。"}
    elif interview_flow>0 or len(scheduled)>0:
        next_action={"key":"advance_interviews","label":"推进电话筛选与面试","tab":"flow","reason":f"{interview_flow} 位候选人处于短名单/电话筛选/面试阶段；未来已排期 {len(scheduled)} 场。"}
    elif offer_followups>0:
        next_action={"key":"follow_up_offers","label":"跟进 Offer","tab":"candidates","reason":f"{offer_followups} 份 Offer 仍处于草案、已批准或已发送状态。"}
    else:
        next_action={"key":"continue_pipeline","label":"继续推进候选人","tab":"candidates","reason":"当前没有证据、反馈或 Offer 阻塞项；继续从候选人 Pipeline 推进。"}
    workflow_summary={
        "criteria_published":bool(project and project.current_protocol_revision_id),
        "candidate_count":int(active_candidates),
        "candidates_without_material":int(candidates_without_material),
        "decision_work_candidates":decision_work,
        "unreviewed_claims":int(unreviewed_claims),
        "pending_interview_feedback":int(pending_feedback),
        "upcoming_interviews":len(scheduled),
        "offer_followups":offer_followups,
        "next_action":next_action,
    }
    return {**base,"project_status":project.status if project else "","offers_by_status":offers,"upcoming_interviews":len(scheduled),"scheduled_events":scheduled,"workflow_summary":workflow_summary}

