from __future__ import annotations

from typing import Any

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.candidate.models import Candidate
from srw.modules.recruiting.models import OfferRecord
from srw.recruiting.operations import change_offer_status, create_offer, offer_view
from srw.runtime.db.session import v1_session_scope


def _body_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V1InvariantError("request body must be an object")
    return value


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        return _body_dict(await request.json())
    except V1InvariantError:
        raise
    except Exception as exc:
        raise V1InvariantError("request body must be valid JSON") from exc


def _s(body: dict[str, Any], key: str, default: str = "", required: bool = False) -> str:
    value = body.get(key, default)
    if not isinstance(value, str):
        raise V1InvariantError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise V1InvariantError(f"{key} is required")
    return value


def install_offer_routes(app, factory) -> None:
    """Install the existing Offer HTTP contract without owning Offer business rules.

    The state machine, audit events and candidate-stage guard remain authoritative
    in ``srw.recruiting.operations``.  This module is deliberately only the HTTP
    adapter for the three frozen Offer routes.
    """

    async def candidate_offers(request: Request):
        candidate_id = request.path_params["candidate_id"]
        with factory() as session:
            if session.get(Candidate, candidate_id) is None:
                raise V1NotFoundError(f"candidate not found: {candidate_id}")
            rows = session.scalars(
                select(OfferRecord)
                .where(OfferRecord.candidate_id == candidate_id)
                .order_by(OfferRecord.created_at.desc())
            ).all()
            return JSONResponse({"offers": [offer_view(row) for row in rows]})

    async def create_candidate_offer(request: Request):
        candidate_id = request.path_params["candidate_id"]
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            row = create_offer(
                session,
                candidate_id,
                title=_s(body, "title", required=True),
                compensation_note=_s(body, "compensation_note"),
                target_start_date=_s(body, "target_start_date"),
                terms=_s(body, "terms"),
                actor=_s(body, "actor", default="human"),
            )
            return JSONResponse(offer_view(row))

    async def offer_status(request: Request):
        offer_id = request.path_params["offer_id"]
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            row = change_offer_status(
                session,
                offer_id,
                _s(body, "status", required=True),
                actor=_s(body, "actor", default="human"),
                reason=_s(body, "reason"),
            )
            return JSONResponse(offer_view(row))

    app.routes.extend([
        Route('/api/v1/candidates/{candidate_id:str}/offers', candidate_offers, methods=['GET']),
        Route('/api/v1/candidates/{candidate_id:str}/offers', create_candidate_offer, methods=['POST']),
        Route('/api/v1/offers/{offer_id:str}/status', offer_status, methods=['POST']),
    ])
