from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.human_decision import _action_gate
from srw.modules.decision.models import HumanDecision
from srw.modules.work.repository import resolve_work_items_for_context


@dataclass(frozen=True, slots=True)
class DecisionHistoryRow:
    decision_id: str
    decision_context_hash: str
    decision: str
    reason: str
    actor: str
    created_at: str
    is_current_context: bool
    stale: bool
    reaffirmed_from_decision_id: str | None


def get_decision_history(
    session: Session,
    candidate_id: str,
    *,
    evaluation_policy_revision: str,
    limit: int = 100,
) -> list[DecisionHistoryRow]:
    if session.get(Candidate, candidate_id) is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    try:
        current_hash = get_current_decision_context(
            session, candidate_id, evaluation_policy_revision=evaluation_policy_revision
        ).hash
    except V1InvariantError:
        current_hash = ""
    rows = list(
        session.scalars(
            select(HumanDecision)
            .where(HumanDecision.candidate_id == candidate_id)
            .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
            .limit(min(max(int(limit), 1), 500))
        )
    )
    return [
        DecisionHistoryRow(
            decision_id=row.id,
            decision_context_hash=row.decision_context_hash,
            decision=row.decision,
            reason=row.reason,
            actor=row.actor,
            created_at=row.created_at.isoformat(),
            is_current_context=bool(current_hash and row.decision_context_hash == current_hash),
            # With no current Protocol/Material identity, a prior human decision
            # is historical but cannot be treated as current.
            stale=not bool(current_hash and row.decision_context_hash == current_hash),
            reaffirmed_from_decision_id=row.reaffirmed_from_decision_id,
        )
        for row in rows
    ]


def latest_stale_decision(
    session: Session,
    candidate_id: str,
    *,
    current_context_hash: str,
) -> HumanDecision | None:
    return session.scalar(
        select(HumanDecision)
        .where(
            HumanDecision.candidate_id == candidate_id,
            HumanDecision.decision_context_hash != current_context_hash,
        )
        .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
        .limit(1)
    )


def reaffirm_latest_decision(
    session: Session,
    candidate_id: str,
    *,
    actor: str,
    reason: str,
    evaluation_policy_revision: str,
) -> HumanDecision:
    """Explicitly reaffirm the latest historical decision under the current context.

    No decision is carried forward automatically. The current action gate is run
    again, so an old advance/reject can only be reaffirmed if the current evidence
    still satisfies the current protocol.
    """
    if not reason.strip():
        raise V1InvariantError("reaffirmation reason is required")
    ctx = get_current_decision_context(
        session, candidate_id, evaluation_policy_revision=evaluation_policy_revision
    )
    existing = session.scalar(
        select(HumanDecision)
        .where(
            HumanDecision.candidate_id == candidate_id,
            HumanDecision.decision_context_hash == ctx.hash,
        )
        .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
        .limit(1)
    )
    if existing is not None:
        raise V1InvariantError("current decision context already has a human decision")
    previous = latest_stale_decision(session, candidate_id, current_context_hash=ctx.hash)
    if previous is None:
        raise V1InvariantError("no historical decision is available to reaffirm")
    allowed, blocking = _action_gate(
        session,
        candidate_id,
        previous.decision,
        evaluation_policy_revision=evaluation_policy_revision,
    )
    if not allowed:
        raise V1InvariantError(f"historical decision cannot be reaffirmed under current evidence: {blocking}")
    row = HumanDecision(
        project_id=ctx.project_id,
        candidate_id=candidate_id,
        decision_context_hash=ctx.hash,
        decision=previous.decision,
        reason=reason.strip(),
        actor=actor or "human",
        reaffirmed_from_decision_id=previous.id,
    )
    session.add(row)
    session.flush()
    if row.decision != "hold":
        resolve_work_items_for_context(session, candidate_id, ctx.hash)
    append_audit_event(
        session,
        event_type="HUMAN_DECISION_REAFFIRMED",
        entity_type="human_decision",
        entity_id=row.id,
        actor=actor or "human",
        reason=reason.strip(),
        payload={
            "decision": row.decision,
            "current_context_hash": ctx.hash,
            "reaffirmed_from_decision_id": previous.id,
            "previous_context_hash": previous.decision_context_hash,
        },
        project_id=ctx.project_id,
        candidate_id=candidate_id,
    )
    session.flush()
    return row
