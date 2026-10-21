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


def apply_result_as_criterion(
    session: Session,
    *,
    project_id: str,
    result: dict,
    criterion_name: str = "",
    decision_critical: bool = False,
    verification_required: bool = True,
) -> tuple[str, dict]:
    """Append one knowledge-search result as a criterion on the project's current protocol draft.

    Returns ``(revision_id, saved_criterion)``. Raises V1NotFoundError when the project does
    not exist. The criterion keeps the knowledge provenance (database/knowledge_id/title) so
    later review can trace the suggestion back to its source; nothing is auto-published.
    """
    from srw.modules.protocol.models import Project, ProtocolRevision
    from srw.modules.protocol.repository import ProtocolRepository

    if not isinstance(result, dict):
        raise V1InvariantError("result must be an object")
    project = session.get(Project, project_id)
    if project is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    draft = session.scalar(
        select(ProtocolRevision)
        .where(ProtocolRevision.project_id == project_id, ProtocolRevision.state == "draft")
        .order_by(ProtocolRevision.revision.desc())
        .limit(1)
    )
    repo = ProtocolRepository(session)
    if draft is None:
        draft = repo.fork_current_to_draft(project_id)
    payload = repo.get_payload(draft.id)
    criteria = list(payload.get("criteria") or [])
    criterion = {
        "name": criterion_name.strip() or str(result.get("title") or "知识建议"),
        "definition": str(result.get("detail") or ""),
        "decision_critical": bool(decision_critical),
        "verification_required": bool(verification_required),
        "verification_probes": [],
        "knowledge_source": {
            "database": str(result.get("database") or ""),
            "knowledge_id": str(result.get("knowledge_id") or ""),
            "title": str(result.get("title") or ""),
        },
    }
    criteria.append(criterion)
    payload["criteria"] = criteria
    row = repo.update_draft(
        draft.id,
        payload,
        {"origin": "knowledge_apply", "knowledge_id": criterion["knowledge_source"]["knowledge_id"]},
    )
    saved = repo.get_payload(row.id)["criteria"][-1]
    return row.id, saved
