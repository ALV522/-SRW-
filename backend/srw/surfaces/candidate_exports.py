"""Candidate comparison and CSV export read models (ADR-0002 slice 4).

Extracted from the HTTP layer; aggregation, decision-context rules and the
spreadsheet formula-injection guard are unchanged. HTTP adapters keep path
parsing and response headers only.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from sqlalchemy import select

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import decision_context_hash
from srw.modules.candidate.models import Candidate, CandidateContact
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.decision.models import CriterionJudgment
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.models import OfferRecord
from srw.recruiting.workbench import contact_queue

COMPARE_NOTE = (
    "Comparison is limited to the same project and current protocol/material decision context. "
    "Fit is shown only when evidence is publishable; no automatic hiring decision is made."
)


def csv_safe_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection for untrusted cell values."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def render_csv(fields: list[str], rows: list[dict]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def compare_candidates(session, candidate_ids: list[str], *, evaluation_policy_revision: str) -> dict:
    """Compare 2-5 candidates of one project under the current decision context."""
    candidates = [session.get(Candidate, cid) for cid in candidate_ids]
    if any(c is None for c in candidates):
        raise V1NotFoundError("one or more candidates were not found")
    project_ids = {c.project_id for c in candidates if c is not None}
    if len(project_ids) != 1:
        raise V1InvariantError("compare candidates must belong to the same project")
    pid = next(iter(project_ids))
    project = session.get(Project, pid)
    if not project or not project.current_protocol_revision_id:
        raise V1InvariantError("project has no published protocol")
    protocol_id = project.current_protocol_revision_id
    payload = ProtocolRepository(session).get_payload(protocol_id)
    criteria = [
        {
            "criterion_key": str(x.get("criterion_key") or ""),
            "name": str(x.get("name") or ""),
            "decision_critical": bool(x.get("decision_critical", False)),
        }
        for x in (payload.get("criteria") or [])
        if isinstance(x, dict)
    ]
    contacts = {
        x.candidate_id: x
        for x in session.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(candidate_ids))).all()
    }
    offers_by_candidate = {}
    for offer in session.scalars(
        select(OfferRecord)
        .where(OfferRecord.candidate_id.in_(candidate_ids))
        .order_by(OfferRecord.created_at.desc(), OfferRecord.id.desc())
    ).all():
        offers_by_candidate.setdefault(offer.candidate_id, offer)
    judgments = session.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(candidate_ids))).all()
    judgment_map = {}
    for c in candidates:
        if c is None or not c.current_material_revision_id:
            continue
        expected = decision_context_hash(protocol_id, c.current_material_revision_id, evaluation_policy_revision)
        for j in judgments:
            if j.candidate_id == c.id and j.decision_context_hash == expected:
                judgment_map[(c.id, j.criterion_key)] = j
    rows = []
    for c in candidates:
        contact = contacts.get(c.id)
        offer = offers_by_candidate.get(c.id)
        crit = []
        for definition in criteria:
            j = judgment_map.get((c.id, definition["criterion_key"]))
            crit.append(
                {
                    **definition,
                    "status": j.status if j else "missing",
                    "evidence_level": j.evidence_level if j else "none",
                    "reason": j.reason if j else "",
                    "gap": j.gap if j else "",
                }
            )
        assessment = None
        if c.current_material_revision_id:
            try:
                assessment = get_candidate_assessment(s, c.id, evaluation_policy_revision=evaluation_policy_revision)
            except Exception:
                assessment = None
        rows.append(
            {
                "candidate_id": c.id,
                "display_name": c.display_name,
                "pipeline_stage": c.pipeline_stage or "new",
                "has_material": bool(c.current_material_revision_id),
                "contact": {
                    "phone": contact.phone if contact else "",
                    "email": contact.email if contact else "",
                    "user_confirmed": bool(contact.user_confirmed) if contact else False,
                },
                "offer_status": offer.status if offer else "",
                "assessment": assessment,
                "criteria": crit,
            }
        )
    return {
        "project_id": pid,
        "protocol_revision_id": protocol_id,
        "evaluation_policy_revision": evaluation_policy_revision,
        "criteria": criteria,
        "candidates": rows,
        "note": COMPARE_NOTE,
    }


def candidates_csv_text(session, *, project_id: str, evaluation_policy_revision: str) -> str:
    """Render the project candidate export as CSV text (formula-injection guarded)."""
    project = session.get(Project, project_id)
    if project is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    protocol_id = project.current_protocol_revision_id or ""
    protocol_payload = ProtocolRepository(session).get_payload(protocol_id) if protocol_id else {"criteria": []}
    definitions = [x for x in (protocol_payload.get("criteria") or []) if isinstance(x, dict)]
    rows = session.scalars(select(Candidate).where(Candidate.project_id == project_id).order_by(Candidate.created_at, Candidate.id)).all()
    ids = [x.id for x in rows]
    contacts = {
        x.candidate_id: x
        for x in session.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(ids))).all()
    } if ids else {}
    offers_by_candidate = {}
    if ids:
        for offer in session.scalars(
            select(OfferRecord)
            .where(OfferRecord.candidate_id.in_(ids))
            .order_by(OfferRecord.created_at.desc(), OfferRecord.id.desc())
        ).all():
            offers_by_candidate.setdefault(offer.candidate_id, offer)
    all_j = session.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(ids))).all() if ids else []
    by_candidate = {}
    for x in rows:
        if not protocol_id or not x.current_material_revision_id:
            continue
        h = decision_context_hash(protocol_id, x.current_material_revision_id, evaluation_policy_revision)
        by_candidate[x.id] = {j.criterion_key: j for j in all_j if j.candidate_id == x.id and j.decision_context_hash == h}
    generated = datetime.now(timezone.utc).isoformat()
    fields = [
        "candidate_id", "display_name", "pipeline_stage", "archived", "has_material", "phone", "email",
        "contact_confirmed", "offer_status", "protocol_revision_id", "evaluation_policy_revision",
        "criteria_summary", "evidence_gaps", "created_at", "generated_at",
    ]
    out_rows = []
    for x in rows:
        contact = contacts.get(x.id)
        offer = offers_by_candidate.get(x.id)
        js = by_candidate.get(x.id, {})
        summaries = []
        gaps = []
        for d in definitions:
            key = str(d.get("criterion_key") or "")
            name = str(d.get("name") or key)
            j = js.get(key)
            status = j.status if j else "missing"
            evidence = j.evidence_level if j else "none"
            summaries.append(f"{name}:{status}/{evidence}")
            if not j or j.gap:
                gaps.append(f"{name}:{j.gap if j and j.gap else '待核实'}")
        out_rows.append(
            {
                "candidate_id": x.id,
                "display_name": csv_safe_cell(x.display_name),
                "pipeline_stage": x.pipeline_stage or "new",
                "archived": int(x.archived),
                "has_material": int(bool(x.current_material_revision_id)),
                "phone": csv_safe_cell(contact.phone if contact else ""),
                "email": csv_safe_cell(contact.email if contact else ""),
                "contact_confirmed": int(bool(contact.user_confirmed)) if contact else 0,
                "offer_status": offer.status if offer else "",
                "protocol_revision_id": protocol_id,
                "evaluation_policy_revision": evaluation_policy_revision,
                "criteria_summary": csv_safe_cell(" | ".join(summaries)),
                "evidence_gaps": csv_safe_cell(" | ".join(gaps)),
                "created_at": x.created_at.isoformat(),
                "generated_at": generated,
            }
        )
    return render_csv(fields, out_rows)


def contact_list_csv_text(session, *, project_id: str) -> str:
    """Render the project contact queue as CSV text (formula-injection guarded)."""
    queue = contact_queue(session, project_id, limit=10000, offset=0)
    fields = ["candidate_id", "display_name", "phone", "email", "priority", "contact_status", "next_contact_at", "next_action"]
    out_rows = [
        {
            "candidate_id": x["candidate_id"],
            "display_name": csv_safe_cell(x["display_name"]),
            "phone": csv_safe_cell(x["phone"]),
            "email": csv_safe_cell(x["email"]),
            "priority": x["priority"],
            "contact_status": x["contact_status"],
            "next_contact_at": csv_safe_cell(x["next_contact_at"] or ""),
            "next_action": csv_safe_cell(x["reason"] or "联系并核实未决条件"),
        }
        for x in queue["candidates"]
    ]
    return render_csv(fields, out_rows)
