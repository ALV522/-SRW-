from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate, CandidateContact
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import CriterionJudgment
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.operations_models import CandidateActionPlan, InterviewScorecardSubmission

PRIORITIES={"today","high","normal","low"}
CONTACT_STATUSES={"to_contact","attempted","callback","contacted","not_interested","waiting_material","done"}
SCORECARD_RATINGS={"strong","acceptable","concern","unknown"}


def _parse_dt(value: str | None):
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError as exc: raise V1InvariantError("next_contact_at must be ISO-8601") from exc


def update_job_setup(session: Session, project_id: str, body: dict) -> dict:
    project=session.get(Project,project_id)
    if project is None: raise V1NotFoundError(f"project not found: {project_id}")
    draft=session.scalar(select(ProtocolRevision).where(ProtocolRevision.project_id==project_id,ProtocolRevision.state=="draft").order_by(ProtocolRevision.revision.desc()).limit(1))
    if draft is None:
        draft=ProtocolRepository(session).fork_current_to_draft(project_id)
    payload=ProtocolRepository(session).get_payload(draft.id)
    ctx=dict(payload.get("recruitment_context") or {})
    fields=("role_title","location","level","employment_type","compensation","target_start_date","recruiter_owner","hiring_manager","jd_text")
    for key in fields:
        if key in body: ctx[key]=str(body.get(key) or "").strip()
    if "headcount" in body:
        try: headcount=int(body.get("headcount") or 0)
        except Exception as exc: raise V1InvariantError("headcount must be an integer") from exc
        if headcount<0: raise V1InvariantError("headcount must be non-negative")
        ctx["headcount"]=headcount
    payload["recruitment_context"]=ctx
    if ctx.get("role_title"):
        brief=dict(payload.get("brief") or {}); brief["title"]=ctx["role_title"]
        if ctx.get("jd_text"): brief["summary"]=ctx["jd_text"]
        payload["brief"]=brief
    ProtocolRepository(session).update_draft(draft.id,payload,{"action":"job_setup","actor":"human"})
    append_audit_event(session,event_type="JOB_SETUP_UPDATED",entity_type="project",entity_id=project_id,actor="human",payload={"fields":sorted(ctx)},project_id=project_id)
    return {"project_id":project_id,"revision_id":draft.id,"protocol_state":draft.state,"recruitment_context":ctx}


def suggest_job_setup(session: Session, project_id: str) -> dict:
    project=session.get(Project,project_id)
    if project is None: raise V1NotFoundError(f"project not found: {project_id}")
    draft=session.scalar(select(ProtocolRevision).where(ProtocolRevision.project_id==project_id,ProtocolRevision.state=="draft").order_by(ProtocolRevision.revision.desc()).limit(1))
    if draft is None: draft=ProtocolRepository(session).fork_current_to_draft(project_id)
    payload=ProtocolRepository(session).get_payload(draft.id)
    ctx=dict(payload.get("recruitment_context") or {})
    suggestions=[]
    if not payload.get("criteria"):
        role=ctx.get("role_title") or (payload.get("brief") or {}).get("title") or project.title
        suggestions=[{"name":f"{role}核心能力","definition":"请结合岗位实际人工完善定义与证据门槛","decision_critical":False,"verification_required":True,"verification_probes":["请提供可核实的具体案例"]}]
    return {"project_id":project_id,"revision_id":draft.id,"protocol_state":"draft","suggestions":suggestions,"note":"Suggestions are draft-only and require human review before publish."}


