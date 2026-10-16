from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.repository import ensure_claims_belong_to_candidate
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import CriterionJudgment, CriterionJudgmentEvidence


def record_assessment(
    session: Session,
    candidate_id: str,
    criterion_key: str,
    *,
    status: str,
    evidence_level: str,
    reason: str,
    gap: str,
    claim_ids: list[str],
    actor: str,
    evaluation_policy_revision: str,
    origin: str = "assessment",
) -> CriterionJudgment:
    ensure_claims_belong_to_candidate(session, candidate_id, claim_ids)
    context = get_current_decision_context(
        session,
        candidate_id,
        evaluation_policy_revision=evaluation_policy_revision,
    )
    row = session.scalar(
        select(CriterionJudgment).where(
            CriterionJudgment.candidate_id == candidate_id,
            CriterionJudgment.criterion_key == criterion_key,
            CriterionJudgment.decision_context_hash == context.hash,
        )
    )
    created = row is None
    if row is None:
        row = CriterionJudgment(
            project_id=context.project_id,
            candidate_id=candidate_id,
            criterion_key=criterion_key,
            decision_context_hash=context.hash,
            status=status,
            evidence_level=evidence_level,
            reason=reason,
            gap=gap,
            origin=origin or "assessment",
        )
        session.add(row)
        session.flush()
    else:
        row.status = status
        row.evidence_level = evidence_level
        row.reason = reason
        row.gap = gap
        row.origin = origin or row.origin or "assessment"
        session.flush()
        session.execute(
            delete(CriterionJudgmentEvidence).where(
                CriterionJudgmentEvidence.judgment_id == row.id
            )
        )

    for claim_id in sorted(set(claim_ids)):
        session.add(
            CriterionJudgmentEvidence(
                judgment_id=row.id,
                claim_id=claim_id,
                role="support",
            )
        )
    session.flush()
    append_audit_event(
        session,
        event_type="CRITERION_JUDGMENT_RECORDED",
        entity_type="criterion_judgment",
        entity_id=row.id,
        actor=actor,
        reason=reason,
        payload={
            "candidate_id": candidate_id,
            "criterion_key": criterion_key,
            "decision_context_hash": context.hash,
            "status": status,
            "evidence_level": evidence_level,
            "claim_ids": sorted(set(claim_ids)),
            "created": created,
            "origin": row.origin,
        },
        project_id=context.project_id, candidate_id=candidate_id,
    )
    return row

# Stable public facade for v1 write-side decision commands.
from srw.modules.decision.verification import record_verification_note  # noqa: E402,F401
from srw.modules.decision.human_decision import make_human_decision  # noqa: E402,F401
