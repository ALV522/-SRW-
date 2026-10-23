"""SRW Core Supervisor: attach protocol and refcounted carrier lifecycle (ADR-0003 S1/S5).

The Supervisor is the only process that holds the workspace lease. Carriers
(WPF Host, local-web launcher, browser tab) attach to it over loopback HTTP;
the Supervisor tracks every attachment, refreshes liveness from heartbeats,
auto-detaches silent carriers, and exits after an idle grace period once the
last carrier is gone. This module is pure logic (clock injectable, no sockets,
no processes) so the lifecycle rules are unit-testable; runtime.py wires it to
uvicorn and the workspace lease.
"""
from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass


DEFAULT_IDLE_GRACE_SECONDS = 300.0
DEFAULT_ATTACH_TIMEOUT_SECONDS = 90.0


class SupervisorError(RuntimeError):
    """Base class for attach-protocol failures."""


class UnknownAttachment(SupervisorError):
    """The attach_id is not registered on this Supervisor."""


class InvalidToken(SupervisorError):
    """The token does not match the attachment."""


class SupervisorShuttingDown(SupervisorError):
    """The Supervisor is exiting and no longer accepts attachments."""


@dataclass(frozen=True)
class Attachment:
    attach_id: str
    token: str
    carrier: str
    edition: str
    attached_at: float
    last_heartbeat_at: float

    def public_view(self) -> dict:
        return {
            "attach_id": self.attach_id,
            "carrier": self.carrier,
            "edition": self.edition,
            "attached_at": self.attached_at,
            "last_heartbeat_at": self.last_heartbeat_at,
        }


@dataclass(frozen=True)
class CarrierSession:
    """One issued carrier session (ADR-0003 S3). The token never leaves memory."""

    session_id: str
    attach_id: str
    supervisor_instance_id: str
    edition: str
    carrier: str
    session_token: str
    csrf_token: str
    issued_at: float
    last_seen_at: float
    revoked_reason: str = ""

    @property
    def revoked(self) -> bool:
        return bool(self.revoked_reason)

    def record_view(self) -> dict:
        """The persistable projection (no secrets)."""
        return {
            "session_id": self.session_id,
            "attach_id": self.attach_id,
            "supervisor_instance_id": self.supervisor_instance_id,
            "edition": self.edition,
            "carrier": self.carrier,
            "issued_at": self.issued_at,
            "last_seen_at": self.last_seen_at,
            "revoked_reason": self.revoked_reason,
        }


@dataclass(frozen=True)
class SupervisorStatus:
    instance_id: str
    attachments: int
    idle_grace_seconds: float
    idle_deadline: float | None
    shutting_down: bool

    def public_view(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "attachments": self.attachments,
            "idle_grace_seconds": self.idle_grace_seconds,
            "idle_deadline": self.idle_deadline,
            "shutting_down": self.shutting_down,
        }


class SessionRegistry:
    """In-memory one-time carrier sessions with an optional persistence hook.

    ``persist`` receives the persistable projection on issue and on revocation;
    the Supervisor runtime wires it to the carrier_session table so revocation
    is auditable without any token ever touching disk.
    """

    def __init__(self, *, persist=None, clock=time.monotonic) -> None:
        self._persist = persist
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, CarrierSession] = {}

    def issue(self, *, attach_id: str, supervisor_instance_id: str, edition: str, carrier: str) -> CarrierSession:
        with self._lock:
            now = self._clock()
            session = CarrierSession(
                session_id=uuid.uuid4().hex,
                attach_id=attach_id,
                supervisor_instance_id=supervisor_instance_id,
                edition=str(edition or "")[:40],
                carrier=str(carrier or "")[:120],
                session_token=secrets.token_hex(24),
                csrf_token=secrets.token_hex(24),
                issued_at=now,
                last_seen_at=now,
            )
            self._sessions[session.session_id] = session
            if self._persist is not None:
                self._persist("issue", session.record_view())
            return session

    def validate(self, session_id: str, session_token: str) -> CarrierSession | None:
        with self._lock:
            session = self._sessions.get(str(session_id or ""))
            if session is None or session.revoked:
                return None
            if not secrets.compare_digest(session.session_token, str(session_token or "")):
                return None
            object.__setattr__(session, "last_seen_at", self._clock())
            return session

    def csrf_ok(self, session: CarrierSession, csrf_token: str) -> bool:
        return secrets.compare_digest(session.csrf_token, str(csrf_token or ""))

    def revoke(self, session_id: str, reason: str) -> bool:
        with self._lock:
            session = self._sessions.get(str(session_id or ""))
            if session is None or session.revoked:
                return False
            object.__setattr__(session, "revoked_reason", str(reason)[:120])
            if self._persist is not None:
                self._persist("revoke", session.record_view())
            return True

    def revoke_attach(self, attach_id: str, reason: str) -> int:
        with self._lock:
            return sum(
                1
                for session in list(self._sessions.values())
                if session.attach_id == str(attach_id) and self.revoke(session.session_id, reason)
            )

    def revoke_all(self, reason: str) -> int:
        with self._lock:
            return sum(
                1 for session_id in list(self._sessions) if self.revoke(session_id, reason)
            )

    def active_views(self) -> list[dict]:
        with self._lock:
            return [s.record_view() for s in self._sessions.values() if not s.revoked]


