"""Task and role-template routes extracted from the fullworkbench aggregate.

These are the operational surfaces an operator uses to watch background work and
to reuse a recruiting protocol across projects. Behaviour is intentionally
identical to the code that lived inside ``install_full_workbench_routes``.

Scope note: the ``GET /api/v1/dashboard`` handler is **not** moved here. It is a
284-line read model that aggregates projects, candidates, claims, offers,
interviews and contacts; it belongs with the read-projection work rather than a
transport module. It stays in the aggregate until that slice happens, and the
API inventory keeps recording its real owner.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.api.shared import latest_draft
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.fullworkbench import RoleTemplate, TaskRecord
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.session import v1_session_scope
from srw.runtime.jobs.engine import JobEngine


def task_json(task: TaskRecord) -> dict[str, Any]:
    try:
        result = json.loads(task.result_json or "{}")
    except Exception:
        result = {}
    return {
        "task_id": task.id, "type": task.task_type, "status": task.status,
        "candidate_id": task.candidate_id, "source_id": task.source_id,
        "result_source_id": task.result_source_id,
        "progress_current": task.progress_current, "progress_total": task.progress_total,
        "attempt_count": task.attempt_count,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "duration_ms": task.duration_ms,
        "error_code": task.error_code, "error_message": task.error_message,
        "result": result,
        "created_at": task.created_at.isoformat(),
    }


def operation_routes(*, factory) -> list[Route]:
    """Bind the task and template endpoints to one Core session factory."""

    async def tasks(request: Request) -> JSONResponse:
        status = (request.query_params.get("status") or "").strip()
        task_type = (request.query_params.get("type") or "").strip()
        candidate_id = (request.query_params.get("candidate_id") or "").strip()
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        filters = []
        if status:
            filters.append(TaskRecord.status == status)
        if task_type:
            filters.append(TaskRecord.task_type == task_type)
        if candidate_id:
            filters.append(TaskRecord.candidate_id == candidate_id)
        with factory() as session:
            total = session.scalar(select(func.count(TaskRecord.id)).where(*filters)) or 0
            rows = session.scalars(
                select(TaskRecord).where(*filters).order_by(TaskRecord.created_at.desc()).limit(limit).offset(offset)
            ).all()
            return JSONResponse({"tasks": [task_json(x) for x in rows], "total": total,
                                 "limit": limit, "offset": offset})

    async def task_detail(request: Request) -> JSONResponse:
        tid = request.path_params["task_id"]
        with factory() as session:
            row = session.get(TaskRecord, tid)
            if not row:
                raise V1NotFoundError(f"task not found: {tid}")
            return JSONResponse(task_json(row))

    async def cancel_task(request: Request) -> JSONResponse:
        tid = request.path_params["task_id"]
        with v1_session_scope(factory) as session:
            row = session.get(TaskRecord, tid)
            if not row:
                raise V1NotFoundError(f"task not found: {tid}")
            if row.status == "succeeded":
                return JSONResponse({"task_id": tid, "status": row.status})
            row.cancel_requested = True
            row.status = "cancelled"
            if row.job_id:
                JobEngine(session).cancel(row.job_id)
            return JSONResponse({"task_id": tid, "status": row.status})

    async def retry_task(request: Request) -> JSONResponse:
        tid = request.path_params["task_id"]
        with v1_session_scope(factory) as session:
            row = session.get(TaskRecord, tid)
            if not row:
                raise V1NotFoundError(f"task not found: {tid}")
            if row.status == "cancelled":
                raise V1InvariantError("cancelled task cannot be retried")
            if not row.job_id:
                job = JobEngine(session).enqueue(
                    f"task.{row.task_type}", {"task_id": row.id},
                    idempotency_key=f"task:{row.id}:retry:{row.attempt_count + 1}",
                )
                row.job_id = job.id
            else:
                JobEngine(session).requeue(row.job_id)
            row.cancel_requested = False
            row.status = "queued"
            row.error_code = ""
            row.error_message = ""
            row.finished_at = None
            return JSONResponse({"task_id": tid, "job_id": row.job_id, "status": "queued"})

    async def templates(_r: Request) -> JSONResponse:
        with factory() as session:
            rows = session.scalars(select(RoleTemplate).order_by(RoleTemplate.updated_at.desc())).all()
            return JSONResponse({"templates": [
                {"template_id": x.id, "name": x.name, "role_title": x.role_title,
                 "payload": json.loads(x.payload_json), "updated_at": x.updated_at.isoformat()}
                for x in rows
            ]})

    async def template_create(request: Request) -> JSONResponse:
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = RoleTemplate(
                name=s_field(body, "name", required=True),
                role_title=s_field(body, "role_title"),
                payload_json=json.dumps(body.get("payload") if isinstance(body.get("payload"), dict) else {},
                                        ensure_ascii=False),
            )
            session.add(row)
            session.flush()
            return JSONResponse({"template_id": row.id, "name": row.name})

    async def template_update(request: Request) -> JSONResponse:
        tid = request.path_params["template_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = session.get(RoleTemplate, tid)
            if not row:
                raise V1NotFoundError(f"template not found: {tid}")
            if "name" in body:
                row.name = s_field(body, "name", required=True)
            if "role_title" in body:
                row.role_title = s_field(body, "role_title")
            if "payload" in body:
                if not isinstance(body["payload"], dict):
                    raise V1InvariantError("payload must be an object")
                row.payload_json = json.dumps(body["payload"], ensure_ascii=False)
            return JSONResponse({"template_id": row.id, "name": row.name})

    async def template_delete(request: Request) -> JSONResponse:
        tid = request.path_params["template_id"]
        with v1_session_scope(factory) as session:
            row = session.get(RoleTemplate, tid)
            if not row:
                raise V1NotFoundError(f"template not found: {tid}")
            session.delete(row)
            return JSONResponse({"deleted": True})

    async def template_from_current(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            project = session.get(Project, pid)
            if not project:
                raise V1NotFoundError(f"project not found: {pid}")
            revision = latest_draft(session, pid)
            if revision is None and project.current_protocol_revision_id:
                revision = session.get(ProtocolRevision, project.current_protocol_revision_id)
            if not revision:
                raise V1InvariantError("project has no protocol to save as template")
            payload = ProtocolRepository(session).get_payload(revision.id)
            role = str((payload.get("brief") or {}).get("title") or "")
            row = RoleTemplate(name=s_field(body, "name", required=True), role_title=role,
                               payload_json=json.dumps(payload, ensure_ascii=False))
            session.add(row)
            session.flush()
            return JSONResponse({"template_id": row.id, "name": row.name, "source_revision_id": revision.id})

    async def template_apply(request: Request) -> JSONResponse:
        tid = request.path_params["template_id"]
        pid = request.path_params["project_id"]
        body = await json_body(request)
        mode = s_field(body, "mode", default="merge")
        if mode not in {"merge", "replace"}:
            raise V1InvariantError("mode must be merge or replace")
        with v1_session_scope(factory) as session:
            template = session.get(RoleTemplate, tid)
            project = session.get(Project, pid)
            if not template:
                raise V1NotFoundError(f"template not found: {tid}")
            if not project:
                raise V1NotFoundError(f"project not found: {pid}")
            draft = latest_draft(session, pid)
            if not draft:
                draft = ProtocolRepository(session).fork_current_to_draft(pid)
            current = ProtocolRepository(session).get_payload(draft.id)
            incoming = json.loads(template.payload_json or "{}")
            if mode == "replace":
                merged = incoming
            else:
                merged = dict(current)
                existing = list(current.get("criteria") or [])
                names = {str(x.get("name") or "").strip().lower() for x in existing if isinstance(x, dict)}
                for item in incoming.get("criteria") or []:
                    if isinstance(item, dict) and str(item.get("name") or "").strip().lower() not in names:
                        existing.append(dict(item))
                merged["criteria"] = existing
            row = ProtocolRepository(session).update_draft(
                draft.id, merged, {"origin": "template_apply", "template_id": tid, "mode": mode})
            return JSONResponse({"revision_id": row.id, "state": row.state, "mode": mode,
                                 "criteria_count": len(ProtocolRepository(session).get_payload(row.id).get("criteria") or [])})

    return [
        Route("/api/v1/tasks", tasks, methods=["GET"]),
        Route("/api/v1/tasks/{task_id:str}", task_detail, methods=["GET"]),
        Route("/api/v1/tasks/{task_id:str}/retry", retry_task, methods=["POST"]),
        Route("/api/v1/tasks/{task_id:str}/cancel", cancel_task, methods=["POST"]),
        Route("/api/v1/templates", templates, methods=["GET"]),
        Route("/api/v1/templates", template_create, methods=["POST"]),
        Route("/api/v1/templates/{template_id:str}", template_delete, methods=["DELETE"]),
        Route("/api/v1/templates/{template_id:str}", template_update, methods=["PATCH"]),
        Route("/api/v1/projects/{project_id:str}/templates/from-current", template_from_current, methods=["POST"]),
        Route("/api/v1/templates/{template_id:str}/apply/{project_id:str}", template_apply, methods=["POST"]),
    ]
