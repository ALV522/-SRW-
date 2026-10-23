from __future__ import annotations

from urllib.parse import urlsplit

from starlette.responses import JSONResponse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _split_host_port(value: str) -> tuple[str, str | None]:
    value = (value or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return value, None
        host = value[1:end]
        port = value[end + 1 :]
        return host.rstrip("."), port[1:] if port.startswith(":") else None
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return host.rstrip("."), port
    return value.rstrip("."), None


def is_local_host_header(value: str) -> bool:
    host, _ = _split_host_port(value)
    return host in _LOCAL_HOSTS


def _normalized_netloc(value: str) -> tuple[str, str | None] | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    host = parsed.hostname.rstrip(".").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80 if parsed.scheme.lower() == "http" else None
    return host, str(port) if port is not None else None


def _same_origin(host_header: str, origin: str) -> bool:
    host, host_port = _split_host_port(host_header)
    origin_parts = _normalized_netloc(origin)
    if origin_parts is None:
        return False
    origin_host, origin_port = origin_parts
    if origin_host != host:
        return False
    # A host header without an explicit port is compatible with the origin's
    # default port.  An explicit host port must match exactly.
    if host_port is None:
        return origin_port in {"80", "443"}
    return host_port == origin_port


class LocalBoundaryMiddleware:
    """Keep the local-first workbench inaccessible from LAN / cross-site origins.

    Native Host/API clients may omit Origin entirely.  Browser mutations that do
    send Origin or Referer must be same-origin with the local Host header.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        host = headers.get("host", "")
        if not is_local_host_header(host):
            response = JSONResponse({"detail": "仅允许通过本机地址访问工作台"}, status_code=400)
            await response(scope, receive, send)
            return

        method = str(scope.get("method") or "GET").upper()
        if method in _MUTATING_METHODS:
            # ADR-0003 T8: a running backup/restore refuses other-carrier writes.
            # The Starlette instance is on the scope, not on the wrapped app.
            starlette_app = scope.get("app")
            guard = getattr(getattr(starlette_app, "state", None), "backup_guard", None)
            if guard is not None and guard.active:
                response = JSONResponse(
                    {"detail": "备份或恢复进行中，暂不接受写入", "error": {"code": "backup_in_progress"}},
                    status_code=409,
                )
                await response(scope, receive, send)
                return
            origin = headers.get("origin")
            if origin and not _same_origin(host, origin):
                response = JSONResponse({"detail": "拒绝跨站写入请求"}, status_code=403)
                await response(scope, receive, send)
                return
            referer = headers.get("referer")
            if not origin and referer and not _same_origin(host, referer):
                response = JSONResponse({"detail": "拒绝跨站写入请求"}, status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
