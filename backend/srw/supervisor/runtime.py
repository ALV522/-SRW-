"""Supervisor runtime: the detached process that owns the workspace (ADR-0003 S1).

Entry point (run as a module, detached from any carrier):

    python -m srw.supervisor --data-root <workspace> --port <loopback> \
        [--idle-grace-seconds 300] [--frontend-dist <dir>] [--knowledge-root <dir>]

The Supervisor acquires the workspace lease with edition="supervisor", serves
the v1 API plus the attach protocol on the given loopback port, records the
port in the lease metadata so carriers can find it, and exits by itself once
the attach refcount has been zero for the idle grace period. A stale
attachment (no heartbeat) is auto-detached, so a crashed carrier releases its
slot without any carrier-side cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.supervisor.service import (
    InvalidToken,
    SupervisorService,
    SupervisorShuttingDown,
    UnknownAttachment,
)

GRACE_TICK_SECONDS = 2.0
LEASE_READY_TIMEOUT_SECONDS = 30.0


async def attach_endpoint(request: Request) -> JSONResponse:
    service: SupervisorService = request.app.state.supervisor_service
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        attachment = service.attach(
            carrier=str(payload.get("carrier") or "unknown"),
            edition=str(payload.get("edition") or ""),
        )
    except SupervisorShuttingDown as exc:
        return JSONResponse({"error": {"code": "supervisor_shutting_down", "detail": str(exc)}}, status_code=409)
    session = attachment.session
    return JSONResponse(
        {
            "attach_id": attachment.attach_id,
            "token": attachment.token,
            "instance_id": service.instance_id,
            "idle_grace_seconds": service.idle_grace_seconds,
            "session_id": session.session_id,
            "session_token": session.session_token,
            "csrf_token": session.csrf_token,
        }
    )


async def heartbeat_endpoint(request: Request) -> JSONResponse:
    service: SupervisorService = request.app.state.supervisor_service
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        status = service.heartbeat(str(payload.get("attach_id") or ""), str(payload.get("token") or ""))
    except UnknownAttachment as exc:
        return JSONResponse({"error": {"code": "unknown_attachment", "detail": str(exc)}}, status_code=404)
    except InvalidToken as exc:
        return JSONResponse({"error": {"code": "invalid_token", "detail": str(exc)}}, status_code=403)
    return JSONResponse(status.public_view())


async def detach_endpoint(request: Request) -> JSONResponse:
    service: SupervisorService = request.app.state.supervisor_service
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        status = service.detach(str(payload.get("attach_id") or ""), str(payload.get("token") or ""))
    except UnknownAttachment as exc:
        return JSONResponse({"error": {"code": "unknown_attachment", "detail": str(exc)}}, status_code=404)
    except InvalidToken as exc:
        return JSONResponse({"error": {"code": "invalid_token", "detail": str(exc)}}, status_code=403)
    return JSONResponse(status.public_view())


async def status_endpoint(request: Request) -> JSONResponse:
    service: SupervisorService = request.app.state.supervisor_service
    body = service.status().public_view()
    body["attachment_list"] = service.attachment_views()
    return JSONResponse(body)


def supervisor_routes() -> list[Route]:
    return [
        Route("/api/v1/supervisor/attach", attach_endpoint, methods=["POST"]),
        Route("/api/v1/supervisor/heartbeat", heartbeat_endpoint, methods=["POST"]),
        Route("/api/v1/supervisor/detach", detach_endpoint, methods=["POST"]),
        Route("/api/v1/supervisor/status", status_endpoint, methods=["GET"]),
    ]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="srw.supervisor", description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="workspace root (holds data/)")
    parser.add_argument("--port", type=int, required=True, help="loopback port to serve on")
    parser.add_argument("--database", type=Path, default=None, help="SQLite file (default: <data-root>/data/srw_v1.db)")
    parser.add_argument("--frontend-dist", type=Path, default=None)
    parser.add_argument("--knowledge-root", type=Path, default=None)
    parser.add_argument("--idle-grace-seconds", type=float, default=300.0)
    parser.add_argument("--attach-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--enforce-sessions", action="store_true",
                        help="ADR-0003 S3: require a valid carrier session + CSRF token on mutations")
    return parser.parse_args(argv)


def _release_identity() -> tuple[str, str]:
    """Best-effort (version, release_id) from the repository root next to the backend."""
    repo_root = Path(__file__).resolve().parents[3]
    version = ""
    release_id = ""
    try:
        version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        version = "unknown"
    try:
        release_id = json.loads((repo_root / "BUILD_INFO.json").read_text(encoding="utf-8")).get("release_id", version)
    except (OSError, ValueError):
        release_id = version
    return version, str(release_id)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    data_root = args.data_root.resolve()
    data_dir = data_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    database = args.database or (data_dir / "srw_v1.db")

    import uvicorn

    from srw.api.app import create_v1_app
    from srw.workspace_lease import WorkspaceLease, WorkspaceLeaseError

    version, release_id = _release_identity()

    # Session RECORDS are persisted (tokens never are): the store shares the
    # workspace database file with the Core engine.
    from srw.kernel.clock import utc_now
    from srw.runtime.db.base import V1Base
    from srw.runtime.db.models_registry import import_v1_models
    from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
    from srw.supervisor.models import CarrierSession

    import_v1_models()
    store_engine = create_v1_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    V1Base.metadata.create_all(store_engine)
    store_factory = create_v1_session_factory(store_engine)

    def _persist_session(action: str, record: dict) -> None:
        try:
            with store_factory() as store:
                if action == "issue":
                    store.add(
                        CarrierSession(
                            session_id=record["session_id"],
                            attach_id=record["attach_id"],
                            supervisor_instance_id=record["supervisor_instance_id"],
                            edition=record["edition"],
                            carrier=record["carrier"],
                            created_at=utc_now(),
                            last_seen_at=utc_now(),
                        )
                    )
                else:
                    row = store.get(CarrierSession, record["session_id"])
                    if row is not None:
                        row.revoked_at = utc_now()
                        row.revoked_reason = record["revoked_reason"]
                        row.last_seen_at = utc_now()
                store.commit()
        except Exception as exc:  # persistence must never break the protocol
            print(json.dumps({"event": "supervisor_session_persist_failed", "detail": str(exc)}), flush=True)

    lease = WorkspaceLease(data_dir, edition="supervisor", port=args.port, version=version, release_id=release_id)
    try:
        lease.acquire()
    except WorkspaceLeaseError as exc:
        print(json.dumps({"event": "supervisor_lease_refused", "detail": str(exc)}), flush=True)
        return 3

    service = SupervisorService(
        idle_grace_seconds=args.idle_grace_seconds,
        attach_timeout_seconds=args.attach_timeout_seconds,
        session_persist=_persist_session,
    )
    app = create_v1_app(
        f"sqlite+pysqlite:///{database.as_posix()}",
        frontend_dist=args.frontend_dist,
        data_dir=data_dir,
        knowledge_dir=args.knowledge_root,
        supervisor_service=service,
        enforce_carrier_sessions=args.enforce_sessions,
    )

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    stop = threading.Event()

    def _grace_loop() -> None:
        while not stop.wait(GRACE_TICK_SECONDS):
            service.expire_stale()
            if service.idle_exit_due():
                service.begin_shutdown()
                print(json.dumps({"event": "supervisor_idle_exit", "attachments": 0}), flush=True)
                server.should_exit = True
                return

    watcher = threading.Thread(target=_grace_loop, name="srw-supervisor-grace", daemon=True)
    watcher.start()

    print(
        json.dumps(
            {
                "event": "supervisor_started",
                "instance_id": service.instance_id,
                "port": args.port,
                "edition": "supervisor",
                "idle_grace_seconds": service.idle_grace_seconds,
            }
        ),
        flush=True,
    )
    try:
        server.run()
    finally:
        stop.set()
        lease.release()
        store_engine.dispose()
        print(json.dumps({"event": "supervisor_stopped", "instance_id": service.instance_id}), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    sys.exit(main())
