from __future__ import annotations

from collections import Counter
from typing import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.protocol.models import Project
from srw.modules.recruiting.models import CandidateStageTransition, OfferRecord

PROJECT_STATUSES = ("draft", "open", "paused", "filled", "closed", "archived")
PIPELINE_STAGES = ("new", "screening", "shortlisted", "phone_screen", "interview", "offer", "hired", "rejected", "talent_pool", "withdrawn")
OFFER_STATES = ("draft", "approved", "sent", "accepted", "declined", "withdrawn")

_PROJECT_TRANSITIONS = {
    "draft": {"open", "archived"},
    "open": {"paused", "filled", "closed", "archived"},
    "paused": {"open", "closed", "archived"},
    "filled": {"closed", "archived"},
    "closed": {"archived"},
    "archived": {"draft", "open"},
}

_STAGE_TRANSITIONS = {
    "new": {"screening", "shortlisted", "rejected", "talent_pool", "withdrawn"},
    "screening": {"shortlisted", "phone_screen", "rejected", "talent_pool", "withdrawn"},
    "shortlisted": {"phone_screen", "interview", "rejected", "talent_pool", "withdrawn"},
    "phone_screen": {"interview", "rejected", "talent_pool", "withdrawn"},
    "interview": {"offer", "rejected", "talent_pool", "withdrawn"},
    "offer": {"hired", "rejected", "talent_pool", "withdrawn"},
    "hired": set(),
    "rejected": {"talent_pool"},
    "talent_pool": {"screening", "shortlisted", "withdrawn"},
    "withdrawn": set(),
}

_OFFER_TRANSITIONS = {
    "draft": {"approved", "withdrawn"},
    "approved": {"sent", "withdrawn"},
    "sent": {"accepted", "declined", "withdrawn"},
    "accepted": set(),
    "declined": set(),
    "withdrawn": set(),
}


def change_project_status(session: Session, project_id: str, status: str, *, actor: str, reason: str) -> Project:
    row = session.get(Project, project_id)
    if row is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    current = "open" if row.status == "active" else row.status
    if status not in PROJECT_STATUSES:
        raise V1InvariantError(f"unsupported project status: {status}")
    if status == current:
        return row
    if status not in _PROJECT_TRANSITIONS.get(current, set()):
        raise V1InvariantError(f"project status transition is not allowed: {current} -> {status}")
    before = current
    row.status = status
    append_audit_event(
        session, event_type="PROJECT_STATUS_CHANGED", entity_type="project", entity_id=row.id,
        actor=actor or "human", reason=reason, payload={"from_status": before, "to_status": status},
    )
    session.flush()
    return row


def change_candidate_stage(session: Session, candidate_id: str, stage: str, *, actor: str, reason: str) -> Candidate:
    row = session.get(Candidate, candidate_id)
    if row is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    current = row.pipeline_stage or "new"
    if stage not in PIPELINE_STAGES:
        raise V1InvariantError(f"unsupported candidate pipeline stage: {stage}")
    if stage == current:
        return row
    if stage not in _STAGE_TRANSITIONS.get(current, set()):
        raise V1InvariantError(f"candidate stage transition is not allowed: {current} -> {stage}")
    transition = CandidateStageTransition(
        project_id=row.project_id, candidate_id=row.id, from_stage=current, to_stage=stage,
        actor=actor or "human", reason=reason,
    )
    row.pipeline_stage = stage
    session.add(transition)
    append_audit_event(
        session, event_type="CANDIDATE_STAGE_CHANGED", entity_type="candidate", entity_id=row.id,
        actor=actor or "human", reason=reason, payload={"from_stage": current, "to_stage": stage},
    )
    session.flush()
    return row


def bulk_change_candidate_stage(session: Session, project_id: str, candidate_ids: Iterable[str], stage: str, *, actor: str, reason: str) -> dict:
    unique_ids = list(dict.fromkeys(str(x) for x in candidate_ids if str(x)))
    if not unique_ids:
        raise V1InvariantError("candidate_ids must not be empty")
    results = []
    updated = failed = 0
    for candidate_id in unique_ids:
        try:
            candidate = session.get(Candidate, candidate_id)
            if candidate is None or candidate.project_id != project_id:
                raise V1NotFoundError(f"candidate not found in project: {candidate_id}")
            change_candidate_stage(session, candidate_id, stage, actor=actor, reason=reason)
            results.append({"candidate_id": candidate_id, "status": "succeeded", "pipeline_stage": stage})
            updated += 1
        except (V1InvariantError, V1NotFoundError) as exc:
            results.append({"candidate_id": candidate_id, "status": "failed", "error": str(exc)})
            failed += 1
    return {"updated": updated, "failed": failed, "items": results}


