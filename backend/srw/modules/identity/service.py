from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate, CandidateContact
from srw.modules.identity.models import CandidateIdentityReview
from srw.modules.protocol.repository import ensure_project_exists


def _phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("0086") and len(digits) > 11:
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    return digits


def _email(value: str) -> str:
    return (value or "").strip().casefold()


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scan_project_identity(session: Session, project_id: str, *, actor: str = "system") -> dict:
    ensure_project_exists(session, project_id)
    candidates = list(session.scalars(select(Candidate).where(Candidate.project_id == project_id, Candidate.archived.is_(False))).all())
    candidate_ids = [row.id for row in candidates]
    contacts = list(session.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
    by_candidate = {row.candidate_id: row for row in contacts}
    indexes: dict[str, dict[str, list[str]]] = {"email": defaultdict(list), "phone": defaultdict(list)}
    for candidate in candidates:
        contact = by_candidate.get(candidate.id)
        if not contact:
            continue
        email = _email(contact.email)
        phone = _phone(contact.phone)
        if email:
            indexes["email"][email].append(candidate.id)
        if len(phone) >= 7:
            indexes["phone"][phone].append(candidate.id)

    existing = {
        (row.candidate_a_id, row.candidate_b_id): row
        for row in session.scalars(select(CandidateIdentityReview).where(CandidateIdentityReview.project_id == project_id)).all()
    }
    created = 0
    matches: list[dict] = []
    for reason in ("email", "phone"):
        for normalized, ids in indexes[reason].items():
            if len(ids) < 2:
                continue
            ids = sorted(set(ids))
            for i, first in enumerate(ids):
                for second in ids[i + 1:]:
                    pair = _pair(first, second)
                    row = existing.get(pair)
                    if row is None:
                        row = CandidateIdentityReview(
                            project_id=project_id,
                            candidate_a_id=pair[0], candidate_b_id=pair[1],
                            match_reason=f"exact_{reason}", match_value_hash=_hash_value(normalized),
                            source="deterministic_contact", status="pending",
                        )
                        session.add(row); session.flush(); existing[pair] = row; created += 1
                        append_audit_event(session, event_type="IDENTITY_REVIEW_CREATED", entity_type="candidate_identity_review", entity_id=row.id, actor=actor, payload={"match_reason": row.match_reason}, project_id=project_id)
                    matches.append({"review_id": row.id, "candidate_a_id": pair[0], "candidate_b_id": pair[1], "match_reason": row.match_reason, "status": row.status})
    session.flush()
    return {"project_id": project_id, "created": created, "matches": matches}


def _output(session: Session, row: CandidateIdentityReview) -> dict:
    a = session.get(Candidate, row.candidate_a_id)
    b = session.get(Candidate, row.candidate_b_id)
    merged = bool(
        (a and a.merged_into_candidate_id == row.candidate_b_id)
        or (b and b.merged_into_candidate_id == row.candidate_a_id)
    )
    canonical_id = ""
    if a and a.merged_into_candidate_id == row.candidate_b_id:
        canonical_id = row.candidate_b_id
    elif b and b.merged_into_candidate_id == row.candidate_a_id:
        canonical_id = row.candidate_a_id
    return {
        "review_id": row.id, "project_id": row.project_id,
        "candidate_a": {"candidate_id": row.candidate_a_id, "display_name": a.display_name if a else "", "archived": bool(a.archived) if a else False, "merged_into_candidate_id": a.merged_into_candidate_id if a else None},
        "candidate_b": {"candidate_id": row.candidate_b_id, "display_name": b.display_name if b else "", "archived": bool(b.archived) if b else False, "merged_into_candidate_id": b.merged_into_candidate_id if b else None},
        "match_reason": row.match_reason, "source": row.source, "status": row.status,
        "resolution_note": row.resolution_note, "resolved_by": row.resolved_by,
        "created_at": row.created_at.isoformat(), "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "merge_performed": merged, "canonical_candidate_id": canonical_id or None,
    }


def list_identity_reviews(session: Session, project_id: str, *, status: str | None = None) -> list[dict]:
    ensure_project_exists(session, project_id)
    query = select(CandidateIdentityReview).where(CandidateIdentityReview.project_id == project_id)
    if status:
        query = query.where(CandidateIdentityReview.status == status)
    rows = session.scalars(query.order_by(CandidateIdentityReview.created_at.desc())).all()
    return [_output(session, row) for row in rows]


def resolve_identity_review(session: Session, review_id: str, *, status: str, actor: str, note: str = "") -> dict:
    if status not in {"confirmed_same", "confirmed_distinct", "dismissed"}:
        raise V1InvariantError("identity review status must be confirmed_same, confirmed_distinct or dismissed")
    if not actor.strip():
        raise V1InvariantError("actor is required")
    row = session.get(CandidateIdentityReview, review_id)
    if row is None:
        raise V1NotFoundError(f"identity review not found: {review_id}")
    if row.status != "pending":
        raise V1InvariantError("identity review is already resolved")
    row.status = status; row.resolution_note = note.strip(); row.resolved_by = actor.strip(); row.resolved_at = utc_now()
    session.flush()
    append_audit_event(session, event_type="IDENTITY_REVIEW_RESOLVED", entity_type="candidate_identity_review", entity_id=row.id, actor=actor, reason=note, payload={"status": status, "merge_performed": False}, project_id=row.project_id)
    return _output(session, row)


def _business_history_counts(session: Session, candidate_id: str) -> dict[str, int]:
    """Count persisted history that must remain on the source identity after merge.

    Identity merge intentionally does not rewrite historical business records. The
    canonical candidate receives a copy of the source's *current material* while
    prior evaluations, events and decisions remain attached to the archived source
    candidate for auditability.
    """
    from sqlalchemy import func
    from srw.modules.candidate.models import Claim, Source
    from srw.modules.decision.models import CriterionJudgment, HumanDecision
    from srw.modules.fullworkbench import RecruitmentEvent, ReevaluationDraft, EvaluationSnapshot, TaskRecord
    from srw.modules.recruiting.models import CandidateStageTransition, OfferRecord
    from srw.modules.recruiting.operations_models import CandidateActionPlan, InterviewScorecardSubmission
    from srw.modules.work.models import WorkItem
    from srw.modules.calibration.models import JudgmentReviewItem

    models = {
        "sources": Source,
        "claims": Claim,
        "judgments": CriterionJudgment,
        "human_decisions": HumanDecision,
        "events": RecruitmentEvent,
        "reevaluations": ReevaluationDraft,
        "evaluation_snapshots": EvaluationSnapshot,
        "tasks": TaskRecord,
        "stage_transitions": CandidateStageTransition,
        "offers": OfferRecord,
        "action_plans": CandidateActionPlan,
        "scorecards": InterviewScorecardSubmission,
        "work_items": WorkItem,
        "judgment_reviews": JudgmentReviewItem,
    }
    return {
        name: int(session.scalar(select(func.count()).select_from(model).where(model.candidate_id == candidate_id)) or 0)
        for name, model in models.items()
    }


def _contact_dict(row: CandidateContact | None) -> dict:
    return {
        "phone": row.phone if row else "",
        "email": row.email if row else "",
        "display_name": row.display_name if row else "",
        "user_confirmed": bool(row.user_confirmed) if row else False,
    }


def _review_for_pair(session: Session, project_id: str, a: str, b: str) -> CandidateIdentityReview | None:
    first, second = _pair(a, b)
    return session.scalar(
        select(CandidateIdentityReview).where(
            CandidateIdentityReview.project_id == project_id,
            CandidateIdentityReview.candidate_a_id == first,
            CandidateIdentityReview.candidate_b_id == second,
        )
    )


def identity_merge_preview(
    session: Session,
    review_id: str,
    *,
    target_candidate_id: str,
) -> dict:
    """Return a non-mutating, explicit preview for a reviewed duplicate pair."""
    from srw.modules.candidate.repository import get_current_source_ids

    review = session.get(CandidateIdentityReview, review_id)
    if review is None:
        raise V1NotFoundError(f"identity review not found: {review_id}")
    if review.status != "confirmed_same":
        raise V1InvariantError("identity merge requires a confirmed_same review")
    pair = {review.candidate_a_id, review.candidate_b_id}
    if target_candidate_id not in pair:
        raise V1InvariantError("target candidate is not part of this identity review")
    source_candidate_id = next(iter(pair - {target_candidate_id}))
    target = session.get(Candidate, target_candidate_id)
    source = session.get(Candidate, source_candidate_id)
    if target is None or source is None:
        raise V1NotFoundError("identity merge candidate not found")
    if target.project_id != source.project_id or target.project_id != review.project_id:
        raise V1InvariantError("identity merge candidates must belong to the same project")

    blocked_reason = ""
    if target.id == source.id:
        blocked_reason = "target and source candidate are identical"
    elif target.merged_into_candidate_id:
        blocked_reason = "target candidate is already merged into another identity"
    elif source.merged_into_candidate_id:
        blocked_reason = "source candidate is already merged into another identity"

    try:
        source_current_ids = get_current_source_ids(session, source.id) if source.current_material_revision_id else []
    except Exception:
        source_current_ids = []
    try:
        target_current_ids = get_current_source_ids(session, target.id) if target.current_material_revision_id else []
    except Exception:
        target_current_ids = []

    source_contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == source.id))
    target_contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == target.id))
    conflicts: list[str] = []
    if source_contact and target_contact:
        if _email(source_contact.email) and _email(target_contact.email) and _email(source_contact.email) != _email(target_contact.email):
            conflicts.append("email")
        if _phone(source_contact.phone) and _phone(target_contact.phone) and _phone(source_contact.phone) != _phone(target_contact.phone):
            conflicts.append("phone")

    counts = _business_history_counts(session, source.id)
    preserved_history = sum(v for k, v in counts.items() if k not in {"sources"})
    return {
        "review_id": review.id,
        "project_id": review.project_id,
        "target_candidate": {"candidate_id": target.id, "display_name": target.display_name, "pipeline_stage": target.pipeline_stage or "new"},
        "source_candidate": {"candidate_id": source.id, "display_name": source.display_name, "pipeline_stage": source.pipeline_stage or "new"},
        "target_contact": _contact_dict(target_contact),
        "source_contact": _contact_dict(source_contact),
        "contact_conflicts": conflicts,
        "source_current_source_count": len(source_current_ids),
        "target_current_source_count": len(target_current_ids),
        "source_business_history_counts": counts,
        "source_has_preserved_business_history": preserved_history > 0,
        "effects": {
            "copy_source_current_material_to_target": bool(source_current_ids),
            "publish_new_target_material_revision": bool(source_current_ids),
            "fill_blank_target_contact_fields": True,
            "overwrite_conflicting_target_contact_fields": False,
            "archive_source_candidate": True,
            "set_source_merged_into_candidate_id": target.id,
            "rewrite_historical_business_records": False,
            "change_target_pipeline_stage": False,
        },
        "can_merge": not blocked_reason,
        "blocked_reason": blocked_reason,
    }


