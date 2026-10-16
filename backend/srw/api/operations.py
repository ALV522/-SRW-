from __future__ import annotations

from dataclasses import asdict
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.ai_runs.models import AiRun
from srw.modules.ai_runs.service import list_ai_runs
from srw.modules.decision.lineage import get_decision_history, reaffirm_latest_decision
from srw.runtime.db.session import v1_session_scope


def _run_view(row: AiRun) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "task_type": row.task_type,
        "project_id": row.project_id,
        "candidate_id": row.candidate_id,
        "source_id": row.source_id,
        "provider_kind": row.provider_kind,
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "schema_version": row.schema_version,
        "input_hash": row.input_hash,
        "output_hash": row.output_hash,
        "input_safety_meta_json": row.input_safety_meta_json,
        "status": row.status,
        "error_class": row.error_class,
        "error_code": row.error_code,
        "retry_count": row.retry_count,
        "latency_ms": row.latency_ms,
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "raw_input_stored": False,
        "raw_output_stored": False,
        "api_key_stored": False,
    }


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:
        raise V1InvariantError("request body must be valid JSON") from exc
    if not isinstance(value, dict):
        raise V1InvariantError("request body must be an object")
    return value


def install_operations_routes(app, factory, *, evaluation_policy_revision: str) -> None:
    async def project_ai_runs(request: Request):
        try:
            limit = min(500, max(1, int(request.query_params.get("limit", "100"))))
        except ValueError as exc:
            raise V1InvariantError("limit must be an integer") from exc
        status = (request.query_params.get("status") or "").strip()
        with factory() as session:
            rows = list_ai_runs(
                session,
                project_id=request.path_params["project_id"],
                status=status,
                limit=limit,
            )
            return JSONResponse({"runs": [_run_view(row) for row in rows]})

    async def candidate_ai_runs(request: Request):
        try:
            limit = min(500, max(1, int(request.query_params.get("limit", "100"))))
        except ValueError as exc:
            raise V1InvariantError("limit must be an integer") from exc
        with factory() as session:
            rows = list_ai_runs(session, candidate_id=request.path_params["candidate_id"], limit=limit)
            return JSONResponse({"runs": [_run_view(row) for row in rows]})

    async def ai_run_detail(request: Request):
        with factory() as session:
            row = session.get(AiRun, request.path_params["run_id"])
            if row is None:
                raise V1NotFoundError("AI run not found")
            return JSONResponse(_run_view(row))

    async def decision_history(request: Request):
        with factory() as session:
            rows = get_decision_history(
                session,
                request.path_params["candidate_id"],
                evaluation_policy_revision=evaluation_policy_revision,
                limit=100,
            )
            return JSONResponse({"candidate_id": request.path_params["candidate_id"], "decisions": [asdict(row) for row in rows]})

    async def reaffirm_decision(request: Request):
        body = await _body(request)
        actor = str(body.get("actor") or "human").strip() or "human"
        reason = str(body.get("reason") or "").strip()
        with v1_session_scope(factory) as session:
            row = reaffirm_latest_decision(
                session,
                request.path_params["candidate_id"],
                actor=actor,
                reason=reason,
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse({
                "decision_id": row.id,
                "decision": row.decision,
                "reason": row.reason,
                "decision_context_hash": row.decision_context_hash,
                "reaffirmed_from_decision_id": row.reaffirmed_from_decision_id,
                "actor": row.actor,
                "created_at": row.created_at.isoformat(),
            })

    app.routes.extend([
        Route('/api/v1/projects/{project_id:str}/ai-runs', project_ai_runs, methods=['GET']),
        Route('/api/v1/candidates/{candidate_id:str}/ai-runs', candidate_ai_runs, methods=['GET']),
        Route('/api/v1/ai-runs/{run_id:str}', ai_run_detail, methods=['GET']),
        Route('/api/v1/candidates/{candidate_id:str}/decision-history', decision_history, methods=['GET']),
        Route('/api/v1/candidates/{candidate_id:str}/decisions/reaffirm', reaffirm_decision, methods=['POST']),
    ])
