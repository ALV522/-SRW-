"""Carrier session enforcement for the Supervisor (ADR-0003 S3).

Installed only when this process is the Supervisor AND session enforcement is
enabled (phase-2 flag, default off until the frontend carries the headers).

Two rules:
1. Origin/Referer allowlist - only loopback origins may talk to the Core;
2. every mutating /api/v1 request must carry a valid one-time carrier session
   (X-SRW-Session + X-SRW-Token) and the matching CSRF token (X-SRW-CSRF).

The attach endpoint itself is exempt (it is how a session is obtained), as are
the health probes. A refused request never reaches a domain handler, so it can
neither write state nor produce audit.
"""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# The attach protocol authenticates with its own per-attach bearer token, so it
# is exempt from the session/CSRF rule (the loopback origin rule still applies).
EXEMPT_PATH_SUFFIXES = (
    "/health/live",
    "/health/ready",
    "/api/v1/supervisor/attach",
    "/api/v1/supervisor/heartbeat",
    "/api/v1/supervisor/detach",
)


def _origin_host(value: str) -> str:
    text = (value or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if text.startswith("["):
        return text.split("]", 1)[0] + "]"
    return text.rsplit(":", 1)[0] if ":" in text else text


def _is_loopback(value: str) -> bool:
    host = _origin_host(value).lower()
    return host in LOOPBACK_HOSTS


def _headers(scope: Scope) -> dict[str, str]:
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers") or []}


def _json(payload: dict, status: int):
    return JSONResponse(payload, status_code=status)


class CarrierSessionMiddleware:
    """Pure ASGI middleware; no framework coupling beyond Starlette responses."""

    def __init__(self, app: ASGIApp, service) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        path = scope.get("path") or ""
        method = (scope.get("method") or "GET").upper()

        origin = headers.get("origin") or headers.get("referer") or ""
        if origin and not _is_loopback(origin):
            await _json({"error": {"code": "origin_not_allowed", "detail": "loopback origins only"}}, 403)(scope, receive, send)
            return

        if method in SAFE_METHODS or not path.startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        if any(path == suffix or path.endswith(suffix) for suffix in EXEMPT_PATH_SUFFIXES):
            await self.app(scope, receive, send)
            return

        session = self.service.sessions.validate(
            headers.get("x-srw-session", ""), headers.get("x-srw-token", "")
        )
        if session is None:
            await _json({"error": {"code": "carrier_session_required", "detail": "attach first"}}, 401)(scope, receive, send)
            return
        if not self.service.sessions.csrf_ok(session, headers.get("x-srw-csrf", "")):
            await _json({"error": {"code": "csrf_token_mismatch", "detail": "X-SRW-CSRF does not match the session"}}, 403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