def _merge_contact(session: Session, target: Candidate, source: Candidate) -> dict:
    import json
    target_contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == target.id))
    source_contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == source.id))
    if source_contact is None:
        return {"filled": [], "conflicts_preserved": []}
    if target_contact is None:
        target_contact = CandidateContact(candidate_id=target.id, display_name=target.display_name)
        session.add(target_contact)
        session.flush()
    filled: list[str] = []
    conflicts: list[str] = []
    for field, normalizer in (("email", _email), ("phone", _phone)):
        src = getattr(source_contact, field) or ""
        dst = getattr(target_contact, field) or ""
        if src and not dst:
            setattr(target_contact, field, src)
            filled.append(field)
        elif src and dst and normalizer(src) != normalizer(dst):
            conflicts.append(field)
    if source_contact.display_name and not target_contact.display_name:
        target_contact.display_name = source_contact.display_name
        filled.append("display_name")
    try:
        provenance = json.loads(target_contact.provenance_json or "{}")
        if not isinstance(provenance, dict):
            provenance = {}
    except Exception:
        provenance = {}
    provenance["identity_merge"] = {"source_candidate_id": source.id, "filled_fields": filled, "conflicts_preserved": conflicts}
    target_contact.provenance_json = json.dumps(provenance, ensure_ascii=False, separators=(",", ":"))
    return {"filled": filled, "conflicts_preserved": conflicts}