def pipeline_history(session: Session, candidate_id: str) -> dict:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    rows = session.scalars(
        select(CandidateStageTransition).where(CandidateStageTransition.candidate_id == candidate_id)
        .order_by(CandidateStageTransition.created_at, CandidateStageTransition.id)
    ).all()
    return {
        "candidate_id": candidate_id,
        "current_stage": candidate.pipeline_stage or "new",
        "transitions": [
            {"transition_id": x.id, "from_stage": x.from_stage, "to_stage": x.to_stage,
             "actor": x.actor, "reason": x.reason, "created_at": x.created_at.isoformat()}
            for x in rows
        ],
    }


def project_funnel(session: Session, project_id: str) -> dict:
    if session.get(Project, project_id) is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    rows = session.execute(
        select(Candidate.pipeline_stage, func.count(Candidate.id))
        .where(Candidate.project_id == project_id, Candidate.archived.is_(False))
        .group_by(Candidate.pipeline_stage)
    ).all()
    counts = {stage: 0 for stage in PIPELINE_STAGES}
    for stage, count in rows:
        counts[str(stage or "new")] = int(count)
    return {"project_id": project_id, "total_candidates": sum(counts.values()), "stages": counts}


def create_offer(session: Session, candidate_id: str, *, title: str, compensation_note: str, target_start_date: str, terms: str, actor: str) -> OfferRecord:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    if candidate.pipeline_stage not in {"interview", "offer"}:
        raise V1InvariantError("offer can be created only for a candidate in interview or offer stage")
    row = OfferRecord(
        project_id=candidate.project_id, candidate_id=candidate.id, title=title.strip(),
        compensation_note=compensation_note.strip(), target_start_date=target_start_date.strip(),
        terms=terms.strip(), created_by=actor or "human",
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session, event_type="OFFER_CREATED", entity_type="offer", entity_id=row.id,
        actor=actor or "human", payload={"candidate_id": candidate.id, "status": "draft"},
    )
    return row


def change_offer_status(session: Session, offer_id: str, status: str, *, actor: str, reason: str,
                        expected_status: str | None = None) -> OfferRecord:
    row = session.get(OfferRecord, offer_id)
    if row is None:
        raise V1NotFoundError(f"offer not found: {offer_id}")
    if status not in OFFER_STATES:
        raise V1InvariantError(f"unsupported offer status: {status}")
    current = row.status
    # Conditional status is an additive, backwards-compatible CAS contract.
    # A stale browser window must not silently apply the next transition.
    if expected_status is not None:
        if expected_status not in OFFER_STATES:
            raise V1InvariantError("expected_status must be a valid offer state")
        if current != expected_status:
            raise V1InvariantError("offer status changed; refresh before updating")
    if status == current:
        return row
    if status not in _OFFER_TRANSITIONS.get(current, set()):
        raise V1InvariantError(f"offer status transition is not allowed: {current} -> {status}")
    if expected_status is None:
        # Older clients retain the historical transition behavior.
        row.status = status
    else:
        # Do not rely only on the pre-read status: another session can update
        # after the read. This guarded SQL UPDATE is atomic with the audit row.
        changed = session.execute(
            update(OfferRecord).where(
                OfferRecord.id == offer_id,
                OfferRecord.status == expected_status,
            ).values(status=status)
        ).rowcount
        if changed != 1:
            raise V1InvariantError("offer status changed; refresh before updating")
        session.refresh(row)
    append_audit_event(
        session, event_type="OFFER_STATUS_CHANGED", entity_type="offer", entity_id=row.id,
        actor=actor or "human", reason=reason, payload={"from_status": current, "to_status": status, "candidate_id": row.candidate_id},
    )
    session.flush()
    return row


def offer_view(row: OfferRecord) -> dict:
    return {
        "offer_id": row.id, "project_id": row.project_id, "candidate_id": row.candidate_id,
        "status": row.status, "title": row.title, "compensation_note": row.compensation_note,
        "target_start_date": row.target_start_date, "terms": row.terms, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }
