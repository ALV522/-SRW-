from __future__ import annotations
import json
from collections import Counter
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.errors import V1InvariantError,V1NotFoundError
from srw.modules.candidate.models import Candidate
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.recruiting.models import OfferRecord
from srw.modules.protocol.models import Project
from srw.modules.decision_operations.models import DecisionAction
from .models import RecruitmentPlan

def upsert_plan(session:Session,project_id:str,*,target_hires:int,target_date:str,owner:str,source_channels:list[str],notes:str)->RecruitmentPlan:
    if not session.get(Project,project_id): raise V1NotFoundError('project not found')
    if target_hires<1 or target_hires>10000: raise V1InvariantError('target_hires must be between 1 and 10000')
    row=session.scalar(select(RecruitmentPlan).where(RecruitmentPlan.project_id==project_id))
    if not row: row=RecruitmentPlan(project_id=project_id);session.add(row)
    row.target_hires=target_hires;row.target_date=target_date.strip();row.owner=owner.strip();row.source_channels_json=json.dumps([str(x).strip() for x in source_channels if str(x).strip()],ensure_ascii=False,separators=(',',':'));row.notes=notes.strip();session.flush();return row

def planning_snapshot(session:Session,project_id:str,policy:str)->dict:
    project=session.get(Project,project_id)
    if not project: raise V1NotFoundError('project not found')
    plan=session.scalar(select(RecruitmentPlan).where(RecruitmentPlan.project_id==project_id))
    candidates=list(session.scalars(select(Candidate).where(Candidate.project_id==project_id,Candidate.archived.is_(False),Candidate.merged_into_candidate_id.is_(None))))
    stages=Counter(c.pipeline_stage for c in candidates)
    assessments=[]
    for c in candidates:
        if not c.current_material_revision_id: continue
        try: assessments.append(get_candidate_assessment(session,c.id,evaluation_policy_revision=policy))
        except Exception: pass
    publishable=sum(1 for a in assessments if a.get('publishable_for_comparison'))
    ready=sum(1 for a in assessments if a.get('decision_ready'))
    coverages=[float(a.get('evidence_coverage') or 0) for a in assessments]
    avg_cov=round(sum(coverages)/len(coverages),4) if coverages else 0.0
    accepted_offers=session.scalars(select(OfferRecord).where(OfferRecord.project_id==project_id,OfferRecord.status=='accepted')).all()
    hired=max(stages.get('hired',0),len(list(accepted_offers)))
    target=plan.target_hires if plan else 1
    open_actions=list(session.scalars(select(DecisionAction).where(DecisionAction.project_id==project_id,DecisionAction.status.in_({'proposed','accepted','in_progress'}))))
    action_counts=Counter(a.action_type for a in open_actions)
    bottlenecks=[]
    if candidates and avg_cov<0.70:bottlenecks.append({'code':'LOW_EVIDENCE_COVERAGE','severity':'high','text':'候选人平均证据覆盖不足 70%，应优先补证而不是扩大排名。'})
    if stages.get('new',0)+stages.get('screening',0)>max(5,stages.get('shortlisted',0)*3):bottlenecks.append({'code':'SCREENING_BACKLOG','severity':'medium','text':'新候选人与筛选队列堆积，筛选吞吐可能成为瓶颈。'})
    if action_counts.get('phone_verify',0)+action_counts.get('independent_verify',0)>5:bottlenecks.append({'code':'VERIFICATION_BACKLOG','severity':'high','text':'核实动作积压，应优先关闭决策关键证据缺口。'})
    return {'project_id':project_id,'plan':{'configured':bool(plan),'target_hires':target,'target_date':plan.target_date if plan else '','owner':plan.owner if plan else '','source_channels':json.loads(plan.source_channels_json or '[]') if plan else [],'notes':plan.notes if plan else ''},'pipeline':dict(stages),'candidate_count':len(candidates),'hired_count':hired,'remaining_hires':max(0,target-hired),'assessment':{'assessed_count':len(assessments),'publishable_count':publishable,'decision_ready_count':ready,'average_evidence_coverage':avg_cov},'open_actions':{'total':len(open_actions),'by_type':dict(action_counts)},'bottlenecks':bottlenecks,'semantics':{'operational_priority_is_not_hiring_rank':True,'missing_is_not_zero':True}}
