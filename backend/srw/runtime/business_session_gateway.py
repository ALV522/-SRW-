"""Opt-in business session gateway for the Local Web carrier (#43 M3A).

Scope
-----
This module is the *only* place that turns a local operator into an HTTP
business session. It is inert unless ``RECRUITMENT_SESSION_ENFORCE`` is exactly
``1``; with the flag off the application behaves byte-for-byte as before.

Three credentials, deliberately distinct
----------------------------------------
* **pairing code** - random, single use, 60 second lifetime, printed only to the
  trusted interactive console by ``scripts/start_local_web.py``. It travels in a
  JSON POST body and never in a URL, a log line or an acceptance report. A
  redirected stdout has no trusted channel at all, so the launcher refuses to
  start rather than write the code into a collected log.
* **business session cookie** - opaque ``srw1.<tag>.<secret>`` from
  :class:`srw.supervisor.session_registry.SessionRegistry`, ``HttpOnly``,
  ``SameSite=Strict``, ``Path=/``. It is the only thing that authorises reads and
  writes, and it can never satisfy the Host lifecycle route.
* **CSRF token** - readable by same-origin JavaScript on purpose and required in
  ``X-SRW-CSRF`` for every mutating request. Readable does not mean sufficient:
  it cannot replace the HttpOnly session cookie.

Denials are decided from the raw ASGI header list, never from a dict, so two
contradictory ``Cookie`` headers or two credential headers are refused instead of
silently picking one. Every refusal happens before routing, so a denied request
cannot create a business row, an audit event or a file.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlsplit

from starlette.responses import JSONResponse

from srw.supervisor.session_registry import (
    DEFAULT_TTL_SECONDS,
    Session,
    SessionDenied,
    SessionRegistry,
)
from srw.supervisor.session_policy import TOKEN_QUERY_KEYS

COOKIE_NAME = "srw_business_session"
CSRF_COOKIE_NAME = "srw_csrf"
CSRF_HEADER = "x-srw-csrf"
PAIRING_PATH = "/api/v1/runtime/business-attach"
HOST_ATTACH_PATH = "/api/v1/runtime/host-business-attach"
LOGOUT_PATH = "/api/v1/runtime/business-logout"
#: The Host lifecycle route keeps its own independent secret. A business cookie
#: must never become a shutdown credential, so the gateway steps aside and lets
#: ``runtime.py`` apply its existing check.
LIFECYCLE_PATH = "/api/v1/runtime/shutdown"

PAIRING_TTL_SECONDS = 60.0
PAIRING_MAX_ATTEMPTS = 5
MAX_PAIRING_BODY = 512
PAIRING_CODE_BYTES = 24
#: The minted code is 32 characters; anything longer is not ours to hash.
MAX_PAIRING_CODE_LENGTH = 256

READ_SCOPE = "read"
WRITE_SCOPE = "write"
BUSINESS_SCOPES = (READ_SCOPE, WRITE_SCOPE)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Anonymous, credential-free surfaces. They carry no business data: liveness,
#: the static shell and its assets, the pairing endpoint and the lifecycle route.
ANONYMOUS_EXACT = frozenset({"/", "/v1", "/health/live", "/health/ready",
                             "/api/v1/runtime/ready", PAIRING_PATH,
                             HOST_ATTACH_PATH, LIFECYCLE_PATH})
ANONYMOUS_PREFIXES = ("/v1/",)

DENY_FLAG = "enforcement_disabled"
DENY_CREDENTIAL_IN_URL = "credential_in_url"
DENY_AMBIGUOUS_COOKIE = "ambiguous_cookie"
DENY_NO_SESSION = "session_cookie_required"
DENY_BAD_SESSION = "session_cookie_rejected"
DENY_NO_CSRF = "csrf_required"
DENY_BAD_CSRF = "csrf_rejected"
DENY_CROSS_SITE = "cross_site_request"
DENY_BODY_TOO_LARGE = "pairing_body_too_large"
DENY_PAIRING = "pairing_rejected"


@dataclass(frozen=True)
class Decision:
    """One authorisation answer. Never carries a credential or a token fragment."""

    allowed: bool
    status_code: int = 200
    reason: str = ""
    session: Session | None = None


def _raw_pairs(headers: Iterable[tuple[bytes, bytes]]) -> list[tuple[str, str]]:
    return [(name.decode("latin1").lower(), value.decode("latin1")) for name, value in headers]


def _is_canonical_pairing_code(code: object) -> bool:
    """True only for the ASCII text this module mints.

    ``isascii()`` is the exact guard ``encode('ascii')`` needs: it also rejects
    lone surrogates such as ``"\\ud800"``, which ``json.loads`` accepts and which
    neither ASCII nor UTF-8 can encode. Legal JSON is still untrusted input, so
    every shape check here is a refusal rather than an exception.
    """
    return (isinstance(code, str) and 0 < len(code) <= MAX_PAIRING_CODE_LENGTH
            and code.isascii())


def _presented_digest(code: str) -> bytes:
    """SHA-256 of a code already proven ASCII; never raises on hostile text."""
    try:
        encoded = code.encode("ascii")
    except UnicodeEncodeError as exc:  # defence in depth; the guard above is primary
        raise PairingDenied(DENY_PAIRING) from exc
    return hashlib.sha256(encoded).digest()


def _cookie_values(pairs: list[tuple[str, str]], name: str) -> tuple[list[str], bool]:
    """Return every value for ``name`` and whether the envelope was ambiguous.

    A duplicated ``Cookie`` header is ambiguous by itself: two headers mean a
    proxy and the application can disagree about which one counts.
    """
    cookie_headers = [value for key, value in pairs if key == "cookie"]
    ambiguous = len(cookie_headers) > 1
    values: list[str] = []
    for header in cookie_headers:
        for part in header.split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key.strip() == name:
                values.append(value.strip())
    if len(values) > 1:
        ambiguous = True
    return values, ambiguous


def _header_values(pairs: list[tuple[str, str]], name: str) -> list[str]:
    return [value for key, value in pairs if key == name]


def _same_origin(origin: str, host: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return parsed.netloc.lower().rstrip(".") == host.lower().rstrip(".")


class BusinessSessionGateway:
    """Pairing, cookie minting, CSRF and the per-request decision."""

    def __init__(self, *, clock: Callable[[], float] | None = None,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 pairing_ttl_seconds: float = PAIRING_TTL_SECONDS,
                 max_attempts: int = PAIRING_MAX_ATTEMPTS,
                 registry: SessionRegistry | None = None) -> None:
        self._clock = clock
        self._registry = registry or SessionRegistry(clock=clock, ttl_seconds=ttl_seconds)
        self._pairing_ttl = float(pairing_ttl_seconds)
        self._max_attempts = int(max_attempts)
        self._pairing: tuple[bytes, float] | None = None
        self._attempts = 0
        self._csrf: dict[str, str] = {}
        self._host_nonces: set[str] = set()

    # ---------------------------------------------------------------- pairing
    def issue_pairing_code(self) -> str:
        """Mint a single-use code. Only the digest is retained."""
        code = secrets.token_urlsafe(PAIRING_CODE_BYTES)
        self._pairing = (_presented_digest(code), self._now() + self._pairing_ttl)
        self._attempts = 0
        return code

    @property
    def has_pairing_code(self) -> bool:
        return self._pairing is not None and self._now() < self._pairing[1]

    def pair(self, code: object) -> tuple[str, str]:
        """Consume the code and mint one business session. Raises ``PairingDenied``.

        Shape is rejected *before* any state is read or written, so a hostile
        body cannot burn an attempt or clear the pending code; that keeps the
        "no side effect" promise of a refused pairing attempt.
        """
        if not _is_canonical_pairing_code(code):
            raise PairingDenied(DENY_PAIRING)
        pending = self._pairing
        if pending is None:
            raise PairingDenied(DENY_PAIRING)
        digest, expires_at = pending
        if self._now() >= expires_at:
            self._pairing = None
            raise PairingDenied(DENY_PAIRING)
        self._attempts += 1
        if self._attempts > self._max_attempts:
            self._pairing = None
            raise PairingDenied(DENY_PAIRING)
        if not hmac.compare_digest(_presented_digest(code), digest):
            raise PairingDenied(DENY_PAIRING)
        # Single use: the code dies with the attempt that consumed it.
        self._pairing = None
        return self._mint_business_session()

    def issue_host_session(self, nonce: str) -> tuple[str, str]:
        """Mint only once for a validated Host HMAC nonce (never the raw secret)."""
        if (not isinstance(nonce, str) or len(nonce) != 64
                or any(ch not in "0123456789abcdef" for ch in nonce)):
            raise PairingDenied("host_nonce_invalid")
        if nonce in self._host_nonces:
            raise PairingDenied("host_nonce_replayed")
        if len(self._host_nonces) >= 128:
            raise PairingDenied("host_attach_limit")
        self._host_nonces.add(nonce)
        return self._mint_business_session()

    def _mint_business_session(self) -> tuple[str, str]:
        token, session = self._registry.issue(BUSINESS_SCOPES)
        self._csrf[session.session_id] = secrets.token_urlsafe(32)
        return token, self._csrf[session.session_id]

    # --------------------------------------------------------------- sessions
    def csrf_for(self, session: Session) -> str:
        return self._csrf.get(session.session_id, "")

    def revoke(self, token: str) -> bool:
        session_id = self._session_id(token)
        if session_id is not None:
            self._csrf.pop(session_id, None)
        return self._registry.revoke(token)

    def _session_id(self, token: str) -> str | None:
        try:
            return self._registry.authorize(token, READ_SCOPE).session_id
        except SessionDenied:
            return None

    @property
    def registry(self) -> SessionRegistry:
        return self._registry

    # --------------------------------------------------------------- decision
    def evaluate(self, *, method: str, raw_path: str, query_string: str,
                 headers: Iterable[tuple[bytes, bytes]]) -> Decision:
        """Decide one request. Pure: it never mutates session or pairing state."""
        method = (method or "GET").upper()
        pairs = _raw_pairs(headers)
        host = next((value for key, value in pairs if key == "host"), "")

        # A credential in the URL lands in history and logs; it is refused even
        # when a perfectly valid cookie accompanies it.
        if self._query_carries_credential(query_string):
            return Decision(False, 401, DENY_CREDENTIAL_IN_URL)

        cookies, ambiguous = _cookie_values(pairs, COOKIE_NAME)
        if ambiguous:
            return Decision(False, 400, DENY_AMBIGUOUS_COOKIE)

        if raw_path in ANONYMOUS_EXACT or raw_path.startswith(ANONYMOUS_PREFIXES):
            # Static shell and pairing entry stay anonymous, but a browser must
            # never be handed a business credential by simply loading a page.
            return Decision(True, 200, "")

        if not cookies:
            return Decision(False, 401, DENY_NO_SESSION)
        token = cookies[0]
        try:
            session = self._registry.authorize(
                token, READ_SCOPE if method in SAFE_METHODS else WRITE_SCOPE)
        except SessionDenied:
            # One generic reason: the precise cause would tell an attacker
            # whether a tag was foreign, expired or simply unknown.
            return Decision(False, 401, DENY_BAD_SESSION)

        if method in MUTATING_METHODS:
            if self._cross_site(pairs, host):
                return Decision(False, 403, DENY_CROSS_SITE, session)
            csrf = _header_values(pairs, CSRF_HEADER)
            if not csrf:
                return Decision(False, 403, DENY_NO_CSRF, session)
            if len(csrf) != 1:
                return Decision(False, 403, DENY_BAD_CSRF, session)
            expected = self.csrf_for(session)
            # ``compare_digest`` raises ``TypeError`` for a non-ASCII ``str``, so
            # a legal but non-ASCII header value is refused *here* rather than
            # turning a security decision into a 500.
            if (not expected or not csrf[0].isascii()
                    or not hmac.compare_digest(csrf[0], expected)):
                return Decision(False, 403, DENY_BAD_CSRF, session)
        return Decision(True, 200, "", session)

    @staticmethod
    def _query_carries_credential(query_string: str) -> bool:
        if not query_string:
            return False
        try:
            pairs = parse_qsl(query_string, keep_blank_values=True, max_num_fields=32)
        except ValueError:
            # An unparseable query cannot be proven credential-free.
            return True
        return any(name.strip().lower() in TOKEN_QUERY_KEYS for name, _ in pairs)

    @staticmethod
    def _cross_site(pairs: list[tuple[str, str]], host: str) -> bool:
        origins = _header_values(pairs, "origin")
        if len(origins) != 1:
            # A browser mutation always states its origin once. Missing or
            # repeated means the request cannot be proven same-origin.
            return True
        if not _same_origin(origins[0], host):
            return True
        fetch_site = _header_values(pairs, "sec-fetch-site")
        if len(fetch_site) > 1:
            return True
        return bool(fetch_site) and fetch_site[0].strip().lower() not in ("same-origin", "")

    def _now(self) -> float:
        if self._clock is not None:
            return float(self._clock())
        import time
        return time.monotonic()


class PairingDenied(Exception):
    """Pairing refused. The message never contains the presented code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BusinessSessionMiddleware:
    """Pure ASGI middleware: refuse before routing, never after a write."""

    def __init__(self, app, *, gateway: BusinessSessionGateway) -> None:
        self.app = app
        self.gateway = gateway

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        decision = self.gateway.evaluate(
            method=str(scope.get("method") or "GET"),
            raw_path=str(scope.get("path") or ""),
            query_string=(scope.get("query_string") or b"").decode("latin1"),
            headers=scope.get("headers") or [],
        )
        if not decision.allowed:
            from starlette.responses import JSONResponse

            response = JSONResponse(
                {"detail": "business session refused",
                 "error": {"code": decision.reason}},
                status_code=decision.status_code,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def session_cookie_header(token: str) -> str:
    return (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict")


def csrf_cookie_header(csrf: str) -> str:
    # Readable by same-origin JS on purpose; it cannot authorise anything alone.
    return f"{CSRF_COOKIE_NAME}={csrf}; Path=/; SameSite=Strict"


def clear_cookie_headers() -> list[str]:
    return [f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
            f"{CSRF_COOKIE_NAME}=; Path=/; SameSite=Strict; Max-Age=0"]


def pairing_body_code(payload: bytes) -> str:
    """Extract the code from a bounded JSON body, refusing anything else.

    The body is untrusted JSON, so a *legal* string may still be non-ASCII, may
    hold a lone surrogate escape, or may not be a string at all. Each of those
    is a ``PairingDenied`` - never an exception escaping to a 500 - and none of
    them reaches the gateway, so a refused body cannot touch pairing state.
    """
    if len(payload) > MAX_PAIRING_BODY:
        raise PairingDenied(DENY_BODY_TOO_LARGE)
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PairingDenied(DENY_PAIRING) from exc
    if not isinstance(data, dict) or set(data) != {"code"}:
        raise PairingDenied(DENY_PAIRING)
    code = data["code"]
    if not _is_canonical_pairing_code(code):
        raise PairingDenied(DENY_PAIRING)
    return code
