"""Project and protocol authoring routes (ADR-0002 R2, twelfth slice).

Six routes that create a project and drive its protocol from draft to published:
list projects, create a project with an initial draft, fork a draft from the
current revision, read the protocol workspace, edit a draft and publish it.

The Domain owns publish eligibility: ``ProtocolRepository.publish`` re-reads
the persisted draft and requires a named criterion linked to an assessment stage
before any published revision or project pointer changes. The route remains a
thin transport adapter. ``_object`` rejects a non-object PATCH payload with 422;
a draft that cannot be published is rejected by the Domain with 409.

Scope note: the protocol workspace read model stays here because it is the same
authoring surface the editor reads from; separating it from the writes would make
the draft/publish contract harder to follow, not easier.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from srw.api.request_fields import body_dict as _body, body_object as _object, body_string as _string
from srw.api.serialization import jsonable as _json
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.session import v1_session_scope
from srw.surfaces.protocol_workspace import get_protocol_workspace
from srw.surfaces.projects import create_project_with_draft, get_projects_surface


def project_authoring_routes(*, factory) -> list[Route]:
    """Bind the project/protocol authoring endpoints to one Core session factory."""

    async def projects(_request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_projects_surface(session)))
    async def create_project(request: Request) -> Response:
        body = await _body(request)
        with v1_session_scope(factory) as session:
            result = create_project_with_draft(
                session,
                title=_string(body, "title", required=True),
                role_title=_string(body, "role_title", required=True),
                brief_summary=_string(body, "brief_summary", default=""),
            )
            return JSONResponse(_json(result))
    async def fork_protocol_draft(request: Request) -> Response:
        project_id = request.path_params["project_id"]
        with v1_session_scope(factory) as session:
            row = ProtocolRepository(session).fork_current_to_draft(project_id)
            return JSONResponse({"revision_id": row.id, "revision": row.revision, "state": row.state})
    async def protocol_workspace(request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_protocol_workspace(session, request.path_params["project_id"])))
    async def update_protocol(request: Request) -> Response:
        body = await _body(request)
        with v1_session_scope(factory) as session:
            row = ProtocolRepository(session).update_draft(
                request.path_params["revision_id"],
                _object(body, "payload"),
                _object(body, "provenance", default={}),
            )
            return JSONResponse({"revision_id": row.id, "revision": row.revision, "state": row.state})
    async def publish_protocol(request: Request) -> Response:
        with v1_session_scope(factory) as session:
            row = ProtocolRepository(session).publish(request.path_params["revision_id"])
            return JSONResponse({"revision_id": row.id, "revision": row.revision, "state": row.state})

    return [
        Route("/api/v1/projects", projects, methods=["GET"]),
        Route("/api/v1/projects", create_project, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/protocol-drafts", fork_protocol_draft, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/protocol-workspace", protocol_workspace, methods=["GET"]),
        Route("/api/v1/protocol-revisions/{revision_id:str}", update_protocol, methods=["PATCH"]),
        Route("/api/v1/protocol-revisions/{revision_id:str}/publish", publish_protocol, methods=["POST"]),
    ]
