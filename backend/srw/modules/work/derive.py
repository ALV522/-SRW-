from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.repository import JudgmentView, get_judgments_for_context
from srw.modules.protocol.repository import get_protocol_payload
from srw.modules.work.models import WorkItem
from srw.modules.work.repository import supersede_stale_work_items


@dataclass(frozen=True, slots=True)
class WorkSpec:
    id: str
    project_id: str
    candidate_id: str
    criterion_key: str | None
    type: str
    priority: int
    reason: str
    decision_context_hash: str
    criterion_name: str = ""
    protocol_revision_id: str | None = None
    material_revision_id: str | None = None
    state: str = "open"
    created_at: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)


def derive_work_specs(
    *,
    project_id: str,
    candidate_id: str,
    context_hash: str,
    protocol_payload: dict,
    judgments: list[JudgmentView],
) -> list[WorkSpec]:
    by_key = {row.criterion_key: row for row in judgments}
    specs: list[WorkSpec] = []
    for position, criterion in enumerate(protocol_payload.get("criteria") or []):
        if not isinstance(criterion, dict):
            continue
        key = str(criterion.get("criterion_key") or "").strip()
        if not key:
            continue
        judgment = by_key.get(key)
        status = judgment.status if judgment is not None else "missing"
        blocking = bool(criterion.get("decision_critical") or criterion.get("verification_required"))
        if status == "conflict":
            specs.append(
                WorkSpec(
                    id=f"derived:{context_hash}:{key}:conflict",
                    project_id=project_id,
                    candidate_id=candidate_id,
                    criterion_key=key,
                    criterion_name=str(criterion.get("name") or key),
                    type="RESOLVE_CONFLICT",
                    priority=10 + position,
                    reason=(judgment.gap or judgment.reason) if judgment else "存在矛盾，需要先解决",
                    decision_context_hash=context_hash,
                )
            )
        elif blocking and status in {"missing", "partial"}:
            reason = (judgment.gap or judgment.reason) if judgment else "尚无足够证据"
            specs.append(
                WorkSpec(
                    id=f"derived:{context_hash}:{key}:verify",
                    project_id=project_id,
                    candidate_id=candidate_id,
                    criterion_key=key,
                    criterion_name=str(criterion.get("name") or key),
                    type="VERIFY_CRITERION",
                    priority=20 + position,
                    reason=reason,
                    decision_context_hash=context_hash,
                )
            )
    return specs


def refresh_candidate_work_items(
    session: Session,
    candidate_id: str,
    *,
    evaluation_policy_revision: str,
) -> list[WorkItem]:
    context = get_current_decision_context(
        session,
        candidate_id,
        evaluation_policy_revision=evaluation_policy_revision,
    )
    payload = get_protocol_payload(session, context.protocol_revision_id)
    judgments = get_judgments_for_context(session, candidate_id, context.hash)
    supersede_stale_work_items(session, candidate_id, context.hash)
    existing = session.scalars(
        select(WorkItem).where(
            WorkItem.candidate_id == candidate_id,
            WorkItem.decision_context_hash == context.hash,
            WorkItem.state.in_(("open", "in_progress")),
        )
    ).all()
    for row in existing:
        row.state = "superseded"
    session.flush()

    rows: list[WorkItem] = []
    specs = derive_work_specs(
        project_id=context.project_id,
        candidate_id=candidate_id,
        context_hash=context.hash,
        protocol_payload=payload,
        judgments=judgments,
    )
    if not specs:
        specs = [WorkSpec(id=f"derived:{context.hash}:decision", project_id=context.project_id, candidate_id=candidate_id, criterion_key=None, criterion_name="人工决定", type="MAKE_DECISION", priority=90, reason="当前判断信息已满足决策条件", decision_context_hash=context.hash)]
    for spec in specs:
        row = WorkItem(
            project_id=spec.project_id,
            candidate_id=spec.candidate_id,
            criterion_key=spec.criterion_key,
            criterion_name=spec.criterion_name,
            protocol_revision_id=context.protocol_revision_id,
            material_revision_id=context.material_revision_id,
            type=spec.type,
            priority=spec.priority,
            reason=spec.reason,
            decision_context_hash=spec.decision_context_hash,
            state="open",
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows
