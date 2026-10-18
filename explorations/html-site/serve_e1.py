#!/usr/bin/env python3
"""Read-only same-origin bridge for the isolated SRW HTML E1 experiment.

This file is exploration-only. It never imports or mutates SRW production code.
It serves e1-live.html and proxies GET/HEAD requests to an already-running SRW
local service so the experimental page can consume real APIs without CORS.

All mutation methods are rejected locally with HTTP 405.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
HTML = ROOT / "e1-live.html"
DEFAULT_UPSTREAM = os.environ.get("SRW_UPSTREAM", "http://127.0.0.1:8765").rstrip("/")

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ReadOnlyBridge(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = DEFAULT_UPSTREAM

    def log_message(self, fmt: str, *args) -> None:
        print(f"[E1] {self.address_string()} - {fmt % args}")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-SRW-Exploration", "html-e1-read-only")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_html(self) -> None:
        if not HTML.exists():
            self._send_bytes(500, b"e1-live.html is missing", "text/plain; charset=utf-8")
            return
        self._send_bytes(200, HTML.read_bytes(), "text/html; charset=utf-8")

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if not (parsed.path.startswith("/api/") or parsed.path.startswith("/health/")):
            self._send_bytes(404, b"Not found", "text/plain; charset=utf-8")
            return

        target = self.upstream + self.path
        request = Request(
            target,
            method=self.command,
            headers={
                "Accept": self.headers.get("Accept", "application/json"),
                "User-Agent": "SRW-E1-ReadOnly-Bridge/1",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                body = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in HOP_BY_HOP or key.lower() in {"content-length", "cache-control"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-SRW-Exploration", "html-e1-read-only")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
        except HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-SRW-Exploration", "html-e1-read-only")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except URLError as exc:
            message = (
                "SRW upstream unavailable. Start the existing SRW service/EXE and "
                f"check --upstream. Detail: {exc.reason}"
            ).encode("utf-8")
            self._send_bytes(502, message, "text/plain; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in {"/", "/e1-live.html"}:
            self._serve_html()
        elif parsed.path == "/favicon.ico":
            self._send_bytes(204, b"", "image/x-icon")
        else:
            self._proxy()

    def do_HEAD(self) -> None:
        self.do_GET()

    def _reject_mutation(self) -> None:
        message = (
            "E1 exploration is read-only. POST/PATCH/PUT/DELETE are deliberately disabled."
        ).encode("utf-8")
        self._send_bytes(405, message, "text/plain; charset=utf-8")

    do_POST = _reject_mutation
    do_PATCH = _reject_mutation
    do_PUT = _reject_mutation
    do_DELETE = _reject_mutation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the isolated SRW E1 HTML prototype against a running local SRW service."
    )
    parser.add_argument(
        "--upstream",
        default=DEFAULT_UPSTREAM,
        help="Existing SRW local service, e.g. http://127.0.0.1:8765",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8877,
        help="Loopback port for the exploration site (default: 8877)",
    )
    args = parser.parse_args()

    upstream = args.upstream.rstrip("/")
    parsed = urlsplit(upstream)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("--upstream must be an absolute http(s) URL")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("E1 bridge only permits a loopback SRW upstream")

    ReadOnlyBridge.upstream = upstream
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReadOnlyBridge)

    print("SRW HTML E1 read-only bridge")
    print(f"  Web:      http://127.0.0.1:{args.port}/")
    print(f"  Upstream: {upstream}")
    print("  Policy:   GET/HEAD only; all mutation methods return 405")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