class SupervisorService:
    """In-memory attach registry with refcounted idle lifecycle."""

    def __init__(
        self,
        *,
        instance_id: str | None = None,
        idle_grace_seconds: float = DEFAULT_IDLE_GRACE_SECONDS,
        attach_timeout_seconds: float = DEFAULT_ATTACH_TIMEOUT_SECONDS,
        session_persist=None,
        clock=time.monotonic,
    ) -> None:
        if idle_grace_seconds < 0:
            raise ValueError("idle_grace_seconds must not be negative")
        self.instance_id = instance_id or uuid.uuid4().hex
        self.idle_grace_seconds = float(idle_grace_seconds)
        self.attach_timeout_seconds = float(attach_timeout_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._attachments: dict[str, Attachment] = {}
        self._idle_deadline: float | None = None
        self._shutting_down = False
        self.sessions = SessionRegistry(persist=session_persist, clock=clock)

    # -- lifecycle ------------------------------------------------------
    def attach(self, *, carrier: str, edition: str = "") -> Attachment:
        with self._lock:
            if self._shutting_down:
                raise SupervisorShuttingDown("supervisor is shutting down")
            now = self._clock()
            attachment = Attachment(
                attach_id=uuid.uuid4().hex,
                token=secrets.token_hex(24),
                carrier=str(carrier or "unknown")[:120],
                edition=str(edition or "")[:40],
                attached_at=now,
                last_heartbeat_at=now,
            )
            self._attachments[attachment.attach_id] = attachment
            # A live attachment cancels any pending idle exit.
            self._idle_deadline = None
            # ADR-0003 S3: every attach also issues one one-time session.
            session = self.sessions.issue(
                attach_id=attachment.attach_id,
                supervisor_instance_id=self.instance_id,
                edition=attachment.edition,
                carrier=attachment.carrier,
            )
            object.__setattr__(attachment, "session", session)
            return attachment

    def heartbeat(self, attach_id: str, token: str) -> SupervisorStatus:
        with self._lock:
            attachment = self._require(attach_id, token)
            object.__setattr__(attachment, "last_heartbeat_at", self._clock())
            return self.status()

    def detach(self, attach_id: str, token: str) -> SupervisorStatus:
        with self._lock:
            self._require(attach_id, token)
            del self._attachments[attach_id]
            self.sessions.revoke_attach(attach_id, "detached")
            if not self._attachments and not self._shutting_down:
                self._idle_deadline = self._clock() + self.idle_grace_seconds
            return self.status()

    def expire_stale(self) -> list[str]:
        """Drop attachments whose carrier stopped heartbeating; returns removed ids."""
        with self._lock:
            now = self._clock()
            stale = [
                attach_id
                for attach_id, attachment in self._attachments.items()
                if now - attachment.last_heartbeat_at > self.attach_timeout_seconds
            ]
            for attach_id in stale:
                del self._attachments[attach_id]
                self.sessions.revoke_attach(attach_id, "carrier_silent")
            if stale and not self._attachments and self._idle_deadline is None and not self._shutting_down:
                self._idle_deadline = now + self.idle_grace_seconds
            return stale

    def begin_shutdown(self) -> None:
        with self._lock:
            self._shutting_down = True
            self._idle_deadline = None
            self.sessions.revoke_all("supervisor_exit")

    # -- queries --------------------------------------------------------
    def status(self) -> SupervisorStatus:
        with self._lock:
            return SupervisorStatus(
                instance_id=self.instance_id,
                attachments=len(self._attachments),
                idle_grace_seconds=self.idle_grace_seconds,
                idle_deadline=self._idle_deadline,
                shutting_down=self._shutting_down,
            )

    def idle_exit_due(self) -> bool:
        with self._lock:
            return (
                self._idle_deadline is not None
                and not self._attachments
                and not self._shutting_down
                and self._clock() >= self._idle_deadline
            )

    def attachment_views(self) -> list[dict]:
        with self._lock:
            return [a.public_view() for a in self._attachments.values()]

    def _require(self, attach_id: str, token: str) -> Attachment:
        attachment = self._attachments.get(str(attach_id or ""))
        if attachment is None:
            raise UnknownAttachment(f"unknown attachment: {attach_id}")
        if not secrets.compare_digest(attachment.token, str(token or "")):
            raise InvalidToken("attachment token mismatch")
        return attachment
