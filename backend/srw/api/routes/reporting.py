"""Reporting and read-model routes (ADR-0002 R2, ninth slice).

Six read surfaces: project cockpit, project pipeline, candidates CSV export,
candidate brief, project handoff and the candidate comparison view, plus the
shared ``_brief_payload`` projection they all use.

This slice exists because that projection cannot be split: brief, handoff and the
cockpit all build on it. Moving any one of them alone would have relocated the
helper instead of removing it from the aggregate.

Behaviour is identical to the code that lived inside
``install_full_workbench_routes``. Read models do not write state; the only
side-effect-bearing line is the CSV export, which streams through the same
formula-neutralising path as the contact list.

Dependency note: the assessment projection and the protocol repository lookups are
Core services, not transport concerns - this module only shapes their output.
"""
from __future__ import annotations

import csv
import json
from io import StringIO

from sqlalchemy import case, func, select
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from srw.api.http_utils import json_body as _json_body, s_field as _s
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import decision_context_hash
from srw.modules.candidate.models import Candidate, CandidateContact, Claim
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import CriterionJudgment
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.models import OfferRecord
from srw.modules.recruiting.operations_models import CandidateActionPlan, InterviewScorecardSubmission
from srw.recruiting.operations import OFFER_STATES, project_funnel
from srw.surfaces.workbench import get_workbench
from srw.recruiting.workbench import action_plan_view
from srw.runtime.db.session import v1_session_scope


