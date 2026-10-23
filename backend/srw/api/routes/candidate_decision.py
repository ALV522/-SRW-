"""Candidate decision surface routes (ADR-0002 R2, thirteenth slice).

Four routes that carry the product's central rule: a machine may propose, but a
human decides. The candidate workspace and assessment read the projection; the
verification route records a per-criterion judgement; the decision route records
the HumanDecision itself.

Behaviour is identical to the code that lived in ``create_v1_app``. What matters
and is easy to lose in a move:

* verification and decision both write through the decision commands and then
  return the *recomputed* workspace, so the client never sees a stale projection;
* the decision route takes decision and reason as required strings - an empty
  reason is rejected as 422 rather than recorded as "no reason";
* both carry ``evaluation_policy_revision`` into the command, so a policy change
  cannot be bypassed by calling the route directly.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from srw.api.request_fields import body_dict as _body, body_string as _string
from srw.api.serialization import jsonable as _json
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.decision.commands import make_human_decision, record_verification_note
from srw.runtime.db.session import v1_session_scope
from srw.surfaces.candidate_workspace import get_candidate_workspace


def candidate_decision_routes(*, factory, evaluation_policy_revision: str) -> list[Route]:
    """Bind the candidate decision endpoints to one Core session factory."""

    async def candidate_workspace(request: Request) -> Response:
        with factory() as session:
            value = get_candidate_workspace(
                session,
                request.path_params["candidate_id"],
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(value))

    async def candidate_assessment(request: Request) -> Response:
        with factory() as session:
            return JSONResponse(get_candidate_assessment(session,request.path_params["candidate_id"],evaluation_policy_revision=evaluation_policy_revision))

    async def verify(request: Request) -> Response:
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        with v1_session_scope(factory) as session:
            record_verification_note(
                session,
                candidate_id,
                _string(body, "criterion_key", required=True),
                note=_string(body, "note", required=True),
                status=_string(body, "status", required=True),
                evidence_level=_string(body, "evidence_level", required=True),
                reason=_string(body, "reason", required=True),
                gap=_string(body, "gap", default=""),
                actor=_string(body, "actor", default="human"),
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(get_candidate_workspace(session, candidate_id, evaluation_policy_revision=evaluation_policy_revision)))

    async def decide(request: Request) -> Response:
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        with v1_session_scope(factory) as session:
            make_human_decision(
                session,
                candidate_id,
                decision=_string(body, "decision", required=True),
                reason=_string(body, "reason", required=True),
                actor=_string(body, "actor", default="human"),
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(get_candidate_workspace(session, candidate_id, evaluation_policy_revision=evaluation_policy_revision)))

    return [
        Route("/api/v1/candidates/{candidate_id:str}/workspace", candidate_workspace, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/assessment", candidate_assessment, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/verifications", verify, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/decision", decide, methods=["POST"]),
    ]
