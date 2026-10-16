"""Version-bound ranked shortlist projection and immutable publications.

The shortlist is a decision-support artifact, not an employment decision. Only
candidates whose assessment is publishable_for_comparison receive a rank.
Unknown/conflicted evidence remains explicitly unranked.
"""
from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import canonical_json_bytes, content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.decision.models import ShortlistPublication
from srw.modules.protocol.models import Project


def _candidate_row(session: Session, candidate: Candidate, *, evaluation_policy_revision: str) -> dict:
    if not candidate.current_material_revision_id:
        return {
            "candidate_id": candidate.id,
            "display_name": candidate.display_name,
            "pipeline_stage": candidate.pipeline_stage or "new",
            "rankable": False,
            "fit_score": None,
            "evidence_coverage": 0.0,
            "decision_ready": False,
            "blocking_keys": [],
            "unresolved_keys": [],
            "conflict_keys": [],
            "reason": "no_current_material",
            "material_revision_id": None,
            "decision_context_hash": "",
        }
    try:
        assessment = get_candidate_assessment(
            session,
            candidate.id,
            evaluation_policy_revision=evaluation_policy_revision,
        )
    except Exception as exc:
        return {
            "candidate_id": candidate.id,
            "display_name": candidate.display_name,
            "pipeline_stage": candidate.pipeline_stage or "new",
            "rankable": False,
            "fit_score": None,
            "evidence_coverage": 0.0,
            "decision_ready": False,
            "blocking_keys": [],
            "unresolved_keys": [],
            "conflict_keys": [],
            "reason": f"assessment_unavailable:{type(exc).__name__}",
            "material_revision_id": candidate.current_material_revision_id,
            "decision_context_hash": "",
        }
    return {
        "candidate_id": candidate.id,
        "display_name": candidate.display_name,
        "pipeline_stage": candidate.pipeline_stage or "new",
        "rankable": bool(assessment["publishable_for_comparison"] and assessment["fit_score"] is not None),
        "fit_score": assessment["fit_score"],
        "evidence_coverage": assessment["evidence_coverage"],
        "decision_ready": assessment["decision_ready"],
        "blocking_keys": list(assessment["blocking_keys"]),
        "unresolved_keys": list(assessment["unresolved_keys"]),
        "conflict_keys": list(assessment["conflict_keys"]),
        "reason": "rankable" if assessment["publishable_for_comparison"] else "evidence_not_closed",
        "material_revision_id": candidate.current_material_revision_id,
        "decision_context_hash": assessment["decision_context_hash"],
    }


def build_ranked_shortlist(session: Session, project_id: str, *, evaluation_policy_revision: str) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    if not project.current_protocol_revision_id:
        raise V1InvariantError("ranked shortlist requires a published recruitment protocol")
    candidates = session.scalars(
        select(Candidate).where(
            Candidate.project_id == project_id,
            Candidate.archived.is_(False),
            Candidate.merged_into_candidate_id.is_(None),
        ).order_by(Candidate.created_at.asc(), Candidate.id.asc())
    ).all()
    rows = [_candidate_row(session, row, evaluation_policy_revision=evaluation_policy_revision) for row in candidates]
    ranked = [row for row in rows if row["rankable"]]
    ranked.sort(key=lambda row: (-float(row["fit_score"]), -float(row["evidence_coverage"]), row["display_name"].casefold(), row["candidate_id"]))
    last_key = None
    dense_rank = 0
    for position, row in enumerate(ranked, start=1):
        key = (row["fit_score"], row["evidence_coverage"])
        if key != last_key:
            dense_rank += 1
            last_key = key
        row["position"] = position
        row["rank"] = dense_rank
    unranked = [row for row in rows if not row["rankable"]]
    return {
        "project_id": project_id,
        "protocol_revision_id": project.current_protocol_revision_id,
        "evaluation_policy_revision": evaluation_policy_revision,
        "ranked": ranked,
        "unranked": unranked,
        "ranked_count": len(ranked),
        "unranked_count": len(unranked),
        "semantics": {
            "artifact": "decision_support_shortlist",
            "final_decision": False,
            "operational_priority_used": False,
            "protected_attribute_inference": False,
            "ranking_basis": "published protocol + human/evidence-bound criterion judgments",
            "unknown_evidence_policy": "unranked_not_zero",
        },
    }


def publish_ranked_shortlist(session: Session, project_id: str, *, evaluation_policy_revision: str, actor: str) -> dict:
    actor = (actor or "").strip()
    if not actor:
        raise V1InvariantError("actor is required")
    payload = build_ranked_shortlist(session, project_id, evaluation_policy_revision=evaluation_policy_revision)
    if not payload["ranked"]:
        raise V1InvariantError("no candidate is currently publishable for ranked comparison")
    frozen = {
        **payload,
        "published_by": actor,
    }
    digest = content_hash(frozen)
    row = ShortlistPublication(
        project_id=project_id,
        protocol_revision_id=payload["protocol_revision_id"],
        evaluation_policy_revision=evaluation_policy_revision,
        payload_json=canonical_json_bytes(frozen).decode("utf-8"),
        content_hash=digest,
        created_by=actor,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        event_type="RANKED_SHORTLIST_PUBLISHED",
        entity_type="shortlist_publication",
        entity_id=row.id,
        actor=actor,
        after_hash=digest,
        payload={"ranked_count": payload["ranked_count"], "unranked_count": payload["unranked_count"], "final_decision": False},
        project_id=project_id,
    )
    return {
        "publication_id": row.id,
        "content_hash": digest,
        "created_by": actor,
        "created_at": row.created_at.isoformat(),
        **frozen,
    }


def list_shortlist_publications(session: Session, project_id: str, *, limit: int = 20) -> list[dict]:
    rows = session.scalars(
        select(ShortlistPublication).where(ShortlistPublication.project_id == project_id).order_by(ShortlistPublication.created_at.desc()).limit(limit)
    ).all()
    output: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        output.append({
            "publication_id": row.id,
            "protocol_revision_id": row.protocol_revision_id,
            "evaluation_policy_revision": row.evaluation_policy_revision,
            "content_hash": row.content_hash,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat(),
            "ranked_count": int(payload.get("ranked_count") or len(payload.get("ranked") or [])),
            "unranked_count": int(payload.get("unranked_count") or len(payload.get("unranked") or [])),
        })
    return output


def get_shortlist_publication(session: Session, publication_id: str) -> dict:
    row = session.get(ShortlistPublication, publication_id)
    if row is None:
        raise V1NotFoundError(f"shortlist publication not found: {publication_id}")
    try:
        payload = json.loads(row.payload_json)
    except Exception as exc:
        raise V1InvariantError("shortlist publication payload is invalid") from exc
    return {
        "publication_id": row.id,
        "content_hash": row.content_hash,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        **payload,
    }
