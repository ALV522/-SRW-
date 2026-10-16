from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy.orm import Session
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.repository import get_judgments_for_context
from srw.modules.protocol.repository import get_protocol_payload

@dataclass(frozen=True, slots=True)
class DecisionReadiness:
    ready: bool
    blocking_keys: tuple[str,...]


def evaluate_decision_readiness(session: Session, candidate_id: str, *, evaluation_policy_revision: str) -> DecisionReadiness:
    ctx=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    payload=get_protocol_payload(session,ctx.protocol_revision_id); by={j.criterion_key:j for j in get_judgments_for_context(session,candidate_id,ctx.hash)}
    blocking=[]
    for c in payload.get('criteria') or []:
        if not isinstance(c,dict): continue
        key=str(c.get('criterion_key') or '')
        if not (c.get('decision_critical') or c.get('verification_required')): continue
        status=by.get(key).status if by.get(key) else 'missing'
        if status in {'missing','partial','conflict'}: blocking.append(key)
    return DecisionReadiness(not blocking,tuple(blocking))
