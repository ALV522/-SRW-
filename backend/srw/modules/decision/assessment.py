"""Read-only, context-bound candidate assessment projection.

Never writes a human decision. Unknown/conflicted evidence is not a negative
fit signal; it prevents publication of a comparable fit estimate.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite
from sqlalchemy.orm import Session
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.repository import get_judgments_for_context
from srw.modules.decision.readiness import evaluate_decision_readiness
from srw.modules.protocol.repository import get_protocol_payload

STATUS_SCORE = {'met': 1.0, 'partial': 0.5, 'not_met': 0.0}
LEVEL_CONFIDENCE = {'strong': 1.0, 'medium': 0.7, 'weak': 0.35, 'none': 0.0}

@dataclass(frozen=True)
class Assessment:
    candidate_id: str
    decision_context_hash: str
    fit_score: float | None
    evidence_coverage: float
    decision_ready: bool
    blocking_keys: tuple[str, ...]
    unresolved_keys: tuple[str, ...]
    conflict_keys: tuple[str, ...]
    publishable_for_comparison: bool
    criteria: tuple[dict, ...]
    scoring_policy: str = 'srw.assessment.projection.v1'

def calculate_assessment(candidate_id: str, context_hash: str, criteria: list[dict], judgments: list, *, decision_ready: bool, blocking_keys=()) -> Assessment:
    if not criteria:
        return Assessment(candidate_id,context_hash,None,0.0,decision_ready,tuple(blocking_keys),(),(),False,())
    by = {j.criterion_key:j for j in judgments}
    total=0.0; weighted_score=0.0; scored_weight=0.0; covered=0.0
    unresolved=[]; conflicts=[]; output=[]
    keys=set()
    for item in criteria:
        if not isinstance(item,dict): raise ValueError('criterion must be an object')
        key = str(item.get('criterion_key') or '').strip()
        if not key or key in keys: raise ValueError('criteria require unique, nonempty criterion_key')
        keys.add(key)
        weight=item.get('weight',1)
        if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not isfinite(weight) or weight<=0:
            raise ValueError(f'invalid positive criterion weight: {key}')
        weight=float(weight); total+=weight
        j=by.get(key); status=j.status if j else 'missing'
        level=j.evidence_level if j else 'none'
        if status not in (*STATUS_SCORE,'missing','conflict') or level not in LEVEL_CONFIDENCE:
            raise ValueError(f'invalid judgment state: {key}')
        confidence=LEVEL_CONFIDENCE[level]
        # A naked judgment without supporting evidence must never count as coverage.
        if status in STATUS_SCORE and confidence>0:
            covered+=weight*confidence
            weighted_score+=weight*STATUS_SCORE[status]
            scored_weight+=weight
        else:
            unresolved.append(key)
        if status=='conflict': conflicts.append(key)
        output.append({'criterion_key':key,'weight':weight,'status':status,'evidence_level':level,
                       'evidence_factor':confidence,'criterion_score':STATUS_SCORE.get(status) if confidence>0 else None})
    coverage=covered/total
    publishable=not unresolved and not conflicts and coverage>=0.70
    # Diagnostic score is withheld whenever any criterion is unresolved, avoiding misleading ranks.
    fit=round(100*weighted_score/scored_weight,2) if publishable else None
    return Assessment(candidate_id,context_hash,fit,round(coverage,4),decision_ready,
                      tuple(blocking_keys),tuple(unresolved),tuple(conflicts),publishable,tuple(output))

def get_candidate_assessment(session: Session, candidate_id: str, *, evaluation_policy_revision: str) -> dict:
    ctx=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    payload=get_protocol_payload(session,ctx.protocol_revision_id)
    judgment=get_judgments_for_context(session,candidate_id,ctx.hash)
    readiness=evaluate_decision_readiness(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    return asdict(calculate_assessment(candidate_id,ctx.hash,payload.get('criteria') or [],judgment,
                                       decision_ready=readiness.ready,blocking_keys=readiness.blocking_keys))
