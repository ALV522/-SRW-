"""Project lifecycle, standards and contact-list routes (ADR-0002 R2, eighth slice).

Eight routes: status transition, archive, restore, job setup (read-modify and
suggestion), the project audit timeline, the contact queue and its CSV export.

Scope split, stated so the next slice is obvious rather than re-litigated:
``pipeline``, ``cockpit``, ``candidates.csv`` and the candidate ``brief`` /
``handoff`` payloads stay in the aggregate. They are read models and reporting
surfaces that share ``_brief_payload`` and the assessment projection; they move
with that reporting slice, not with lifecycle transitions.

Invariants preserved verbatim:

* archive is a status transition through ``change_project_status`` (so it keeps
  its audit and legality rules) rather than a direct column write;
* restore returns to ``open`` only when a protocol revision exists, otherwise
  ``draft`` - a restored project must never claim to be further along than it is;
* the audit timeline keeps the legacy ``entity_id in (...)`` fallback so events
  written before ``project_id`` was denormalised are still visible;
* CSV export neutralises spreadsheet formula prefixes (``= + - @``) because the
  contact list is opened in Excel by operators.
"""
from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy import func, or_, select
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.models import AuditEvent
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.decision.models import CriterionJudgment, HumanDecision
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.recruiting.models import OfferRecord
from srw.recruiting.operations import change_project_status
from srw.recruiting.workbench import contact_queue, suggest_job_setup, update_job_setup
from srw.runtime.db.session import v1_session_scope


def csv_safe_cell(value) -> str:
    """Neutralise spreadsheet formula prefixes; contacts are opened in Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def project_routes(*, factory) -> list[Route]:
    """Bind the project lifecycle endpoints to one Core session factory."""

    async def project_status(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = change_project_status(
                session, pid, s_field(body, "status", required=True),
                actor=s_field(body, "actor", default="human"),
                reason=s_field(body, "reason"),
            )
            return JSONResponse({"project_id": row.id, "status": row.status})

    async def archive_project(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        with v1_session_scope(factory) as session:
            row = change_project_status(session, pid, "archived", actor="human",
                                        reason="project archived")
            return JSONResponse({"project_id": pid, "status": row.status})

    async def restore_project(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        with v1_session_scope(factory) as session:
            project = session.get(Project, pid)
            if not project:
                raise V1NotFoundError(f"project not found: {pid}")
            target = "open" if project.current_protocol_revision_id else "draft"
            row = change_project_status(session, pid, target, actor="human",
                                        reason="project restored")
            return JSONResponse({"project_id": pid, "status": row.status})

    async def job_setup(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(update_job_setup(session, pid, body))

    async def job_setup_suggest(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        with v1_session_scope(factory) as session:
            return JSONResponse(suggest_job_setup(session, pid))

    async def project_audit(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as session:
            if session.get(Project, pid) is None:
                raise V1NotFoundError(f"project not found: {pid}")
            revisions = session.scalars(
                select(ProtocolRevision).where(ProtocolRevision.project_id == pid)
                .order_by(ProtocolRevision.revision.desc())
            ).all()
            candidate_ids = list(session.scalars(
                select(Candidate.id).where(Candidate.project_id == pid)).all())
            source_ids = list(session.scalars(
                select(Source.id).where(Source.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            claim_ids = list(session.scalars(
                select(Claim.id).where(Claim.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            judgment_ids = list(session.scalars(
                select(CriterionJudgment.id).where(CriterionJudgment.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            decision_ids = list(session.scalars(
                select(HumanDecision.id).where(HumanDecision.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            event_ids = list(session.scalars(
                select(RecruitmentEvent.id).where(RecruitmentEvent.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            offer_ids = list(session.scalars(
                select(OfferRecord.id).where(OfferRecord.project_id == pid)).all())
            # Legacy rows predate the denormalised project_id column; without this
            # fallback the timeline would silently lose history after the move.
            legacy_ids = [pid, *candidate_ids, *source_ids, *claim_ids, *judgment_ids,
                          *decision_ids, *event_ids, *offer_ids]
            filt = or_(AuditEvent.project_id == pid, AuditEvent.entity_id.in_(legacy_ids))
            total = session.scalar(select(func.count(AuditEvent.id)).where(filt)) or 0
            events = session.scalars(
                select(AuditEvent).where(filt)
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                .limit(limit).offset(offset)
            ).all()
            return JSONResponse({
                "protocol_revisions": [{
                    "revision_id": x.id, "revision": x.revision, "state": x.state,
                    "created_at": x.created_at.isoformat(),
                    "published_at": x.published_at.isoformat() if x.published_at else None,
                    "content_hash": x.content_hash,
                } for x in revisions],
                "audit_events": [{
                    "event_id": x.id, "event_type": x.event_type, "entity_type": x.entity_type,
                    "entity_id": x.entity_id, "project_id": x.project_id,
                    "candidate_id": x.candidate_id, "actor": x.actor, "reason": x.reason,
                    "created_at": x.created_at.isoformat(),
                } for x in events],
                "total": int(total), "limit": limit, "offset": offset,
            })

    async def project_contact_queue(request: Request) -> JSONResponse:
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as session:
            return JSONResponse(contact_queue(session, request.path_params["project_id"],
                                              limit=limit, offset=offset))

    async def contact_list_csv(request: Request) -> PlainTextResponse:
        pid = request.path_params["project_id"]
        with factory() as session:
            queue = contact_queue(session, pid, limit=10000, offset=0)
            out = StringIO()
            fields = ["candidate_id", "display_name", "phone", "email", "priority",
                      "contact_status", "next_contact_at", "next_action"]
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            for row in queue["candidates"]:
                writer.writerow({
                    "candidate_id": row["candidate_id"],
                    "display_name": csv_safe_cell(row["display_name"]),
                    "phone": csv_safe_cell(row["phone"]),
                    "email": csv_safe_cell(row["email"]),
                    "priority": row["priority"],
                    "contact_status": row["contact_status"],
                    "next_contact_at": csv_safe_cell(row["next_contact_at"] or ""),
                    "next_action": csv_safe_cell(row["reason"] or "联系并核实未决条件"),
                })
            return PlainTextResponse(
                out.getvalue(), media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="contact-list-{pid}.csv"'},
            )

    return [
        Route("/api/v1/projects/{project_id:str}/status", project_status, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/archive", archive_project, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/restore", restore_project, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/job-setup", job_setup, methods=["PATCH"]),
        Route("/api/v1/projects/{project_id:str}/job-setup/suggest", job_setup_suggest, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/audit", project_audit, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/contact-queue", project_contact_queue, methods=["GET"]),
        Route("/api/v1/projects/{project_id:str}/contact-list.csv", contact_list_csv, methods=["GET"]),
    ]
