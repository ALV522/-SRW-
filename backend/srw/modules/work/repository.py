from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.modules.work.models import WorkItem


def supersede_stale_work_items(session: Session, candidate_id: str, current_context_hash: str) -> int:
    rows = session.scalars(
        select(WorkItem).where(
            WorkItem.candidate_id == candidate_id,
            WorkItem.state.in_(("open", "in_progress")),
            WorkItem.decision_context_hash.is_not(None),
            WorkItem.decision_context_hash != current_context_hash,
        )
    ).all()
    now = utc_now()
    for row in rows:
        row.state = "superseded"
        row.resolved_at = now
    session.flush()
    return len(rows)


def resolve_work_items_for_context(session: Session, candidate_id: str, context_hash: str) -> int:
    rows = session.scalars(
        select(WorkItem).where(
            WorkItem.candidate_id == candidate_id,
            WorkItem.decision_context_hash == context_hash,
            WorkItem.state.in_(("open", "in_progress")),
        )
    ).all()
    now = utc_now()
    for row in rows:
        row.state = "resolved"
        row.resolved_at = now
    session.flush()
    return len(rows)
