from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.calibration.models import CriterionAnchorCase, JudgmentReviewItem
from srw.modules.protocol.repository import ensure_project_exists

LIFECYCLE_ORDER = ("observed", "human_reviewed", "candidate", "gold")
REASON_CLASS = {
    "input_error": "input",
    "evidence_error": "evidence",
    "rubric_error": "rubric",
    "execution_error": "execution",
    "decision_error": "decision",
    "other": "other",
}


def anchor_output(row: CriterionAnchorCase) -> dict:
    return {
        "anchor_id": row.id, "project_id": row.project_id, "criterion_key": row.criterion_key,
        "lifecycle": row.lifecycle, "case_text": row.case_text,
        "expected_judgment": row.expected_judgment, "expected_evidence_level": row.expected_evidence_level,
        "first_reviewer": row.first_reviewer, "second_reviewer": row.second_reviewer,
        "source_case_id": row.source_case_id, "content_hash": row.content_hash,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def create_anchor(session: Session, project_id: str, *, criterion_key: str, case_text: str, expected_judgment: str, expected_evidence_level: str, actor: str, source_case_id: str = "") -> dict:
    ensure_project_exists(session, project_id)
    criterion_key = criterion_key.strip(); case_text = case_text.strip(); actor = actor.strip()
    if not criterion_key or not case_text or not actor:
        raise V1InvariantError("criterion_key, case_text and actor are required")
    if expected_judgment not in {"met", "partial", "missing", "conflict", "not_met"}:
        raise V1InvariantError("invalid expected_judgment")
    if expected_evidence_level not in {"strong", "medium", "weak", "none"}:
        raise V1InvariantError("invalid expected_evidence_level")
    payload = {"criterion_key": criterion_key, "case_text": case_text, "expected_judgment": expected_judgment, "expected_evidence_level": expected_evidence_level}
    row = CriterionAnchorCase(project_id=project_id, criterion_key=criterion_key, lifecycle="observed", case_text=case_text, expected_judgment=expected_judgment, expected_evidence_level=expected_evidence_level, source_case_id=source_case_id.strip(), content_hash=content_hash(payload))
    session.add(row); session.flush()
    append_audit_event(session, event_type="CALIBRATION_ANCHOR_CREATED", entity_type="criterion_anchor_case", entity_id=row.id, actor=actor, payload={"criterion_key": criterion_key}, project_id=project_id)
    return anchor_output(row)


def list_anchors(session: Session, project_id: str, *, lifecycle: str | None = None) -> list[dict]:
    ensure_project_exists(session, project_id)
    q = select(CriterionAnchorCase).where(CriterionAnchorCase.project_id == project_id)
    if lifecycle: q = q.where(CriterionAnchorCase.lifecycle == lifecycle)
    return [anchor_output(row) for row in session.scalars(q.order_by(CriterionAnchorCase.created_at.desc())).all()]


def promote_anchor(session: Session, anchor_id: str, *, target: str, actor: str) -> dict:
    row = session.get(CriterionAnchorCase, anchor_id)
    if row is None: raise V1NotFoundError(f"anchor not found: {anchor_id}")
    if target not in LIFECYCLE_ORDER: raise V1InvariantError("invalid anchor lifecycle")
    current_i = LIFECYCLE_ORDER.index(row.lifecycle); target_i = LIFECYCLE_ORDER.index(target)
    if target_i != current_i + 1: raise V1InvariantError("anchor lifecycle must advance exactly one stage")
    actor = actor.strip()
    if not actor: raise V1InvariantError("actor is required")
    if target == "human_reviewed": row.first_reviewer = actor
    if target == "candidate" and not row.first_reviewer: raise V1InvariantError("human_reviewed anchor requires first reviewer")
    if target == "gold":
        if not row.first_reviewer: raise V1InvariantError("gold anchor requires first reviewer")
        if actor == row.first_reviewer: raise V1InvariantError("gold promotion requires a distinct second reviewer")
        row.second_reviewer = actor
    row.lifecycle = target; row.updated_at = utc_now(); session.flush()
    append_audit_event(session, event_type="CALIBRATION_ANCHOR_PROMOTED", entity_type="criterion_anchor_case", entity_id=row.id, actor=actor, payload={"lifecycle": target}, project_id=row.project_id)
    return anchor_output(row)


def review_output(row: JudgmentReviewItem) -> dict:
    return {"review_id": row.id, "project_id": row.project_id, "candidate_id": row.candidate_id, "trigger": row.trigger, "criterion_key": row.criterion_key, "before": row.before, "after": row.after, "reason": row.reason, "error_class": row.error_class, "actor": row.actor, "state": row.state, "resolution_note": row.resolution_note, "created_at": row.created_at.isoformat(), "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}


def create_review(session: Session, project_id: str, *, trigger: str, criterion_key: str, before: str, after: str, reason: str, actor: str, candidate_id: str | None = None) -> dict:
    ensure_project_exists(session, project_id)
    if reason not in REASON_CLASS: raise V1InvariantError(f"invalid review reason: {reason}")
    if not trigger.strip() or not criterion_key.strip() or not actor.strip(): raise V1InvariantError("trigger, criterion_key and actor are required")
    row = JudgmentReviewItem(project_id=project_id, candidate_id=candidate_id or None, trigger=trigger.strip(), criterion_key=criterion_key.strip(), before=before.strip(), after=after.strip(), reason=reason, error_class=REASON_CLASS[reason], actor=actor.strip())
    session.add(row); session.flush()
    append_audit_event(session, event_type="JUDGMENT_REVIEW_CREATED", entity_type="judgment_review_item", entity_id=row.id, actor=actor, payload={"criterion_key": row.criterion_key, "reason": reason}, project_id=project_id, candidate_id=candidate_id)
    return review_output(row)


def list_reviews(session: Session, project_id: str, *, state: str | None = None) -> list[dict]:
    ensure_project_exists(session, project_id)
    q = select(JudgmentReviewItem).where(JudgmentReviewItem.project_id == project_id)
    if state: q = q.where(JudgmentReviewItem.state == state)
    return [review_output(row) for row in session.scalars(q.order_by(JudgmentReviewItem.created_at.desc())).all()]


def resolve_review(session: Session, review_id: str, *, actor: str, note: str) -> dict:
    row = session.get(JudgmentReviewItem, review_id)
    if row is None: raise V1NotFoundError(f"judgment review not found: {review_id}")
    if row.state != "open": raise V1InvariantError("judgment review is already resolved")
    if not actor.strip() or not note.strip(): raise V1InvariantError("actor and resolution note are required")
    row.state = "resolved"; row.resolution_note = note.strip(); row.resolved_at = utc_now(); session.flush()
    append_audit_event(session, event_type="JUDGMENT_REVIEW_RESOLVED", entity_type="judgment_review_item", entity_id=row.id, actor=actor, reason=note, project_id=row.project_id, candidate_id=row.candidate_id)
    return review_output(row)
