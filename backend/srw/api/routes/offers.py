"""Offer routes: first domain extracted from the fullworkbench aggregate.

Behaviour is intentionally identical to the code that lived inside
``install_full_workbench_routes``: same paths, same methods, same response
bodies, same error paths, same transaction boundaries. The only change is that
the handlers are now built from an explicit factory parameter instead of being
closures over the installer's local scope.

The offer state machine itself stays in ``srw.recruiting.operations`` - this
module is a transport adapter and must not re-implement business rules
(ADR-0002 §2.3).
"""
from __future__ import annotations

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.kernel.errors import V1NotFoundError
from srw.modules.candidate.models import Candidate
from srw.modules.recruiting.models import OfferRecord
from srw.recruiting.operations import change_offer_status, create_offer, offer_view
from srw.runtime.db.session import v1_session_scope


def offer_routes(*, factory) -> list[Route]:
    """Bind the offer endpoints to one Core session factory."""

    async def candidate_offers(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with factory() as session:
            if session.get(Candidate, cid) is None:
                raise V1NotFoundError(f"candidate not found: {cid}")
            rows = session.scalars(
                select(OfferRecord)
                .where(OfferRecord.candidate_id == cid)
                .order_by(OfferRecord.created_at.desc())
            ).all()
            return JSONResponse({"offers": [offer_view(row) for row in rows]})

    async def create_candidate_offer(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = create_offer(
                session, cid,
                title=s_field(body, "title", required=True),
                compensation_note=s_field(body, "compensation_note"),
                target_start_date=s_field(body, "target_start_date"),
                terms=s_field(body, "terms"),
                actor=s_field(body, "actor", default="human"),
            )
            return JSONResponse(offer_view(row))

    async def offer_status(request: Request) -> JSONResponse:
        oid = request.path_params["offer_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = change_offer_status(
                session, oid,
                s_field(body, "status", required=True),
                actor=s_field(body, "actor", default="human"),
                reason=s_field(body, "reason"),
            )
            return JSONResponse(offer_view(row))

    return [
        Route("/api/v1/candidates/{candidate_id:str}/offers", candidate_offers, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/offers", create_candidate_offer, methods=["POST"]),
        Route("/api/v1/offers/{offer_id:str}/status", offer_status, methods=["POST"]),
    ]
