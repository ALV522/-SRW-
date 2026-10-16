from __future__ import annotations
import hashlib,json
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError,V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.decision.lineage import latest_stale_decision
from srw.modules.decision.models import HumanDecision
from srw.modules.decision.context import get_current_decision_context
from .models import DecisionAction,KnowledgeFeedbackDraft

OPEN={'proposed','accepted','in_progress'}

def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _hash(v): return hashlib.sha256(_canon(v).encode()).hexdigest()

def _recommend(session:Session,c:Candidate,policy:str)->list[dict]:
    try: a=get_candidate_assessment(session,c.id,evaluation_policy_revision=policy); ctx=a['decision_context_hash']
    except Exception: return []
    current=session.scalar(select(HumanDecision).where(HumanDecision.candidate_id==c.id,HumanDecision.decision_context_hash==ctx).order_by(HumanDecision.created_at.desc()).limit(1))
    if current: return []
    stale=latest_stale_decision(session,c.id,current_context_hash=ctx)
    if stale: return [{'action_type':'reevaluate','priority':98,'reason_code':'DECISION_STALE','reason_text':'材料或招聘协议已变化，历史人工决定不能静默沿用；应先复评当前证据。','criterion_key':'','decision_context_hash':ctx}]
    out=[]
    for k in a.get('conflict_keys') or []: out.append({'action_type':'independent_verify','priority':100,'reason_code':'EVIDENCE_CONFLICT','reason_text':'证据存在冲突，需要独立来源核实后再判断。','criterion_key':k,'decision_context_hash':ctx})
    seen={x['criterion_key'] for x in out}
    for k in a.get('blocking_keys') or []:
        if k not in seen: out.append({'action_type':'phone_verify','priority':90,'reason_code':'DECISION_BLOCKER','reason_text':'决策关键项尚未闭合，应优先核实。','criterion_key':k,'decision_context_hash':ctx});seen.add(k)
    for k in a.get('unresolved_keys') or []:
        if k not in seen: out.append({'action_type':'collect_evidence','priority':80,'reason_code':'EVIDENCE_GAP','reason_text':'当前标准缺少可比较证据，应补充材料或结构化询问。','criterion_key':k,'decision_context_hash':ctx});seen.add(k)
    if not out and a.get('decision_ready'): out.append({'action_type':'human_decision','priority':70,'reason_code':'HUMAN_DECISION','reason_text':'当前证据已达到决策门槛，下一步必须由授权人员作出人工决定。','criterion_key':'','decision_context_hash':ctx})
    return out

def recommend_actions(session:Session,project_id:str,policy:str)->list[DecisionAction]:
    candidates=list(session.scalars(select(Candidate).where(Candidate.project_id==project_id,Candidate.archived.is_(False),Candidate.merged_into_candidate_id.is_(None)).order_by(Candidate.created_at,Candidate.id)))
    desired=[]
    for c in candidates:
        for r in _recommend(session,c,policy):
            content=_hash({'candidate_id':c.id,**r}); desired.append((c,r,content))
    desired_hashes={x[2] for x in desired}
    for old in session.scalars(select(DecisionAction).where(DecisionAction.project_id==project_id,DecisionAction.status.in_(OPEN))):
        if old.content_hash not in desired_hashes: old.status='stale';old.expected_state_version+=1
    existing={x.content_hash:x for x in session.scalars(select(DecisionAction).where(DecisionAction.project_id==project_id,DecisionAction.content_hash.in_(desired_hashes) if desired_hashes else DecisionAction.id=='__none__'))}
    rows=[]
    for c,r,h in desired:
        x=existing.get(h)
        if x is None:
            x=DecisionAction(project_id=project_id,candidate_id=c.id,content_hash=h,**r);session.add(x);session.flush()
        rows.append(x)
    return sorted(rows,key=lambda x:(-x.priority,x.created_at,x.id))

