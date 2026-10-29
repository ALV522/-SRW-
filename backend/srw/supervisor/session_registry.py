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

Canonical shape before comparison
---------------------------------
``hmac.compare_digest`` raises ``TypeError`` when a ``str`` operand holds
non-ASCII characters, so untrusted text must never reach it directly. Both the
tag and the secret are therefore validated against the exact alphabet this
module mints *before* any comparison: an unsupported character, a dot inside the
tag, a wrong-length or non-hex secret is ``DENY_MALFORMED`` rather than an
unhandled exception. The same validator constrains an injected ``instance_tag``
at construction time, because a tag we cannot parse would mint credentials we
cannot verify. TTL, clock readings and the resulting expiry are all required to
be finite: an infinite TTL, an infinite or NaN clock reading, and a finite
clock plus finite TTL that overflow to infinity are all refused, and a refused
``issue`` inserts nothing.
"""
from __future__ import annotations

import hmac
import math
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
#: Upper bound for an injected tag; the minted tag is ``2 * INSTANCE_TAG_BYTES``.
MAX_INSTANCE_TAG_LENGTH = 64
#: The only characters this module ever puts in, or accepts for, a tag.
TAG_ALPHABET = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
)
#: ``secrets.token_hex`` emits lowercase hex only.
SECRET_ALPHABET = frozenset("0123456789abcdef")

DENY_MALFORMED = "malformed_session"
DENY_FOREIGN_INSTANCE = "stale_instance"
DENY_UNKNOWN = "unknown_session"
DENY_EXPIRED = "expired_session"
DENY_SCOPE = "scope_not_granted"
DENY_CLOCK = "clock_unavailable"
DENY_EXPIRY = "expiry_unrepresentable"


class SessionDenied(Exception):
    """A refusal that carries a coarse reason and never the presented token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:  # keep ``str(exc)`` and logs token-free by construction
        return f"session denied: {self.reason}"


def _is_canonical_tag(tag: object) -> bool:
    """True only for text this module would ever mint as an instance tag."""
    return (
        isinstance(tag, str)
        and 0 < len(tag) <= MAX_INSTANCE_TAG_LENGTH
        and all(character in TAG_ALPHABET for character in tag)
    )


def _is_canonical_secret(secret: object) -> bool:
    """True only for the fixed-width lowercase hex this module mints."""
    return (
        isinstance(secret, str)
        and len(secret) == SECRET_BYTES * 2
        and all(character in SECRET_ALPHABET for character in secret)
    )


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
        if not isinstance(ttl_seconds, (int, float)) or isinstance(ttl_seconds, bool):
            raise ValueError("session ttl must be a real number of seconds")
        if not math.isfinite(float(ttl_seconds)):
            raise ValueError("session ttl must be finite")
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        if instance_tag is None:
            instance_tag = secrets.token_hex(INSTANCE_TAG_BYTES)
        elif not isinstance(instance_tag, str) or not instance_tag:
            raise ValueError("instance tag must be a non-empty string")
        elif not _is_canonical_tag(instance_tag):
            raise ValueError(
                "instance tag must be 1-64 characters of [A-Za-z0-9_-]; a dot or a "
                "non-ASCII character would mint an unparseable credential"
            )
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
        # Finite + finite can still overflow to infinity; refuse before minting so
        # a failed issue cannot leave an immortal record behind.
        expires_at = now + self._ttl
        if not math.isfinite(expires_at):
            raise SessionDenied(DENY_EXPIRY)
        secret = secrets.token_hex(SECRET_BYTES)
        token = f"{TOKEN_PREFIX}.{self._instance_tag}.{secret}"
        digest = self._digest(secret)
        session = Session(
            session_id=secrets.token_hex(16),
            instance_tag=self._instance_tag,
            scopes=granted,
            issued_at=now,
            expires_at=expires_at,
            token_digest=digest,
        )
        self._sessions[digest] = session
        return token, session

    def authorize(self, token: str, scope: str) -> Session:
        """Return the session when ``token`` grants ``scope``; raise otherwise."""
        parsed = self._parse(token)
        if parsed is None:
            raise SessionDenied(DENY_MALFORMED)
        tag, secret = parsed
        if not isinstance(scope, str) or not scope:
            raise SessionDenied(DENY_SCOPE)
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
        parsed = self._parse(token)
        if parsed is None:
            return False
        tag, secret = parsed
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
    @staticmethod
    def _parse(token: object) -> tuple[str, str] | None:
        """Split ``srw1.<tag>.<secret>`` into canonical parts, or return None.

        Returning ``None`` instead of raising keeps ``authorize`` (deny) and
        ``revoke`` (``False``) on one parser contract. Nothing here compares,
        hashes or logs the presented text, so a hostile value cannot reach
        ``hmac.compare_digest`` and cannot appear in an error message.
        """
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        prefix, _, rest = token.partition(".")
        if prefix != TOKEN_PREFIX:
            return None
        tag, _, secret = rest.partition(".")
        if "." in secret:
            return None
        if not _is_canonical_tag(tag):
            return None
        if not _is_canonical_secret(secret):
            return None
        return tag, secret

    def _now(self) -> float:
        try:
            now = float(self._clock())
        except Exception as exc:  # default deny: an unusable clock never authorises
            raise SessionDenied(DENY_CLOCK) from exc
        if not math.isfinite(now):  # NaN and both infinities
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
