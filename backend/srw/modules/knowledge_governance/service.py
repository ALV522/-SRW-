from __future__ import annotations
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError,V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.decision_operations.models import KnowledgeFeedbackDraft
from .models import KnowledgeCurationProposal
ACTIONS={'confirm_alias','confirm_specialization','confirm_competency_alias','create_canonical','reject','keep_unknown','defer'}

def create_from_feedback(session:Session,feedback_id:str,*,actor:str)->KnowledgeCurationProposal:
    fb=session.get(KnowledgeFeedbackDraft,feedback_id)
    if not fb: raise V1NotFoundError('knowledge feedback draft not found')
    existing=session.scalar(select(KnowledgeCurationProposal).where(KnowledgeCurationProposal.source_kind=='decision_feedback',KnowledgeCurationProposal.source_ref==feedback_id).limit(1))
    if existing:return existing
    payload={'feedback_type':fb.feedback_type,'summary':fb.summary,'evidence_refs':json.loads(fb.evidence_refs_json or '[]'),'decision_context_hash':fb.decision_context_hash}
    p=KnowledgeCurationProposal(project_id=fb.project_id,source_kind='decision_feedback',source_ref=fb.id,title=fb.title,payload_json=json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    session.add(p);fb.status='promoted_to_curation';fb.reviewed_by=actor;fb.reviewed_at=utc_now();session.flush();append_audit_event(session,event_type='knowledge_curation.proposed',entity_type='knowledge_curation_proposal',entity_id=p.id,project_id=p.project_id,actor=actor,payload={'source_kind':p.source_kind,'source_ref':p.source_ref});return p

def review_proposal(session:Session,proposal_id:str,*,action:str,reviewer:str,reason:str,expected_state_version:int)->KnowledgeCurationProposal:
    p=session.get(KnowledgeCurationProposal,proposal_id)
    if not p: raise V1NotFoundError('curation proposal not found')
    if p.expected_state_version!=expected_state_version: raise V1InvariantError('curation proposal was updated; refresh first')
    if action not in ACTIONS: raise V1InvariantError('invalid curation action')
    if p.status in {'exported','rejected'}: raise V1InvariantError(f'proposal is already {p.status}')
    p.proposed_action=action;p.reviewer=reviewer;p.review_reason=reason;p.status='rejected' if action=='reject' else ('draft' if action=='defer' else 'reviewed');p.expected_state_version+=1
    append_audit_event(session,event_type=f'knowledge_curation.{p.status}',entity_type='knowledge_curation_proposal',entity_id=p.id,project_id=p.project_id,actor=reviewer,reason=reason,payload={'proposed_action':action});session.flush();return p

def export_proposal(session:Session,proposal_id:str,*,actor:str,export_root:Path)->tuple[KnowledgeCurationProposal,Path]:
    p=session.get(KnowledgeCurationProposal,proposal_id)
    if not p: raise V1NotFoundError('curation proposal not found')
    if p.status!='reviewed': raise V1InvariantError('only reviewed proposal can be exported')
    export_root.mkdir(parents=True,exist_ok=True)
    payload={'schema':'srw.knowledge-curation-package.v1','proposal_id':p.id,'project_id':p.project_id,'source_kind':p.source_kind,'source_ref':p.source_ref,'proposed_action':p.proposed_action,'title':p.title,'payload':json.loads(p.payload_json or '{}'),'reviewer':p.reviewer,'review_reason':p.review_reason,'exported_by':actor,'active_knowledge_mutated':False}
    path=export_root/f'{p.id}.json';path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');p.status='exported';p.exported_at=utc_now();p.expected_state_version+=1;append_audit_event(session,event_type='knowledge_curation.exported',entity_type='knowledge_curation_proposal',entity_id=p.id,project_id=p.project_id,actor=actor,payload={'path':path.name,'active_knowledge_mutated':False});session.flush();return p,path

def payload(p:KnowledgeCurationProposal)->dict:
    try:data=json.loads(p.payload_json or '{}')
    except:data={}
    return {'id':p.id,'project_id':p.project_id,'source_kind':p.source_kind,'source_ref':p.source_ref,'status':p.status,'proposed_action':p.proposed_action,'title':p.title,'payload':data,'reviewer':p.reviewer,'review_reason':p.review_reason,'expected_state_version':p.expected_state_version,'exported_at':p.exported_at.isoformat() if p.exported_at else None,'created_at':p.created_at.isoformat() if p.created_at else None}
