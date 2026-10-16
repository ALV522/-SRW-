from __future__ import annotations

from typing import Any
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError
from srw.modules.identity.service import (
    scan_project_identity,
    list_identity_reviews,
    resolve_identity_review,
    identity_merge_preview,
    commit_identity_merge,
    merged_identity_history,
)
from srw.modules.calibration.service import (
    create_anchor,
    list_anchors,
    promote_anchor,
    create_review,
    list_reviews,
    resolve_review,
)
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


def install_governance_routes(app, factory) -> None:
    async def identity_reviews(request: Request):
        project_id = request.path_params["project_id"]
        status = request.query_params.get("status") or None
        with factory() as session:
            return JSONResponse({"project_id": project_id, "reviews": list_identity_reviews(session, project_id, status=status)})

    async def identity_scan(request: Request):
        project_id = request.path_params["project_id"]
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(scan_project_identity(session, project_id, actor=_s(body, "actor", default="human")))

    async def identity_resolve(request: Request):
        review_id = request.path_params["review_id"]
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(resolve_identity_review(
                session,
                review_id,
                status=_s(body, "status", required=True),
                actor=_s(body, "actor", default="human"),
                note=_s(body, "note"),
            ))

    async def merge_preview(request: Request):
        review_id = request.path_params["review_id"]
        target_id = (request.query_params.get("target_candidate_id") or "").strip()
        if not target_id:
            raise V1InvariantError("target_candidate_id is required")
        with factory() as session:
            return JSONResponse(identity_merge_preview(session, review_id, target_candidate_id=target_id))

    async def merge_commit(request: Request):
        review_id = request.path_params["review_id"]
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(commit_identity_merge(
                session,
                review_id,
                target_candidate_id=_s(body, "target_candidate_id", required=True),
                actor=_s(body, "actor", default="human"),
                note=_s(body, "note"),
            ))

    async def identity_history(request: Request):
        with factory() as session:
            rows = merged_identity_history(session, request.path_params["candidate_id"])
            return JSONResponse({"candidate_id": request.path_params["candidate_id"], "merged_sources": rows})

    async def calibration_anchors(request: Request):
        project_id = request.path_params["project_id"]
        if request.method == "GET":
            with factory() as session:
                return JSONResponse({"project_id": project_id, "anchors": list_anchors(session, project_id, lifecycle=request.query_params.get("lifecycle") or None)})
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(create_anchor(
                session,
                project_id,
                criterion_key=_s(body, "criterion_key", required=True),
                case_text=_s(body, "case_text", required=True),
                expected_judgment=_s(body, "expected_judgment", required=True),
                expected_evidence_level=_s(body, "expected_evidence_level", required=True),
                actor=_s(body, "actor", default="human"),
                source_case_id=_s(body, "source_case_id"),
            ))

    async def calibration_promote(request: Request):
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(promote_anchor(
                session,
                request.path_params["anchor_id"],
                target=_s(body, "target", required=True),
                actor=_s(body, "actor", default="human"),
            ))

    async def calibration_reviews(request: Request):
        project_id = request.path_params["project_id"]
        if request.method == "GET":
            with factory() as session:
                return JSONResponse({"project_id": project_id, "reviews": list_reviews(session, project_id, state=request.query_params.get("state") or None)})
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(create_review(
                session,
                project_id,
                trigger=_s(body, "trigger", required=True),
                criterion_key=_s(body, "criterion_key", required=True),
                before=_s(body, "before"),
                after=_s(body, "after"),
                reason=_s(body, "reason", required=True),
                actor=_s(body, "actor", default="human"),
                candidate_id=_s(body, "candidate_id") or None,
            ))

    async def calibration_resolve(request: Request):
        body = await _json_body(request)
        with v1_session_scope(factory) as session:
            return JSONResponse(resolve_review(
                session,
                request.path_params["review_id"],
                actor=_s(body, "actor", default="human"),
                note=_s(body, "note", required=True),
            ))

    app.routes.extend([
        Route('/api/v1/projects/{project_id:str}/identity-reviews', identity_reviews, methods=['GET']),
        Route('/api/v1/projects/{project_id:str}/identity-reviews/scan', identity_scan, methods=['POST']),
        Route('/api/v1/identity-reviews/{review_id:str}/resolve', identity_resolve, methods=['POST']),
        Route('/api/v1/identity-reviews/{review_id:str}/merge-preview', merge_preview, methods=['GET']),
        Route('/api/v1/identity-reviews/{review_id:str}/merge', merge_commit, methods=['POST']),
        Route('/api/v1/candidates/{candidate_id:str}/identity-history', identity_history, methods=['GET']),
        Route('/api/v1/projects/{project_id:str}/calibration/anchors', calibration_anchors, methods=['GET', 'POST']),
        Route('/api/v1/calibration/anchors/{anchor_id:str}/promote', calibration_promote, methods=['POST']),
        Route('/api/v1/projects/{project_id:str}/calibration/reviews', calibration_reviews, methods=['GET', 'POST']),
        Route('/api/v1/calibration/reviews/{review_id:str}/resolve', calibration_resolve, methods=['POST']),
    ])
