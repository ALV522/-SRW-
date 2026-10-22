"""SRW Core Supervisor package (ADR-0003).

S1: the Supervisor is the only process holding the workspace lease; carriers
attach to it over loopback HTTP. S5: attach / reattach / heartbeat / detach
with a refcounted idle lifecycle (last detach starts the grace period, a new
attach cancels it, a silent carrier is auto-detached).
"""
from srw.supervisor.service import (  # noqa: F401
    DEFAULT_ATTACH_TIMEOUT_SECONDS,
    DEFAULT_IDLE_GRACE_SECONDS,
    Attachment,
    InvalidToken,
    SupervisorError,
    SupervisorService,
    SupervisorShuttingDown,
    SupervisorStatus,
    UnknownAttachment,
)
