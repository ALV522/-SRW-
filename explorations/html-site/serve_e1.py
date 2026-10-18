#!/usr/bin/env python3
"""Isolated GET-only bridge from SRW's running local service to the E1 HTML UI.

The Windows EXE chooses a dynamic port. Use --data-root to read its live
app.lock/instance.json, then verify the running backend's identity. This does
not start another SRW backend or open its SQLite database.

Security: loopback-only listener/upstream, explicit GET route allowlist, no
mutation proxy, no redirect following, no upstream proxies, bounded responses.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "e1-live.html"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_INSTANCE_FILE_BYTES = 128 * 1024

# E1 expressly excludes all other GET routes, including source files and
# provider/settings APIs. Unknown paths are blocked rather than forwarded.
ALLOWED_EXACT_PATHS = frozenset({
    "/health/ready",
    "/api/v1/info",
    "/api/v1/runtime/info",
    "/api/v1/dashboard",
    "/api/v1/projects",
})
ALLOWED_PATTERNS = (
    re.compile(r"^/api/v1/projects/[a-zA-Z0-9_-]{1,128}/(?:pipeline|candidates)$"),
    re.compile(r"^/api/v1/candidates/[a-zA-Z0-9_-]{1,128}/(?:summary|workspace|brief)$"),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Disallow environment HTTP proxy use when contacting localhost.
OPENER = build_opener(ProxyHandler({}), NoRedirect())


def is_allowed_api_path(path: str) -> bool:
    return path in ALLOWED_EXACT_PATHS or any(
        pattern.fullmatch(path) is not None for pattern in ALLOWED_PATTERNS
    )


def require_loopback_upstream(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Upstream must be a plain loopback HTTP origin, without credentials or path")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid upstream port") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValueError("Upstream must include an explicit TCP port")
    return value.rstrip("/")


def probe_json(upstream: str, path: str) -> dict:
    request = Request(
        upstream + path,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "SRW-E1-Probe/2"},
    )
    with OPENER.open(request, timeout=3) as response:
        if response.status != 200:
            raise ValueError(f"{path}: HTTP {response.status}")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError(f"{path}: response too large")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def select_upstream(*, supplied_url: str | None, data_root: str | None) -> tuple[str, dict]:
    """Attach to exactly one explicitly identified existing SRW instance."""
    lease = None
    if data_root:
        folder = Path(data_root).expanduser().resolve()
        lease_path = folder / "app.lock" / "instance.json"
        if not lease_path.is_file():
            raise ValueError(
                f"EXE lock file not found: {lease_path}. Keep the Windows EXE open, "
                "and pass its DATA directory (not the application root)."
            )
        if lease_path.stat().st_size > MAX_INSTANCE_FILE_BYTES:
            raise ValueError("EXE lock metadata exceeds expected size")
        lease = json.loads(lease_path.read_text(encoding="utf-8-sig"))
        if not isinstance(lease, dict) or lease.get("edition") != "windows":
            raise ValueError("Lock metadata does not identify a Windows SRW instance")
        try:
            port = int(lease["port"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Lock metadata has no valid port") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Windows SRW backend has not allocated a port yet")
        selected = f"http://127.0.0.1:{port}"
        if supplied_url and require_loopback_upstream(supplied_url) != selected:
            raise ValueError("--upstream does not match the live EXE lock port")
    elif supplied_url:
        selected = require_loopback_upstream(supplied_url)
    else:
        raise ValueError(
            "Provide --data-root PATH for the running Windows EXE, or "
            "--upstream http://127.0.0.1:PORT for a running SRW Web service."
        )

    selected = require_loopback_upstream(selected)
    info = probe_json(selected, "/api/v1/info")
    runtime = probe_json(selected, "/api/v1/runtime/info")
    if info.get("product") != "SRW" or runtime.get("product") != "SRW":
        raise ValueError("The selected local server is not SRW")
    if lease:
        checks = {
            "instance_id": (str(lease.get("instance_id") or ""), str(runtime.get("instanceId") or "")),
            "session_id": (str(lease.get("session_id") or ""), str(runtime.get("sessionId") or "")),
            "version": (str(lease.get("version") or ""), str(runtime.get("version") or "")),
            "data_root_hash": (str(lease.get("data_root_hash") or ""), str(runtime.get("dataScopeId") or "")),
        }
        for field, (expected, actual) in checks.items():
            if not expected or expected != actual:
                raise ValueError(f"EXE identity mismatch ({field}); refusing to attach")
        if runtime.get("runtime") != "desktop" or runtime.get("edition") != "windows":
            raise ValueError("Target process is not the Windows desktop backend")
        if info.get("instance_id") != runtime.get("instanceId"):
            raise ValueError("Backend instance identity differs across info endpoints")

    return selected, runtime


class ReadOnlyBridge(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ""
    listen_port = 0

    def log_message(self, fmt: str, *args) -> None:
        # Never log query strings, candidate identifiers or private payloads.
        path = urlsplit(self.path).path
        category = "api" if path.startswith("/api/") else "health" if path.startswith("/health/") else "static"
        print(f"[E1] {self.client_address[0]} {self.command} {category}", flush=True)

    def _reply(self, status: int, payload: bytes, content_type: str) -> None:
        # All E1 responses are one-request-per-connection. When an unsafe method
        # is rejected without consuming its body, keeping HTTP/1.1 alive would
        # make leftover bytes look like the beginning of the next request.
        # Closing connections also avoids accidental request-body log leakage.
        self.close_connection = True
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-SRW-Exploration", "html-e1-read-only")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _deny(self, status: int, reason: str) -> None:
        self._reply(status, reason.encode("utf-8"), "text/plain; charset=utf-8")

    def _valid_browser_request(self) -> bool:
        allowed_hosts = {
            f"127.0.0.1:{self.listen_port}",
            f"localhost:{self.listen_port}",
        }
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            self._deny(403, "Host is not the E1 loopback origin")
            return False
        if self.headers.get("Sec-Fetch-Site", "") not in {
            "", "none", "same-origin",
        }:
            self._deny(403, "Cross-origin request blocked")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {
            f"http://127.0.0.1:{self.listen_port}",
            f"http://localhost:{self.listen_port}",
        }:
            self._deny(403, "Cross-origin request blocked")
            return False
        return True

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if not is_allowed_api_path(parsed.path) or parsed.fragment:
            self._deny(404, "This API route is outside the E1 read-only allowlist")
            return
        target = self.upstream + self.path
        req = Request(
            target,
            method=self.command,
            headers={
                "Accept": "application/json",
                "User-Agent": "SRW-E1-ReadOnly-Bridge/2",
            },
        )
        try:
            with OPENER.open(req, timeout=15) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
                if len(payload) > MAX_RESPONSE_BYTES:
                    self._deny(502, "SRW API response exceeds E1 size limit")
                    return
                self._reply(status, payload, content_type)
        except HTTPError as exc:
            if 300 <= exc.code <= 399:
                self._deny(502, "Unexpected upstream redirect blocked")
                return
            payload = exc.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                self._deny(502, "SRW API error response exceeds E1 size limit")
                return
            self._reply(exc.code, payload, exc.headers.get("Content-Type", "application/json"))
        except (URLError, TimeoutError, OSError) as exc:
            self._deny(502, f"SRW upstream unavailable: {type(exc).__name__}")

    def do_GET(self) -> None:
        if not self._valid_browser_request():
            return
        parsed = urlsplit(self.path)
        if parsed.path in {"/", "/e1-live.html"} and not parsed.query:
            if not HTML.is_file():
                self._deny(500, "e1-live.html is missing")
                return
            self._reply(200, HTML.read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/favicon.ico":
            self._reply(204, b"", "image/x-icon")
        else:
            self._proxy()

    def do_HEAD(self) -> None:
        self.do_GET()

    def _mutation_denied(self) -> None:
        self._deny(405, "E1 is GET-only. No business mutation can be forwarded.")

    do_POST = _mutation_denied
    do_PUT = _mutation_denied
    do_PATCH = _mutation_denied
    do_DELETE = _mutation_denied
    do_OPTIONS = _mutation_denied


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach an isolated HTML E1 viewer to running SRW.")
    parser.add_argument("--data-root", help="Running SRW Windows EXE data directory")
    parser.add_argument("--upstream", default=os.environ.get("SRW_UPSTREAM"), help="Existing local SRW HTTP origin")
    parser.add_argument("--port", type=int, default=8877, help="E1 browser listener port (0 = OS-assigned)")
    parser.add_argument("--open-browser", action="store_true", help="Open browser after the bridge is bound")
    args = parser.parse_args()

    try:
        upstream, runtime = select_upstream(supplied_url=args.upstream, data_root=args.data_root)
    except (ValueError, OSError, URLError, HTTPError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReadOnlyBridge)
    port = int(server.server_address[1])
    ReadOnlyBridge.upstream = upstream
    ReadOnlyBridge.listen_port = port
    url = f"http://127.0.0.1:{port}/"

    print("SRW E1 HTML Exploration -- READ ONLY", flush=True)
    print(f"Web:      {url}", flush=True)
    print(f"Upstream: {upstream}", flush=True)
    print(f"Version:  {runtime.get('version', 'unknown')}", flush=True)
    print(f"Instance: {str(runtime.get('instanceId') or '')[:12]}...", flush=True)
    print("Only GET/HEAD routes in E1's allowlist can reach the SRW backend.", flush=True)
    print("Press Ctrl+C to stop. The EXE and its database are not managed by this bridge.", flush=True)
    if args.open_browser:
        threading.Timer(0.1, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