def transition_action(session:Session,action_id:str,*,transition:str,actor:str,expected_state_version:int,outcome:dict|None=None,reason:str='')->DecisionAction:
    x=session.get(DecisionAction,action_id)
    if not x: raise V1NotFoundError('decision action not found')
    if x.expected_state_version!=expected_state_version: raise V1InvariantError('action was updated by another operation; refresh first')
    allowed={'accept':({'proposed'},'accepted'),'reject':({'proposed','accepted'},'rejected'),'start':({'accepted'},'in_progress'),'complete':({'accepted','in_progress'},'completed'),'cancel':({'accepted','in_progress'},'cancelled')}
    if transition not in allowed: raise V1InvariantError('invalid action transition')
    states,target=allowed[transition]
    if x.status not in states: raise V1InvariantError(f'cannot {transition} action from {x.status}')
    if transition=='complete':
        if not isinstance(outcome,dict) or outcome.get('human_confirmed') is not True: raise V1InvariantError('completed action requires human_confirmed outcome')
        x.outcome_json=_canon(outcome);x.completed_by=actor;x.completed_at=utc_now()
    if transition=='accept': x.accepted_by=actor;x.accepted_at=utc_now()
    x.status=target;x.expected_state_version+=1
    append_audit_event(session,event_type=f'decision_action.{target}',entity_type='decision_action',entity_id=x.id,project_id=x.project_id,candidate_id=x.candidate_id,actor=actor,reason=reason,payload={'action_type':x.action_type,'priority':x.priority,'state_version':x.expected_state_version})
    session.flush();return x

def stage_knowledge_feedback(session:Session,action_id:str,*,actor:str)->KnowledgeFeedbackDraft:
    action=session.get(DecisionAction,action_id)
    if not action: raise V1NotFoundError('decision action not found')
    if action.status!='completed': raise V1InvariantError('only completed action can stage knowledge feedback')
    outcome=json.loads(action.outcome_json or '{}')
    if outcome.get('human_confirmed') is not True: raise V1InvariantError('action outcome is not human confirmed')
    fb=outcome.get('knowledge_feedback')
    if not isinstance(fb,dict) or not str(fb.get('summary') or '').strip(): raise V1InvariantError('completed outcome has no knowledge_feedback')
    content=_hash({'action':action.id,'feedback':fb,'context':action.decision_context_hash})
    existing=session.scalar(select(KnowledgeFeedbackDraft).where(KnowledgeFeedbackDraft.content_hash==content).limit(1))
    if existing:return existing
    row=KnowledgeFeedbackDraft(project_id=action.project_id,candidate_id=action.candidate_id,decision_action_id=action.id,feedback_type=str(fb.get('feedback_type') or 'operational_learning'),title=str(fb.get('title') or '招聘执行反馈')[:240],summary=str(fb.get('summary') or ''),evidence_refs_json=_canon(fb.get('evidence_refs') or []),outcome_snapshot_json=_canon(outcome),decision_context_hash=action.decision_context_hash,content_hash=content)
    session.add(row);session.flush();append_audit_event(session,event_type='knowledge_feedback.staged',entity_type='knowledge_feedback_draft',entity_id=row.id,project_id=row.project_id,candidate_id=row.candidate_id,actor=actor,payload={'decision_action_id':action.id,'content_hash':content});return row

def action_payload(x:DecisionAction)->dict:
    return {'id':x.id,'project_id':x.project_id,'candidate_id':x.candidate_id,'action_type':x.action_type,'status':x.status,'priority':x.priority,'reason_code':x.reason_code,'reason_text':x.reason_text,'criterion_key':x.criterion_key,'decision_context_hash':x.decision_context_hash,'expected_state_version':x.expected_state_version,'accepted_by':x.accepted_by,'completed_by':x.completed_by,'created_at':x.created_at.isoformat() if x.created_at else None,'updated_at':x.updated_at.isoformat() if x.updated_at else None}
