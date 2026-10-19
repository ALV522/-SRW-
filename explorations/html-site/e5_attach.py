"""E5 per-carrier attach capability + pinned Core identity, SYNTHETIC ONLY.

An independently owned C11 Core can serve multiple browser carriers, but a
listener being loopback-only is not itself authorization. E5 adds a per-carrier
one-time bootstrap URL and a random HttpOnly SameSite=Strict session cookie.

All API/static requests verify that the current Core's instance, session,
data scope and version still equal the pinned identity. A dead/replaced Core
fails closed. This is a prototype for a *real* authenticated attach protocol,
NOT production-grade auth (HTTP loopback, no user roles or TLS).
"""
from __future__ import annotations

import hmac
import secrets
import threading
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from e3_web_bridge import SyntheticE3Bridge
from serve_e1 import probe_json, select_upstream


IDENTITY_FIELDS=("product","instanceId","sessionId","dataScopeId","version","schemaVersion")


class E5ProtectedBridge(SyntheticE3Bridge):
    _token: str = ""
    _cookie_name: str = ""
    _identity: dict = {}
    _active: bool = True

    def _redirect_after_attach(self) -> None:
        """Redeem bootstrap capability without leaving the token in the URL."""
        self.close_connection=True
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{self._cookie_name}={self._token}; HttpOnly; SameSite=Strict; Path=/"
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.send_header("X-Frame-Options","DENY")
        self.end_headers()

    def _current_identity(self) -> dict:
        return probe_json(self.upstream, "/api/v1/runtime/info")

    def _identity_ok(self) -> bool:
        try:
            current=self._current_identity()
        except Exception:
            return False
        return all(
            self._identity.get(field) == current.get(field)
            and self._identity.get(field) not in (None, "")
            for field in IDENTITY_FIELDS
        )

    def _valid_browser_request(self) -> bool:
        if not super()._valid_browser_request():
            return False
        if not self._active or not self._identity_ok():
            self._deny(503, "Pinned SRW Core is unavailable or its identity changed")
            return False
        # Cookies are deliberately distinct per carrier: browser cookies are
        # scoped by hostname, NOT by localhost TCP port.
        cookies=SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            self._deny(403, "Malformed E5 attach cookie")
            return False
        sent=cookies.get(self._cookie_name)
        if sent is None or not hmac.compare_digest(sent.value, self._token):
            self._deny(403, "E5 carrier attachment is required")
            return False
        return True

    def do_GET(self):
        parsed=urlsplit(self.path)
        if parsed.path == "/attach" and not parsed.query:
            self._deny(404, "E5 attach token is required")
            return
        if parsed.path in {"/","/e3-live.html","/e5-live.html"} and not parsed.query:
            if not self._valid_browser_request():
                return
            page=Path(__file__).resolve().parent/"e3-live.html"
            if not page.is_file():
                self._deny(500,"Synthetic E5 HTML is missing")
                return
            # Reuse E3's tested UI without introducing another 40KB fork.
            # Only copy/caption text changes; no auth token enters HTML/JS.
            raw=page.read_text(encoding="utf-8")
            raw=raw.replace("SRW E3 · Atomic SQLite Write (Synthetic Only)",
                            "SRW E5 · Protected Shared Core (Synthetic Only)")
            raw=raw.replace("E3 atomic synthetic","E5 attached synthetic")
            raw=raw.replace("E3 真实数据库事务实验","E5 附着与事务实验")
            self._reply(200,raw.encode("utf-8"),"text/html; charset=utf-8")
            return
        if parsed.path.startswith("/attach/"):
            if not super()._valid_browser_request():
                return
            candidate=parsed.path[len("/attach/"):]
            if (parsed.query or parsed.fragment or not self._active
                or not hmac.compare_digest(candidate, self._token)):
                self._deny(403, "Invalid E5 attach capability")
                return
            if not self._identity_ok():
                self._deny(503, "Pinned SRW Core is unavailable or its identity changed")
                return
            self._redirect_after_attach()
            return
        super().do_GET()


def make_e5_carrier_server(
    *, upstream: str, candidate_ids: set[str], port: int = 0
) -> tuple[ThreadingHTTPServer, str]:
    if not candidate_ids:
        raise ValueError("E5 must receive real synthetic candidate IDs")
    upstream, pinned=select_upstream(supplied_url=upstream,data_root=None)
    if any(not pinned.get(field) for field in IDENTITY_FIELDS):
        raise ValueError("Incomplete Core identity; refusing E5 attachment")
    token=secrets.token_urlsafe(32)
    # Unique cookie name avoids accidental cross-port cookie collisions on
    # 127.0.0.1; a cookie for carrier A never authenticates carrier B.
    cookie_name="srw_e5_"+secrets.token_hex(10)
    cls=type("PinnedE5SyntheticCarrier",(E5ProtectedBridge,),{
        "upstream":upstream,
        "allowed_candidate_ids":frozenset(candidate_ids),
        "listen_port":0,
        "_identity":{field:pinned[field] for field in IDENTITY_FIELDS},
        "_token":token,
        "_cookie_name":cookie_name,
        "_active":True,
        "_write_lock":threading.RLock(),
    })
    server=ThreadingHTTPServer(("127.0.0.1",port),cls)
    cls.listen_port=server.server_address[1]
    return server,token