def upsert_action_plan(session: Session, candidate_id: str, body: dict) -> CandidateActionPlan:
    candidate=session.get(Candidate,candidate_id)
    if candidate is None: raise V1NotFoundError(f"candidate not found: {candidate_id}")
    row=session.scalar(select(CandidateActionPlan).where(CandidateActionPlan.candidate_id==candidate_id))
    if row is None:
        row=CandidateActionPlan(project_id=candidate.project_id,candidate_id=candidate_id);session.add(row)
    priority=str(body.get("priority",row.priority or "normal"))
    if priority not in PRIORITIES: raise V1InvariantError("unsupported contact priority")
    status=str(body.get("contact_status",row.contact_status or "to_contact"))
    if status not in CONTACT_STATUSES: raise V1InvariantError("unsupported contact status")
    row.priority=priority; row.contact_status=status
    if "owner" in body: row.owner=str(body.get("owner") or "").strip()
    if "reason" in body: row.reason=str(body.get("reason") or "").strip()
    if "last_result" in body: row.last_result=str(body.get("last_result") or "").strip()
    if "next_contact_at" in body: row.next_contact_at=_parse_dt(body.get("next_contact_at"))
    session.flush()
    append_audit_event(session,event_type="CANDIDATE_ACTION_PLAN_UPDATED",entity_type="candidate",entity_id=candidate_id,actor=str(body.get("actor") or "human"),payload={"priority":row.priority,"contact_status":row.contact_status},project_id=candidate.project_id,candidate_id=candidate_id)
    return row


def action_plan_view(row: CandidateActionPlan) -> dict:
    return {"candidate_id":row.candidate_id,"project_id":row.project_id,"priority":row.priority,"owner":row.owner,"contact_status":row.contact_status,"next_contact_at":row.next_contact_at.isoformat() if row.next_contact_at else None,"reason":row.reason,"last_result":row.last_result}


def contact_queue(session: Session, project_id: str, *, limit:int, offset:int) -> dict:
    total=len(session.scalars(select(Candidate.id).where(Candidate.project_id==project_id,Candidate.archived.is_(False))).all())
    rows=session.execute(
        select(Candidate,CandidateContact,CandidateActionPlan)
        .outerjoin(CandidateContact,CandidateContact.candidate_id==Candidate.id)
        .outerjoin(CandidateActionPlan,CandidateActionPlan.candidate_id==Candidate.id)
        .where(Candidate.project_id==project_id,Candidate.archived.is_(False))
        .order_by(CandidateActionPlan.next_contact_at.is_(None),CandidateActionPlan.next_contact_at,Candidate.created_at)
        .limit(limit).offset(offset)
    ).all()
    out=[]
    for c,contact,plan in rows:
        out.append({"candidate_id":c.id,"display_name":c.display_name,"pipeline_stage":c.pipeline_stage or "new","phone":contact.phone if contact else "","email":contact.email if contact else "","priority":plan.priority if plan else "normal","owner":plan.owner if plan else "","contact_status":plan.contact_status if plan else "to_contact","next_contact_at":plan.next_contact_at.isoformat() if plan and plan.next_contact_at else None,"reason":plan.reason if plan else ""})
    return {"project_id":project_id,"total":total,"limit":limit,"offset":offset,"priority_semantics":"contact_execution_priority_not_hiring_rank","candidates":out}


def phone_script(session: Session, candidate_id: str, *, evaluation_policy_revision: str) -> dict:
    candidate=session.get(Candidate,candidate_id)
    if candidate is None: raise V1NotFoundError(f"candidate not found: {candidate_id}")
    project=session.get(Project,candidate.project_id)
    protocol_id=project.current_protocol_revision_id if project else None
    payload=ProtocolRepository(session).get_payload(protocol_id) if protocol_id else {"criteria":[]}
    judgments={}
    if protocol_id and candidate.current_material_revision_id:
        ctx=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
        rows=session.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==candidate_id,CriterionJudgment.decision_context_hash==ctx.hash)).all()
        judgments={r.criterion_key:r for r in rows}
    questions=[]
    for item in payload.get("criteria") or []:
        if not isinstance(item,dict): continue
        key=str(item.get("criterion_key") or ""); j=judgments.get(key)
        if j is None or j.status in {"missing","partial","conflict"} or j.gap:
            probes=item.get("verification_probes") or [f"请核实：{item.get('name') or key}"]
            for q in probes[:2]: questions.append({"criterion_key":key,"question":str(q),"purpose":f"核实 {item.get('name') or key} 的证据与缺口"})
    questions.extend([
      {"criterion_key":"business_compensation","question":"请确认当前薪酬预期和可接受范围？","purpose":"确认薪酬业务条件，不作为自动录用评分。"},
      {"criterion_key":"business_location","question":"请确认工作地点/通勤安排是否可接受？","purpose":"确认地点可行性。"},
      {"criterion_key":"business_start","question":"最早到岗时间是什么时候？","purpose":"确认到岗窗口与招聘时效。"},
    ])
    return {"candidate_id":candidate_id,"questions":questions,"note":"Contact execution guidance only; not a hiring rank or automated decision."}


