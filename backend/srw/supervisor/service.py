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


class SupervisorService:
    """In-memory attach registry with refcounted idle lifecycle."""

    def __init__(
        self,
        *,
        instance_id: str | None = None,
        idle_grace_seconds: float = DEFAULT_IDLE_GRACE_SECONDS,
        attach_timeout_seconds: float = DEFAULT_ATTACH_TIMEOUT_SECONDS,
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
            if stale and not self._attachments and self._idle_deadline is None and not self._shutting_down:
                self._idle_deadline = now + self.idle_grace_seconds
            return stale

    def begin_shutdown(self) -> None:
        with self._lock:
            self._shutting_down = True
            self._idle_deadline = None

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
