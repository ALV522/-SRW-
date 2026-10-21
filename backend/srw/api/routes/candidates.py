"""Candidate CRUD and contact routes (ADR-0002 R2, seventh slice).

Eight routes over one entity family: list, summary, search, create, archive,
restore, and the contact pair (read / update). Behaviour is identical to the code
that lived inside ``install_full_workbench_routes``.

Scope note: the task-orchestration routes that also touch candidates -
``batch-intake``, ``files`` (ingest) and ``evidence/extract-task`` - stay in the
aggregate. They enqueue background work and belong with the Job Engine slice, not
with entity CRUD. Splitting by entity would have dragged them in and made this PR
about two different concerns.

Invariants preserved verbatim:

* archive is reversible, but a merged source identity cannot be restored - the
  operator is told to open the canonical candidate instead (409);
* a contact update writes the confirmed-field set, the provenance record and one
  CANDIDATE_CONTACT_UPDATED audit event in the same transaction, and mirrors the
  display name onto the candidate.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.commands import create_candidate
from srw.modules.candidate.models import Candidate, CandidateContact
from srw.modules.recruiting.models import OfferRecord
from srw.recruiting.operations import PIPELINE_STAGES
from srw.runtime.db.session import v1_session_scope


def contact_view(candidate, contact) -> dict:
    return {
        "candidate_id": candidate.id,
        "display_name": contact.display_name if contact else candidate.display_name,
        "phone": contact.phone if contact else "",
        "email": contact.email if contact else "",
        "user_confirmed": bool(contact.user_confirmed) if contact else False,
        "confirmed_fields": json.loads(contact.confirmed_fields_json or "[]") if contact else [],
    }


def candidate_routes(*, factory) -> list[Route]:
    """Bind the candidate entity endpoints to one Core session factory."""

    async def list_candidates(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        query = (request.query_params.get("q") or "").strip()[:200]
        archived = (request.query_params.get("archived") or "all").strip().lower()
        material = (request.query_params.get("material") or "all").strip().lower()
        stage = (request.query_params.get("stage") or "all").strip().lower()
        if archived not in {"all", "active", "archived"}:
            raise V1InvariantError("archived must be all, active, or archived")
        if material not in {"all", "with", "without"}:
            raise V1InvariantError("material must be all, with, or without")
        if stage != "all" and stage not in PIPELINE_STAGES:
            raise V1InvariantError("unsupported pipeline stage")
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", "100"))))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        filters = [Candidate.project_id == pid]
        if query:
            filters.append(func.lower(Candidate.display_name).like(f"%{query.lower()}%"))
        if archived == "active":
            filters.append(Candidate.archived.is_(False))
        elif archived == "archived":
            filters.append(Candidate.archived.is_(True))
        if material == "with":
            filters.append(Candidate.current_material_revision_id.is_not(None))
        elif material == "without":
            filters.append(Candidate.current_material_revision_id.is_(None))
        if stage != "all":
            filters.append(Candidate.pipeline_stage == stage)
        with factory() as session:
            total = session.scalar(select(func.count(Candidate.id)).where(*filters)) or 0
            rows = session.scalars(
                select(Candidate).where(*filters)
                .order_by(Candidate.archived, Candidate.created_at.desc(), Candidate.id)
                .limit(limit).offset(offset)
            ).all()
            return JSONResponse({"candidates": [{
                "candidate_id": x.id, "display_name": x.display_name, "archived": x.archived,
                "merged_into_candidate_id": x.merged_into_candidate_id,
                "pipeline_stage": x.pipeline_stage or "new",
                "has_material": bool(x.current_material_revision_id),
                "created_at": x.created_at.isoformat(),
            } for x in rows], "total": total, "limit": limit, "offset": offset})

    async def candidate_summary(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with factory() as session:
            candidate = session.get(Candidate, cid)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {cid}")
            contact = session.scalar(
                select(CandidateContact).where(CandidateContact.candidate_id == cid))
            offer = session.scalar(
                select(OfferRecord).where(OfferRecord.candidate_id == cid)
                .order_by(OfferRecord.created_at.desc()).limit(1))
            return JSONResponse({
                "candidate_id": candidate.id, "project_id": candidate.project_id,
                "display_name": candidate.display_name,
                "pipeline_stage": candidate.pipeline_stage or "new",
                "archived": bool(candidate.archived),
                "merged_into_candidate_id": candidate.merged_into_candidate_id,
                "has_material": bool(candidate.current_material_revision_id),
                "contact": {
                    "phone": contact.phone if contact else "",
                    "email": contact.email if contact else "",
                    "user_confirmed": bool(contact.user_confirmed) if contact else False,
                },
                "offer_status": offer.status if offer else "",
            })

    async def candidate_search(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        query = (request.query_params.get("q") or "").strip()[:200]
        try:
            limit = min(50, max(1, int(request.query_params.get("limit", "20"))))
        except ValueError as exc:
            raise V1InvariantError("limit must be an integer") from exc
        filters = [Candidate.project_id == pid, Candidate.archived.is_(False)]
        if query:
            filters.append(func.lower(Candidate.display_name).like(f"%{query.lower()}%"))
        with factory() as session:
            rows = session.scalars(
                select(Candidate).where(*filters)
                .order_by(Candidate.display_name, Candidate.id).limit(limit)
            ).all()
            return JSONResponse({"candidates": [{
                "candidate_id": x.id, "display_name": x.display_name,
                "pipeline_stage": x.pipeline_stage or "new",
                "has_material": bool(x.current_material_revision_id),
            } for x in rows]})

    async def add_candidate(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = create_candidate(session, pid, s_field(body, "display_name", required=True))
            return JSONResponse({"candidate_id": row.id, "display_name": row.display_name})

    async def archive_candidate(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with v1_session_scope(factory) as session:
            row = session.get(Candidate, cid)
            if not row:
                raise V1NotFoundError(f"candidate not found: {cid}")
            row.archived = True
            return JSONResponse({"candidate_id": cid, "archived": True})

    async def restore_candidate(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with v1_session_scope(factory) as session:
            row = session.get(Candidate, cid)
            if not row:
                raise V1NotFoundError(f"candidate not found: {cid}")
            if row.merged_into_candidate_id:
                raise V1InvariantError(
                    "merged source identity cannot be restored; open the canonical candidate instead")
            row.archived = False
            return JSONResponse({"candidate_id": cid, "archived": False})

    async def candidate_contact(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with factory() as session:
            candidate = session.get(Candidate, cid)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {cid}")
            contact = session.scalar(
                select(CandidateContact).where(CandidateContact.candidate_id == cid))
            return JSONResponse(contact_view(candidate, contact))

    async def update_candidate_contact(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            candidate = session.get(Candidate, cid)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {cid}")
            contact = session.scalar(
                select(CandidateContact).where(CandidateContact.candidate_id == cid))
            if contact is None:
                contact = CandidateContact(candidate_id=cid, display_name=candidate.display_name)
                session.add(contact)
                session.flush()
            if "display_name" in body:
                name = s_field(body, "display_name", required=True)
                contact.display_name = name
                candidate.display_name = name
            if "phone" in body:
                contact.phone = s_field(body, "phone")
            if "email" in body:
                contact.email = s_field(body, "email")
            if "user_confirmed" in body:
                value = body.get("user_confirmed")
                if not isinstance(value, bool):
                    raise V1InvariantError("user_confirmed must be a boolean")
                contact.user_confirmed = value
            fields = []
            if contact.display_name:
                fields.append("display_name")
            if contact.phone:
                fields.append("phone")
            if contact.email:
                fields.append("email")
            contact.confirmed_fields_json = json.dumps(fields if contact.user_confirmed else [],
                                                       ensure_ascii=False)
            contact.provenance_json = json.dumps(
                {"actor": s_field(body, "actor", default="human"), "source": "manual"},
                ensure_ascii=False)
            append_audit_event(
                session, event_type="CANDIDATE_CONTACT_UPDATED", entity_type="candidate",
                entity_id=cid, actor=s_field(body, "actor", default="human"),
                payload={"confirmed_fields": fields, "user_confirmed": contact.user_confirmed},
            )
            return JSONResponse(contact_view(candidate, contact))

    return [
        Route("/api/v1/projects/{project_id:str}/candidates", list_candidates, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/candidates", add_candidate, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/summary", candidate_summary, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/candidate-search", candidate_search, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/archive", archive_candidate, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/restore", restore_candidate, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/contact", candidate_contact, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/contact", update_candidate_contact, methods=["PATCH"]),
    ]