def commit_identity_merge(
    session: Session,
    review_id: str,
    *,
    target_candidate_id: str,
    actor: str,
    note: str = "",
) -> dict:
    """Commit a conservative canonical-identity merge.

    Current source material is cloned to the target and a new target material
    revision is published. Historical records stay on the archived source identity.
    This preserves the audit lineage and avoids rewriting past decisions.
    """
    import json
    from srw.modules.candidate.commands import add_source
    from srw.modules.candidate.models import Source
    from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids

    actor = (actor or "").strip()
    if not actor:
        raise V1InvariantError("actor is required")
    preview = identity_merge_preview(session, review_id, target_candidate_id=target_candidate_id)
    if not preview["can_merge"]:
        raise V1InvariantError(preview["blocked_reason"])

    target_id = preview["target_candidate"]["candidate_id"]
    source_id = preview["source_candidate"]["candidate_id"]
    target = session.get(Candidate, target_id)
    source = session.get(Candidate, source_id)
    assert target is not None and source is not None

    target_current = get_current_source_ids(session, target.id) if target.current_material_revision_id else []
    source_current = get_current_source_ids(session, source.id) if source.current_material_revision_id else []
    cloned_ids: list[str] = []
    for source_row_id in source_current:
        original = session.get(Source, source_row_id)
        if original is None:
            continue
        try:
            metadata = json.loads(original.metadata_json or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        metadata = dict(metadata)
        metadata["identity_merge_origin"] = {
            "source_candidate_id": source.id,
            "source_id": original.id,
            "review_id": review_id,
        }
        clone = add_source(
            session,
            target.id,
            source_kind=original.source_kind,
            content_hash=original.content_hash,
            text_content=original.text_content,
            media_type=original.media_type,
            blob_hash=original.blob_hash,
            metadata=metadata,
        )
        cloned_ids.append(clone.id)

    combined = list(dict.fromkeys([*target_current, *cloned_ids]))
    new_material_revision_id = target.current_material_revision_id
    if combined and combined != target_current:
        material = MaterialRepository(session).publish_revision(
            target.id,
            combined,
            {
                "action": "identity_merge",
                "review_id": review_id,
                "source_candidate_id": source.id,
                "actor": actor,
            },
        )
        new_material_revision_id = material.id

    contact_result = _merge_contact(session, target, source)
    source.archived = True
    source.merged_into_candidate_id = target.id
    session.flush()

    # Close any still-open reviews involving the archived source. A fresh scan can
    # recreate canonical target-vs-third-party pairs if needed.
    rows = session.scalars(
        select(CandidateIdentityReview).where(
            CandidateIdentityReview.project_id == target.project_id,
            CandidateIdentityReview.status == "pending",
            ((CandidateIdentityReview.candidate_a_id == source.id) | (CandidateIdentityReview.candidate_b_id == source.id)),
        )
    ).all()
    for row in rows:
        row.status = "dismissed"
        row.resolution_note = "source identity merged into canonical candidate"
        row.resolved_by = actor
        row.resolved_at = utc_now()

    append_audit_event(
        session,
        event_type="IDENTITY_MERGE_COMMITTED",
        entity_type="candidate",
        entity_id=target.id,
        actor=actor,
        reason=note,
        payload={
            "review_id": review_id,
            "source_candidate_id": source.id,
            "target_candidate_id": target.id,
            "cloned_source_ids": cloned_ids,
            "new_material_revision_id": new_material_revision_id,
            "history_rewritten": False,
            "contact": contact_result,
            "source_business_history_counts": preview["source_business_history_counts"],
        },
        project_id=target.project_id,
        candidate_id=target.id,
    )
    session.flush()
    return {
        **preview,
        "merged": True,
        "actor": actor,
        "cloned_source_ids": cloned_ids,
        "new_material_revision_id": new_material_revision_id,
        "contact_merge": contact_result,
        "source_archived": True,
        "source_merged_into_candidate_id": target.id,
        "history_rewritten": False,
    }


def merged_identity_history(session: Session, target_candidate_id: str) -> list[dict]:
    target = session.get(Candidate, target_candidate_id)
    if target is None:
        raise V1NotFoundError(f"candidate not found: {target_candidate_id}")
    sources = session.scalars(
        select(Candidate).where(Candidate.merged_into_candidate_id == target_candidate_id).order_by(Candidate.created_at.asc())
    ).all()
    return [
        {
            "candidate_id": row.id,
            "display_name": row.display_name,
            "archived": bool(row.archived),
            "pipeline_stage": row.pipeline_stage or "new",
            "business_history_counts": _business_history_counts(session, row.id),
        }
        for row in sources
    ]
