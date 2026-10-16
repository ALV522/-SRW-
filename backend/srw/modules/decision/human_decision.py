from __future__ import annotations
from sqlalchemy.orm import Session
from srw.kernel.errors import V1InvariantError
from srw.modules.audit.repository import append_audit_event
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import HumanDecision
from srw.modules.decision.repository import get_judgments_for_context
from srw.modules.protocol.repository import get_protocol_payload
from srw.modules.work.repository import resolve_work_items_for_context

_ALLOWED={'advance','reject','hold'}


def _action_gate(session: Session, candidate_id: str, decision: str, *, evaluation_policy_revision: str) -> tuple[bool, list[str]]:
    if decision == 'hold':
        return True, []
    ctx=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    payload=get_protocol_payload(session,ctx.protocol_revision_id)
    judgments={x.criterion_key:x for x in get_judgments_for_context(session,candidate_id,ctx.hash)}
    gated=[c for c in (payload.get('criteria') or []) if isinstance(c,dict) and (c.get('decision_critical') or c.get('verification_required'))]
    if decision == 'reject':
        supported=[]
        for c in gated:
            key=str(c.get('criterion_key') or '')
            j=judgments.get(key)
            if j and j.status=='not_met' and j.evidence_level not in {'none',''}:
                supported.append(key)
        return (bool(supported), [] if supported else ['verified_not_met_reason'])
    blocking=[]
    for c in gated:
        key=str(c.get('criterion_key') or '')
        j=judgments.get(key)
        if j is None or j.status in {'missing','partial','conflict','not_met'} or j.evidence_level in {'none',''}:
            blocking.append(key)
    return (not blocking, blocking)


def make_human_decision(session: Session, candidate_id: str, *, decision: str, reason: str, actor: str, evaluation_policy_revision: str) -> HumanDecision:
    if decision not in _ALLOWED: raise V1InvariantError('invalid human decision')
    if not reason.strip(): raise V1InvariantError('decision reason is required')
    allowed, blocking = _action_gate(session,candidate_id,decision,evaluation_policy_revision=evaluation_policy_revision)
    if not allowed:
        raise V1InvariantError(f'decision action is not ready: {blocking}')
    ctx=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    row=HumanDecision(project_id=ctx.project_id,candidate_id=candidate_id,decision_context_hash=ctx.hash,decision=decision,reason=reason.strip(),actor=actor)
    session.add(row); session.flush()
    if decision != 'hold':
        resolve_work_items_for_context(session, candidate_id, ctx.hash)
    append_audit_event(session,event_type='HUMAN_DECISION_MADE',entity_type='human_decision',entity_id=row.id,actor=actor,reason=reason,payload={'decision':decision,'context_hash':ctx.hash},project_id=ctx.project_id,candidate_id=candidate_id)
    session.flush(); return row
