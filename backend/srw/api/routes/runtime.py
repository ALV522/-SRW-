"""Runtime identity and lifecycle routes (ADR-0002 R2, eleventh slice).

Five routes that describe the running Core and let a supervised host shut it down
safely: live, ready, info, capabilities and shutdown.

Why a context object rather than ten parameters: these handlers need the release
identity, instance/session identifiers, runtime mode, the knowledge directory and
the session token. Passing them individually would make a signature nobody can
call correctly, so they travel as :class:`RuntimeIdentity` assembled once in
``create_v1_app``.

Behaviour is identical to the code that lived there. Two contracts worth naming:

* ``/runtime/ready`` reports 503 with a machine-readable ``issues`` list when the
  database or the five knowledge databases are missing - readiness is evidence,
  not a constant;
* ``/runtime/shutdown`` requires the lifecycle session token when the host issued
  one (403 otherwise) and returns 409 when no shutdown callback is registered, so
  a browser tab can never stop an unsupervised server.

Health probes (``/health/*``) and the ``/api/v1/info`` alias stay in ``app.py``:
they are the app shell's own liveness surface and must not depend on this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from srw.runtime.db.schema import V1_SCHEMA_REVISION


@dataclass(frozen=True)
class RuntimeIdentity:
    """Everything the runtime routes need to describe this process."""

    release: dict
    instance_id: str
    release_id: str
    runtime_session_id: str
    runtime_mode: str
    edition: str
    runtime_session_token: str
    data_dir_identity: str
    knowledge_dir: object


def runtime_routes(*, factory, identity: RuntimeIdentity) -> list[Route]:
    """Bind the runtime endpoints to one Core session factory and identity."""

    release = identity.release
    instance_id = identity.instance_id
    release_id = identity.release_id
    runtime_session_id = identity.runtime_session_id
    runtime_mode = identity.runtime_mode
    edition = identity.edition
    runtime_session_token = identity.runtime_session_token
    data_dir_identity = identity.data_dir_identity
    resolved_knowledge_dir = identity.knowledge_dir

    async def runtime_live(_request: Request) -> Response:
        return JSONResponse({
            "status": "live", "product": "SRW", "version": release["version"],
            "instanceId": instance_id, "releaseId": release_id, "sessionId": runtime_session_id,
        })

    async def runtime_ready(_request: Request) -> Response:
        issues: list[str] = []
        try:
            with factory() as session:
                session.connection()
        except Exception as exc:
            issues.append(f"database_not_ready:{type(exc).__name__}")
        knowledge_ready = all((resolved_knowledge_dir / name / "knowledge.db").is_file() for name in ("taxonomy","job_info","competency","market_reference","reference"))
        if not knowledge_ready:
            issues.append("knowledge_not_ready")
        ready = not issues
        return JSONResponse({
            "status": "ready" if ready else "not_ready",
            "version": release["version"],
            "schemaVersion": V1_SCHEMA_REVISION,
            "databaseReady": not any(x.startswith("database_not_ready") for x in issues),
            "knowledgeReady": knowledge_ready,
            "issues": issues,
        }, status_code=200 if ready else 503)

    async def runtime_info(_request: Request) -> Response:
        return JSONResponse({
            "apiVersion": "v1", "product": "SRW", "version": release["version"],
            "schemaVersion": V1_SCHEMA_REVISION, "runtime": runtime_mode, "edition": edition,
            "instanceId": instance_id, "releaseId": release_id, "sessionId": runtime_session_id,
            "dataScopeId": data_dir_identity,
            "frontend": {"mode": "static_dist"},
            "capabilities": {
                "desktop": runtime_mode == "desktop", "nativeFileDialogs": False,
                "secureSecretStore": False, "notifications": False, "clipboard": True,
                "downloads": True, "externalNavigation": True,
                "gracefulShutdown": True, "lifecycleSessionTokenSupported": True,
                "lifecycleSessionTokenRequired": bool(runtime_session_token),
            },
            "readiness": {"status": "ready"},
        })

    async def runtime_capabilities(_request: Request) -> Response:
        info = await runtime_info(_request)
        # Avoid reparsing Response internals: keep a concise capability contract.
        return JSONResponse({
            "runtime": runtime_mode, "edition": edition, "desktop": runtime_mode == "desktop",
            "nativeFileDialogs": False, "secureSecretStore": False, "notifications": False,
            "clipboard": True, "downloads": True, "externalNavigation": True,
            "gracefulShutdown": True, "lifecycleSessionTokenSupported": True,
            "lifecycleSessionTokenRequired": bool(runtime_session_token),
        })

    async def runtime_shutdown(request: Request) -> Response:
        if runtime_session_token and request.headers.get("X-SRW-Session", "") != runtime_session_token:
            return JSONResponse({"detail": "运行时会话令牌无效"}, status_code=403)
        callback = getattr(request.app.state, "shutdown_callback", None)
        if callback is None:
            return JSONResponse({"detail": "当前启动方式不支持 Host 安全退出"}, status_code=409)
        return JSONResponse({"status": "shutting_down"}, status_code=202, background=BackgroundTask(callback))

    return [
        Route("/api/v1/runtime/live", runtime_live, methods=["GET"]),
        Route("/api/v1/runtime/ready", runtime_ready, methods=["GET"]),
        Route("/api/v1/runtime/info", runtime_info, methods=["GET"]),
        Route("/api/v1/runtime/capabilities", runtime_capabilities, methods=["GET"]),
        Route("/api/v1/runtime/shutdown", runtime_shutdown, methods=["POST"]),
    ]
