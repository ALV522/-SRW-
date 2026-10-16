from __future__ import annotations

from typing import Any
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError
from srw.modules.decision.shortlist import (
    build_ranked_shortlist,
    publish_ranked_shortlist,
    list_shortlist_publications,
    get_shortlist_publication,
)
from srw.runtime.db.session import v1_session_scope


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:
        raise V1InvariantError("request body must be valid JSON") from exc
    if not isinstance(value, dict):
        raise V1InvariantError("request body must be an object")
    return value


def install_ranking_routes(app, factory, *, evaluation_policy_revision: str) -> None:
    async def shortlist(request: Request):
        project_id = request.path_params["project_id"]
        if request.method == "GET":
            with factory() as session:
                return JSONResponse(build_ranked_shortlist(session, project_id, evaluation_policy_revision=evaluation_policy_revision))
        body = await _body(request)
        actor = str(body.get("actor") or "human").strip()
        with v1_session_scope(factory) as session:
            return JSONResponse(publish_ranked_shortlist(session, project_id, evaluation_policy_revision=evaluation_policy_revision, actor=actor))

    async def history(request: Request):
        project_id = request.path_params["project_id"]
        try:
            limit = min(100, max(1, int(request.query_params.get("limit", "20"))))
        except ValueError as exc:
            raise V1InvariantError("limit must be an integer") from exc
        with factory() as session:
            return JSONResponse({"project_id": project_id, "publications": list_shortlist_publications(session, project_id, limit=limit)})

    async def publication(request: Request):
        with factory() as session:
            return JSONResponse(get_shortlist_publication(session, request.path_params["publication_id"]))

    app.routes.extend([
        Route('/api/v1/projects/{project_id:str}/ranked-shortlist', shortlist, methods=['GET', 'POST']),
        Route('/api/v1/projects/{project_id:str}/ranked-shortlists', history, methods=['GET']),
        Route('/api/v1/ranked-shortlists/{publication_id:str}', publication, methods=['GET']),
    ])
