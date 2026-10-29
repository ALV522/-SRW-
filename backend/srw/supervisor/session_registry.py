"""Effect-free session registry for one authoritative Core instance.

Why this module exists
----------------------
``session_policy.py`` answers "may this request proceed?" from a single
configured token. That is enough for a gate, but it cannot express the lifecycle
the product needs next: one session per authorisation, a scope, an expiry, an
explicit revoke, and the guarantee that a token minted before a Core restart is
worthless afterwards. This module is that lifecycle, still with **no wiring**: it
issues and verifies opaque credentials and nothing else.

Ownership boundary
------------------
* no middleware, no route, no ``app.py`` change, no environment read;
* no database, audit, logging, filesystem or network access, so a denied call
  cannot leave a business side effect;
* no Schema/version change and no second Core;
* the public HTTP contract stays owned by Track A. This module is a decision
  engine that a later atomic integration can call.

Credential shape
----------------
``srw1.<instance tag>.<secret>``. The tag is random per registry instance, so a
token presented to a restarted Core fails on the tag *before* any lookup: a
restart invalidates credentials by construction rather than by remembering them.
Only a keyed digest of the secret is stored, never the secret itself.

Verification is constant time (``hmac.compare_digest`` on both the tag and the
digest) and denies by default: malformed, foreign-instance, unknown, expired and
out-of-scope presentations all raise :class:`SessionDenied`, and no denial
message, exception text or ``repr`` ever contains the presented token.
"""
from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

TOKEN_PREFIX = "srw1"
INSTANCE_TAG_BYTES = 8
SECRET_BYTES = 32
DIGEST_KEY_BYTES = 32
DEFAULT_TTL_SECONDS = 8 * 60 * 60.0
#: Refuse to hash unbounded input; a request cannot make us allocate by length.
MAX_TOKEN_LENGTH = 256

DENY_MALFORMED = "malformed_session"
DENY_FOREIGN_INSTANCE = "stale_instance"
DENY_UNKNOWN = "unknown_session"
DENY_EXPIRED = "expired_session"
DENY_SCOPE = "scope_not_granted"
DENY_CLOCK = "clock_unavailable"


