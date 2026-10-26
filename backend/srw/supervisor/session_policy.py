"""Opt-in business-session authorization: pure decisions, no wiring.

Why this module exists
----------------------
Today the Core protects business writes only with the local boundary (loopback
bind, unique ``Host``, same-origin ``Origin``/``Sec-Fetch-Site``). That stops
cross-site pages and DNS rebinding, but it cannot distinguish *this* browser
from any other process running on the same machine. A session token closes that
gap. It is deliberately **off by default**, because the Native WPF Host talks to
loopback without an ``Origin`` and without a token; forcing a header first would
break the Windows carrier.

Ownership boundary
------------------
This module returns decisions and nothing else:

* no middleware, no route, no ``app.py`` change;
* no environment read at import time (``from_environ`` is explicit);
* no database, audit, logging or filesystem access, so a rejected request cannot
  leave an audit side effect;
* no Schema/version change.

Contract (phase 2, agreed with Track A)
---------------------------------------
* ``RECRUITMENT_SESSION_ENFORCE=1`` enables the gate. Every other value, and the
  absent variable, leaves it disabled. Only the literal ``1`` enables it: there
  is no "true"/"yes" aliasing that could be switched on by accident.
* The presented credential is the ``X-SRW-Session`` header. It is never accepted
  from the query string, because query strings land in logs and browser history.
  Detection parses query *keys* after percent-decoding them (``%5f`` and ``%255f``
  included) and never scans values, so ``description=mysession=note`` stays a
  normal filter.
* When the gate is enabled but no token is configured, every request that is not
  an anonymous bootstrap read is rejected. Enabling the gate without a token is
  a misconfiguration and must not silently allow writes.
* ``GET``/``HEAD`` may be anonymous only on a minimal bootstrap allowlist
  (health, readiness, capabilities, the local ``/v1`` static bundle). Everything
  else - including ``/api/v1/info``, ``/api/v1/runtime/info`` and
  ``/api/v1/runtime/live``, which expose instance/release/session identifiers -
  requires the session token.
* Any other method requires the session token, including ``OPTIONS``.
* A cross-origin request is refused even when it carries a valid token: the
  origin boundary is not something a header can buy its way past. ``Sec-Fetch-Site:
  same-site`` is refused too, for reads as well as writes; a request with no Fetch
  Metadata at all (the Native Host) is not rejected for the absence.
* Ambiguous paths are refused instead of normalised. Percent-encoding, back
  slashes, duplicate slashes and dot segments are rejected with ``400`` rather
  than reinterpreted, because "decode then match" is exactly how allowlists get
  bypassed.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import unquote_plus

#: Only the literal "1" enables enforcement.
ENFORCE_ENV = "RECRUITMENT_SESSION_ENFORCE"
#: Reuses the existing lifecycle token name; the value stays a caller concern.
TOKEN_ENV = "RECRUITMENT_SESSION_TOKEN"
#: Header carrying the session credential. Compared case-insensitively.
SESSION_HEADER = "X-SRW-Session"

#: Paths that may be read anonymously while the gate is enabled. Each entry is an
#: exact match after the ambiguity checks, never a prefix.
ANONYMOUS_READ_PATHS = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/api/v1/runtime/ready",
        "/api/v1/runtime/capabilities",
    }
)

#: The bundled SPA must keep loading so the page can show "reopen from the Host"
#: instead of a blank screen. Only static assets live here; no API path matches.
STATIC_READ_PREFIXES = ("/v1",)

SAFE_METHODS = frozenset({"GET", "HEAD"})

#: Query parameter names that are refused outright, even with the correct value.
#: Keys are compared after percent-decoding (up to two rounds) and case folding,
#: so ``session%5ftoken`` and ``x-srw-%73ession`` are the same key as
#: ``session_token`` and ``x-srw-session``. Values are never scanned.
TOKEN_QUERY_NAMES = ("x-srw-session", "session_token", "sessiontoken", "session")
TOKEN_QUERY_KEYS = frozenset(TOKEN_QUERY_NAMES)

#: Only an undecodable or still-encoded key is matched by hint, and only because
#: it cannot be classified safely. A plain value such as ``description=mysession``
#: must not be refused, so values are never inspected.
_AMBIGUOUS_QUERY_HINT = "session"

MAX_PATH_LENGTH = 2048

_ALLOWED_ASCII = frozenset(range(0x21, 0x7F))
_FORBIDDEN_PATH_CHARS = frozenset("\\%?#;")


@dataclass(frozen=True)
class SessionDecision:
    """One immutable authorization decision.

    ``status_code`` is ``200`` when allowed, otherwise the status the caller must
    return. ``reason`` is a stable, log-safe code (never the presented token).
    """

    allowed: bool
    status_code: int
    reason: str


def _allow(reason: str) -> SessionDecision:
    return SessionDecision(allowed=True, status_code=200, reason=reason)


def _deny(status_code: int, reason: str) -> SessionDecision:
    return SessionDecision(allowed=False, status_code=status_code, reason=reason)


def normalise_path(raw_path: object) -> str | None:
    """Return the path to match on, or ``None`` when it is ambiguous.

    Rejection, not rewriting, is the point: a decoder that turns ``%2f`` into
    ``/`` or drops ``.`` segments gives an attacker a second parser to disagree
    with. Callers must treat ``None`` as "refuse", never as "use the raw value".
    """

    if not isinstance(raw_path, str):
        return None
    if not raw_path.startswith("/"):
        return None
    if len(raw_path) > MAX_PATH_LENGTH:
        return None
    for char in raw_path:
        if ord(char) not in _ALLOWED_ASCII:
            return None
        if char in _FORBIDDEN_PATH_CHARS:
            return None
    if "//" in raw_path:
        return None

    body = raw_path[1:]
    if body.endswith("/"):
        body = body[:-1]
    if body == "":
        return "/"
    for segment in body.split("/"):
        if segment == "":
            # A duplicate or trailing duplicate slash: refuse rather than collapse.
            return None
        if segment in {".", ".."}:
            return None
        if segment != segment.strip():
            return None
        if segment.endswith("."):
            return None
    return raw_path


def _is_static(path: str) -> bool:
    if path == "/v1":
        return True
    return any(path.startswith(prefix + "/") for prefix in STATIC_READ_PREFIXES)


def _normalise_query_key(raw_key: str) -> str | None:
    """Decode a query key enough to classify it, or ``None`` if ambiguous.

    Two decode rounds cover ``%5f`` and ``%255f`` names. A key that still carries
    a percent escape after that is not guessed at; the caller refuses it when it
    looks session-related instead of deciding it is safe.
    """

    if not raw_key:
        return ""
    current = raw_key
    for _ in range(2):
        try:
            decoded = unquote_plus(current)
        except (UnicodeDecodeError, ValueError):
            return None
        if decoded == current:
            break
        current = decoded
    normalised = current.strip().casefold()
    if "%" in normalised:
        # Still encoded (or an invalid escape such as %zz): refuse to classify it.
        return None
    return normalised


def _query_carries_token(query_string: str) -> bool:
    """Detect a session credential passed as a query *key*.

    Values are deliberately ignored: ``description=mysession=note`` is an ordinary
    filter, while ``session_token=...`` is a credential that would land in logs and
    browser history. Both a positive and a negative case pin this distinction.
    """

    if not query_string:
        return False
    for pair in query_string.replace(";", "&").split("&"):
        if not pair:
            continue
        raw_key = pair.split("=", 1)[0]
        key = _normalise_query_key(raw_key)
        if key is None:
            if _AMBIGUOUS_QUERY_HINT in raw_key.casefold():
                return True
            continue
        if key in TOKEN_QUERY_KEYS:
            return True
    return False


def _lower_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


class SessionPolicy:
    """Immutable authorization policy; ``evaluate`` has no side effects."""

    __slots__ = ("enforce", "token", "allowed_origins", "revoked")

    def __init__(
        self,
        *,
        enforce: bool = False,
        token: str = "",
        allowed_origins: Iterable[str] = (),
        revoked: Iterable[str] = (),
    ) -> None:
        self.enforce = bool(enforce)
        self.token = token or ""
        self.allowed_origins = frozenset(
            origin.strip().rstrip("/").lower() for origin in allowed_origins if origin
        )
        self.revoked = frozenset(revoked)

    # ---------------------------------------------------------------- factories

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "SessionPolicy":
        """Build from an explicit mapping (never from ambient state at import)."""

        source = environ if environ is not None else {}
        enforce = str(source.get(ENFORCE_ENV, "")).strip() == "1"
        token = str(source.get(TOKEN_ENV, "")).strip()
        return cls(enforce=enforce, token=token)

    # ------------------------------------------------------------------ policy

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def is_revoked(self, token: str) -> bool:
        return token in self.revoked

    def rotated(self, new_token: str) -> "SessionPolicy":
        """Return a policy that accepts ``new_token`` and rejects the old one."""

        previous = {self.token} if self.token else set()
        return SessionPolicy(
            enforce=self.enforce,
            token=new_token,
            allowed_origins=self.allowed_origins,
            revoked=self.revoked | previous,
        )

    def evaluate(
        self,
        *,
        method: str,
        raw_path: object,
        headers: Mapping[str, str] | None = None,
        query_string: str = "",
    ) -> SessionDecision:
        """Decide one request. Pure: same inputs always yield the same decision."""

        if not self.enforce:
            # Default-off compatibility: the Host, the browser SPA and any local
            # script keep the exact behaviour they have today.
            return _allow("enforcement_disabled")

        path = normalise_path(raw_path)
        if path is None:
            return _deny(400, "ambiguous_path")

        if _query_carries_token(query_string):
            return _deny(401, "session_token_in_query")

        incoming = _lower_headers(headers)
        origin = incoming.get("origin", "").strip()
        site = incoming.get("sec-fetch-site", "").strip().lower()
        # same-site is not same-origin: another loopback port or another service on
        # the same registrable domain is still a different origin. Both are refused
        # for reads and writes; a caller that sends no Fetch Metadata at all (the
        # Native WPF Host) is unaffected because there is nothing to contradict.
        if site in {"cross-site", "same-site"}:
            return _deny(403, "origin_not_allowed")
        if origin and not self._origin_allowed(origin):
            return _deny(403, "origin_not_allowed")

        upper = (method or "").upper()
        if upper in SAFE_METHODS and (path in ANONYMOUS_READ_PATHS or _is_static(path)):
            return _allow("anonymous_bootstrap_path")

        presented = incoming.get(SESSION_HEADER.lower(), "")
        if not self.configured:
            # Enforced without a token must fail closed, not fall open.
            return _deny(401, "session_token_not_configured")
        if not presented:
            return _deny(401, "session_token_required")
        if not self._token_matches(presented):
            return _deny(401, "session_token_invalid")
        return _allow("ok")

    # ------------------------------------------------------------------ helpers

    def _origin_allowed(self, origin: str) -> bool:
        if not self.allowed_origins:
            # No configured origin set: only Origin-less callers (Native Host) may
            # authenticate. A browser that sends an Origin must be listed explicitly.
            return False
        return origin.strip().rstrip("/").lower() in self.allowed_origins

    def _token_matches(self, presented: str) -> bool:
        if not self.token or presented in self.revoked:
            return False
        return hmac.compare_digest(presented, self.token)