def validate_scorecard_feedback(value) -> list[dict]:
    if not isinstance(value,list) or not value: raise V1InvariantError("feedback must be a non-empty array")
    out=[]
    for item in value:
        if not isinstance(item,dict): raise V1InvariantError("scorecard feedback item must be an object")
        key=str(item.get("criterion_key") or "").strip(); rating=str(item.get("rating") or "").strip()
        if not key: raise V1InvariantError("criterion_key is required")
        if rating not in SCORECARD_RATINGS: raise V1InvariantError("unsupported scorecard rating")
        out.append({"criterion_key":key,"rating":rating,"observation":str(item.get("observation") or ""),"supporting_evidence":str(item.get("supporting_evidence") or ""),"counter_evidence":str(item.get("counter_evidence") or ""),"recommendation":str(item.get("recommendation") or "")})
    return out


def submit_scorecard(session: Session, event_id: str, body: dict) -> InterviewScorecardSubmission:
    event=session.get(RecruitmentEvent,event_id)
    if event is None: raise V1NotFoundError(f"event not found: {event_id}")
    candidate=session.get(Candidate,event.candidate_id)
    evaluator=str(body.get("evaluator") or "").strip()
    if not evaluator: raise V1InvariantError("evaluator is required")
    feedback=validate_scorecard_feedback(body.get("feedback"))
    row=session.scalar(select(InterviewScorecardSubmission).where(InterviewScorecardSubmission.event_id==event_id,InterviewScorecardSubmission.evaluator==evaluator))
    if row is None:
        row=InterviewScorecardSubmission(event_id=event_id,project_id=candidate.project_id,candidate_id=candidate.id,evaluator=evaluator);session.add(row)
    if row.state=="submitted": raise V1InvariantError("submitted scorecard is locked")
    row.feedback_json=json.dumps(feedback,ensure_ascii=False,separators=(",",":"));row.recommendation=str(body.get("recommendation") or "")
    if bool(body.get("submit")):
        row.state="submitted";row.submitted_at=utc_now()
    session.flush()
    append_audit_event(session,event_type="INTERVIEW_SCORECARD_SUBMITTED" if row.state=="submitted" else "INTERVIEW_SCORECARD_SAVED",entity_type="interview_scorecard",entity_id=row.id,actor=evaluator,payload={"event_id":event_id,"state":row.state},project_id=candidate.project_id,candidate_id=candidate.id)
    return row


def scorecards_view(session: Session, event_id: str) -> dict:
    event=session.get(RecruitmentEvent,event_id)
    if event is None: raise V1NotFoundError(f"event not found: {event_id}")
    rows=session.scalars(select(InterviewScorecardSubmission).where(InterviewScorecardSubmission.event_id==event_id).order_by(InterviewScorecardSubmission.created_at)).all()
    out=[]; by={}
    for row in rows:
        fb=json.loads(row.feedback_json or "[]");out.append({"scorecard_id":row.id,"evaluator":row.evaluator,"state":row.state,"recommendation":row.recommendation,"feedback":fb})
        for item in fb:
            k=item["criterion_key"];by.setdefault(k,[]).append(item["rating"])
    criteria={k:{"ratings":vals,"disagreement":len(set(vals))>1} for k,vals in by.items()}
    return {"event_id":event_id,"scorecards":out,"criteria":criteria,"note":"Independent evaluator opinions are preserved; no automatic average or consensus score is calculated."}