class SessionDenied(Exception):
    """A refusal that carries a coarse reason and never the presented token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:  # keep ``str(exc)`` and logs token-free by construction
        return f"session denied: {self.reason}"


@dataclass(frozen=True)
class Session:
    """An issued session. The credential itself is never stored here."""

    session_id: str
    instance_tag: str
    scopes: frozenset[str]
    issued_at: float
    expires_at: float
    token_digest: bytes = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return (
            f"Session(session_id={self.session_id!r}, instance_tag={self.instance_tag!r}, "
            f"scopes={sorted(self.scopes)!r}, issued_at={self.issued_at!r}, "
            f"expires_at={self.expires_at!r})"
        )


class SessionRegistry:
    """Issue, authorise, revoke and expire sessions for a single Core instance."""

    def __init__(self, *, clock: Callable[[], float] | None = None,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 instance_tag: str | None = None) -> None:
        if not isinstance(ttl_seconds, (int, float)) or ttl_seconds != ttl_seconds:
            raise ValueError("session ttl must be a real number of seconds")
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        if instance_tag is None:
            instance_tag = secrets.token_hex(INSTANCE_TAG_BYTES)
        elif not isinstance(instance_tag, str) or not instance_tag:
            raise ValueError("instance tag must be a non-empty string")
        self._clock = clock if clock is not None else time.monotonic
        self._ttl = float(ttl_seconds)
        self._instance_tag = instance_tag
        self._digest_key = secrets.token_bytes(DIGEST_KEY_BYTES)
        self._sessions: dict[bytes, Session] = {}

    @property
    def instance_tag(self) -> str:
        return self._instance_tag

    def __len__(self) -> int:
        return len(self._sessions)

    def issue(self, scopes: Iterable[str] = ()) -> tuple[str, Session]:
        """Mint one credential. Returns ``(token, session)``; the token is not stored."""
        granted = self._normalise_scopes(scopes)
        now = self._now()
        secret = secrets.token_hex(SECRET_BYTES)
        token = f"{TOKEN_PREFIX}.{self._instance_tag}.{secret}"
        digest = self._digest(secret)
        session = Session(
            session_id=secrets.token_hex(16),
            instance_tag=self._instance_tag,
            scopes=granted,
            issued_at=now,
            expires_at=now + self._ttl,
            token_digest=digest,
        )
        self._sessions[digest] = session
        return token, session

    def authorize(self, token: str, scope: str) -> Session:
        """Return the session when ``token`` grants ``scope``; raise otherwise."""
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            raise SessionDenied(DENY_MALFORMED)
        if not isinstance(scope, str) or not scope:
            raise SessionDenied(DENY_SCOPE)
        prefix, _, rest = token.partition(".")
        if prefix != TOKEN_PREFIX:
            raise SessionDenied(DENY_MALFORMED)
        tag, _, secret = rest.partition(".")
        if not tag or not secret or "." in secret:
            raise SessionDenied(DENY_MALFORMED)
        # Restart fence first: a foreign instance never reaches the lookup table.
        if not hmac.compare_digest(tag, self._instance_tag):
            raise SessionDenied(DENY_FOREIGN_INSTANCE)
        digest = self._digest(secret)
        record = self._sessions.get(digest)
        if record is None:
            raise SessionDenied(DENY_UNKNOWN)
        if not hmac.compare_digest(record.token_digest, digest):
            raise SessionDenied(DENY_UNKNOWN)
        if self._now() >= record.expires_at:
            # Deny only; reclaiming is ``purge_expired``'s job so that every
            # verification path stays a read with no observable state change.
            raise SessionDenied(DENY_EXPIRED)
        if scope not in record.scopes:
            raise SessionDenied(DENY_SCOPE)
        return record

    def revoke(self, token: str) -> bool:
        """Forget one credential. Returns False when it was not live.

        No tombstone is kept: remembering revocations would need unbounded memory
        and would turn "revoked" into an oracle on credentials. A revoked token
        behaves exactly like an unknown one.
        """
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            return False
        prefix, _, rest = token.partition(".")
        if prefix != TOKEN_PREFIX:
            return False
        tag, _, secret = rest.partition(".")
        if not tag or not secret or "." in secret:
            return False
        if not hmac.compare_digest(tag, self._instance_tag):
            return False
        return self._sessions.pop(self._digest(secret), None) is not None

    def revoke_all(self) -> int:
        """Forget every live credential; returns how many were dropped."""
        dropped = len(self._sessions)
        self._sessions.clear()
        return dropped

    def purge_expired(self) -> int:
        """Drop records whose expiry has passed. Never resurrects anything."""
        now = self._now()
        expired = [digest for digest, record in self._sessions.items()
                   if now >= record.expires_at]
        for digest in expired:
            self._sessions.pop(digest, None)
        return len(expired)

    # -- internals -------------------------------------------------------
    def _now(self) -> float:
        try:
            now = float(self._clock())
        except Exception as exc:  # default deny: an unusable clock never authorises
            raise SessionDenied(DENY_CLOCK) from exc
        if now != now:  # NaN
            raise SessionDenied(DENY_CLOCK)
        return now

    def _digest(self, secret: str) -> bytes:
        return hmac.new(self._digest_key, secret.encode("utf-8"), "sha256").digest()

    @staticmethod
    def _normalise_scopes(scopes: Iterable[str]) -> frozenset[str]:
        if isinstance(scopes, (str, bytes)):
            raise ValueError("scopes must be an iterable of scope names, not a string")
        granted = frozenset(scopes)
        for scope in granted:
            if not isinstance(scope, str) or not scope.strip():
                raise ValueError("scope names must be non-empty strings")
        return granted