def reporting_routes(*, factory, evaluation_policy_revision: str) -> list[Route]:
    """Bind the reporting endpoints to one Core session factory."""

    def _brief_payload(s,cid):
        candidate=s.get(Candidate,cid)
        if candidate is None: raise V1NotFoundError(f"candidate not found: {cid}")
        project=s.get(Project,candidate.project_id)
        protocol_id=project.current_protocol_revision_id if project else None
        ctx_hash=""
        judgments=[]
        if protocol_id and candidate.current_material_revision_id:
            ctx=get_current_decision_context(s,cid,evaluation_policy_revision=evaluation_policy_revision);ctx_hash=ctx.hash
            judgments=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==cid,CriterionJudgment.decision_context_hash==ctx.hash)).all()
        contact=s.scalar(select(CandidateContact).where(CandidateContact.candidate_id==cid))
        plan=s.scalar(select(CandidateActionPlan).where(CandidateActionPlan.candidate_id==cid))
        return {"candidate_id":cid,"project_id":candidate.project_id,"display_name":candidate.display_name,"pipeline_stage":candidate.pipeline_stage or "new","contact":{"phone":contact.phone if contact else "","email":contact.email if contact else "","user_confirmed":bool(contact.user_confirmed) if contact else False},"action_plan":action_plan_view(plan) if plan else None,"criteria":[{"criterion_key":j.criterion_key,"status":j.status,"evidence_level":j.evidence_level,"reason":j.reason,"gap":j.gap} for j in judgments],"version_context":{"protocol_revision_id":protocol_id or "","material_revision_id":candidate.current_material_revision_id or "","evaluation_policy_revision":evaluation_policy_revision,"decision_context_hash":ctx_hash}}
    async def cockpit(r):
        pid=r.path_params["project_id"]
        try: limit=min(100,max(1,int(r.query_params.get("limit","25"))));offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc: raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as s:
            if s.get(Project,pid) is None: raise V1NotFoundError(f"project not found: {pid}")
            total=s.scalar(select(func.count(Candidate.id)).where(Candidate.project_id==pid,Candidate.archived.is_(False))) or 0
            claim_counts=(select(Claim.candidate_id.label("cid"),func.sum(case((Claim.confirmation_state=="confirmed",1),else_=0)).label("confirmed"),func.sum(case((Claim.confirmation_state=="unreviewed",1),else_=0)).label("unreviewed")).group_by(Claim.candidate_id).subquery())
            judgment_counts=(select(CriterionJudgment.candidate_id.label("cid"),func.count(CriterionJudgment.id).label("judgments")).group_by(CriterionJudgment.candidate_id).subquery())
            rows=s.execute(select(Candidate,func.coalesce(claim_counts.c.confirmed,0),func.coalesce(claim_counts.c.unreviewed,0),func.coalesce(judgment_counts.c.judgments,0)).outerjoin(claim_counts,claim_counts.c.cid==Candidate.id).outerjoin(judgment_counts,judgment_counts.c.cid==Candidate.id).where(Candidate.project_id==pid,Candidate.archived.is_(False)).order_by(Candidate.created_at.desc(),Candidate.id).limit(limit).offset(offset)).all()
            output=[]
            for c,a,b,j in rows:
                assessment=None
                if c.current_material_revision_id:
                    try: assessment=get_candidate_assessment(s,c.id,evaluation_policy_revision=evaluation_policy_revision)
                    except Exception: assessment=None
                output.append({"candidate_id":c.id,"display_name":c.display_name,"pipeline_stage":c.pipeline_stage or "new","has_material":bool(c.current_material_revision_id),"confirmed_claims":int(a or 0),"unreviewed_claims":int(b or 0),"judgments":int(j or 0),"assessment":assessment})
            return JSONResponse({"candidates":output,"total":int(total),"limit":limit,"offset":offset})
    async def project_pipeline(r):
        from datetime import datetime, timezone
        pid=r.path_params["project_id"]
        with factory() as s:
            base=project_funnel(s,pid)
            project=s.get(Project,pid)
            offer_rows=s.execute(select(OfferRecord.status,func.count(OfferRecord.id)).where(OfferRecord.project_id==pid).group_by(OfferRecord.status)).all()
            offers={status:0 for status in OFFER_STATES}
            for status,count in offer_rows: offers[str(status)]=int(count)
            now=datetime.now(timezone.utc)
            event_rows=s.execute(
                select(RecruitmentEvent,Candidate.display_name)
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .where(Candidate.project_id==pid,RecruitmentEvent.event_state=="scheduled",RecruitmentEvent.scheduled_at.is_not(None),RecruitmentEvent.scheduled_at>=now)
                .order_by(RecruitmentEvent.scheduled_at,RecruitmentEvent.id).limit(20)
            ).all()
            scheduled=[{
                "event_id":event.id,"candidate_id":event.candidate_id,"candidate_name":name,
                "event_type":event.event_type,"title":event.title,"scheduled_at":event.scheduled_at.isoformat() if event.scheduled_at else None,
                "duration_minutes":event.duration_minutes,"interviewer":event.interviewer,"location":event.location,"event_state":event.event_state
            } for event,name in event_rows]
            active_candidates=s.scalar(
                select(func.count(Candidate.id)).where(Candidate.project_id==pid,Candidate.archived.is_(False))
            ) or 0
            candidates_without_material=s.scalar(
                select(func.count(Candidate.id)).where(
                    Candidate.project_id==pid,
                    Candidate.archived.is_(False),
                    Candidate.current_material_revision_id.is_(None),
                )
            ) or 0
            unreviewed_claims=s.scalar(
                select(func.count(Claim.id))
                .join(Candidate,Candidate.id==Claim.candidate_id)
                .where(Candidate.project_id==pid,Candidate.archived.is_(False),Claim.confirmation_state=="unreviewed")
            ) or 0
            pending_feedback=s.scalar(
                select(func.count(RecruitmentEvent.id))
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .where(
                    Candidate.project_id==pid,
                    Candidate.archived.is_(False),
                    RecruitmentEvent.event_state=="completed",
                    RecruitmentEvent.event_type=="interview",
                    ~RecruitmentEvent.id.in_(select(InterviewScorecardSubmission.event_id).where(InterviewScorecardSubmission.state=="submitted")),
                )
            ) or 0
            project_workbench=get_workbench(s,evaluation_policy_revision=evaluation_policy_revision,project_id=pid).items
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
            return JSONResponse({**base,"project_status":project.status if project else "","offers_by_status":offers,"upcoming_interviews":len(scheduled),"scheduled_events":scheduled,"workflow_summary":workflow_summary})
    async def candidates_csv(r):
        import csv
        from io import StringIO
        from datetime import datetime, timezone
        pid=r.path_params["project_id"]
        def safe_cell(value):
            text="" if value is None else str(value)
            return "'"+text if text[:1] in ("=","+","-","@") else text
        with factory() as s:
            project=s.get(Project,pid)
            if project is None: raise V1NotFoundError(f"project not found: {pid}")
            protocol_id=project.current_protocol_revision_id or ""
            protocol_payload=ProtocolRepository(s).get_payload(protocol_id) if protocol_id else {"criteria":[]}
            definitions=[x for x in (protocol_payload.get("criteria") or []) if isinstance(x,dict)]
            rows=s.scalars(select(Candidate).where(Candidate.project_id==pid).order_by(Candidate.created_at,Candidate.id)).all()
            ids=[x.id for x in rows]
            contacts={x.candidate_id:x for x in s.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(ids))).all()} if ids else {}
            offers_by_candidate={}
            if ids:
                for offer in s.scalars(select(OfferRecord).where(OfferRecord.candidate_id.in_(ids)).order_by(OfferRecord.created_at.desc(),OfferRecord.id.desc())).all(): offers_by_candidate.setdefault(offer.candidate_id,offer)
            all_j=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(ids))).all() if ids else []
            by_candidate={}
            for x in rows:
                if not protocol_id or not x.current_material_revision_id: continue
                h=decision_context_hash(protocol_id,x.current_material_revision_id,evaluation_policy_revision)
                by_candidate[x.id]={j.criterion_key:j for j in all_j if j.candidate_id==x.id and j.decision_context_hash==h}
            generated=datetime.now(timezone.utc).isoformat()
            fields=["candidate_id","display_name","pipeline_stage","archived","has_material","phone","email","contact_confirmed","offer_status","protocol_revision_id","evaluation_policy_revision","criteria_summary","evidence_gaps","created_at","generated_at"]
            out=StringIO(); w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
            for x in rows:
                contact=contacts.get(x.id); offer=offers_by_candidate.get(x.id); js=by_candidate.get(x.id,{})
                summaries=[]; gaps=[]
                for d in definitions:
                    key=str(d.get("criterion_key") or ""); name=str(d.get("name") or key); j=js.get(key)
                    status=j.status if j else "missing"; evidence=j.evidence_level if j else "none"
                    summaries.append(f"{name}:{status}/{evidence}")
                    if not j or j.gap: gaps.append(f"{name}:{j.gap if j and j.gap else '待核实'}")
                w.writerow({"candidate_id":x.id,"display_name":safe_cell(x.display_name),"pipeline_stage":x.pipeline_stage or "new","archived":int(x.archived),"has_material":int(bool(x.current_material_revision_id)),"phone":safe_cell(contact.phone if contact else ""),"email":safe_cell(contact.email if contact else ""),"contact_confirmed":int(bool(contact.user_confirmed)) if contact else 0,"offer_status":offer.status if offer else "","protocol_revision_id":protocol_id,"evaluation_policy_revision":evaluation_policy_revision,"criteria_summary":safe_cell(" | ".join(summaries)),"evidence_gaps":safe_cell(" | ".join(gaps)),"created_at":x.created_at.isoformat(),"generated_at":generated})
            return PlainTextResponse(out.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="candidates-{pid}.csv"'})
    async def candidate_brief(r):
        with factory() as s: return JSONResponse(_brief_payload(s,r.path_params["candidate_id"]))
    async def project_handoff(r):
        pid=r.path_params["project_id"]
        with factory() as s:
            rows=s.scalars(select(Candidate).where(Candidate.project_id==pid,Candidate.archived.is_(False)).order_by(Candidate.created_at)).all()
            project=s.get(Project,pid)
            return JSONResponse({"project_id":pid,"project_title":project.title if project else "","generated_at":utc_now().isoformat(),"candidates":[_brief_payload(s,x.id) for x in rows]})
    async def compare_candidates(r):
        ids=[x for x in (r.query_params.get("ids") or "").split(",") if x]
        if not 2<=len(ids)<=5: raise V1InvariantError("compare requires 2 to 5 candidate ids")
        with factory() as s:
            candidates=[s.get(Candidate,cid) for cid in ids]
            if any(c is None for c in candidates): raise V1NotFoundError("one or more candidates were not found")
            project_ids={c.project_id for c in candidates if c is not None}
            if len(project_ids)!=1: raise V1InvariantError("compare candidates must belong to the same project")
            pid=next(iter(project_ids)); project=s.get(Project,pid)
            if not project or not project.current_protocol_revision_id: raise V1InvariantError("project has no published protocol")
            protocol_id=project.current_protocol_revision_id
            payload=ProtocolRepository(s).get_payload(protocol_id)
            criteria=[{"criterion_key":str(x.get("criterion_key") or ""),"name":str(x.get("name") or ""),"decision_critical":bool(x.get("decision_critical",False))} for x in (payload.get("criteria") or []) if isinstance(x,dict)]
            contacts={x.candidate_id:x for x in s.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(ids))).all()}
            offers_by_candidate={}
            for offer in s.scalars(select(OfferRecord).where(OfferRecord.candidate_id.in_(ids)).order_by(OfferRecord.created_at.desc(),OfferRecord.id.desc())).all():
                offers_by_candidate.setdefault(offer.candidate_id,offer)
            judgments=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(ids))).all()
            judgment_map={}
            for c in candidates:
                if c is None or not c.current_material_revision_id: continue
                expected=decision_context_hash(protocol_id,c.current_material_revision_id,evaluation_policy_revision)
                for j in judgments:
                    if j.candidate_id==c.id and j.decision_context_hash==expected:
                        judgment_map[(c.id,j.criterion_key)]=j
            rows=[]
            for c in candidates:
                contact=contacts.get(c.id); offer=offers_by_candidate.get(c.id)
                crit=[]
                for definition in criteria:
                    j=judgment_map.get((c.id,definition["criterion_key"]))
                    crit.append({**definition,"status":j.status if j else "missing","evidence_level":j.evidence_level if j else "none","reason":j.reason if j else "","gap":j.gap if j else ""})
                assessment=None
                if c.current_material_revision_id:
                    try: assessment=get_candidate_assessment(s,c.id,evaluation_policy_revision=evaluation_policy_revision)
                    except Exception: assessment=None
                rows.append({"candidate_id":c.id,"display_name":c.display_name,"pipeline_stage":c.pipeline_stage or "new","has_material":bool(c.current_material_revision_id),"contact":{"phone":contact.phone if contact else "","email":contact.email if contact else "","user_confirmed":bool(contact.user_confirmed) if contact else False},"offer_status":offer.status if offer else "","assessment":assessment,"criteria":crit})
            return JSONResponse({"project_id":pid,"protocol_revision_id":protocol_id,"evaluation_policy_revision":evaluation_policy_revision,"criteria":criteria,"candidates":rows,"note":"Comparison is limited to the same project and current protocol/material decision context. Fit is shown only when evidence is publishable; no automatic hiring decision is made."})

    return [
        Route("/api/v1/projects/{project_id:str}/cockpit", cockpit, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/pipeline", project_pipeline, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/candidates.csv", candidates_csv, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/brief", candidate_brief, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/handoff", project_handoff, methods=["GET"]),
        Route("/api/v1/candidates/compare", compare_candidates, methods=["GET"]),
    ]
