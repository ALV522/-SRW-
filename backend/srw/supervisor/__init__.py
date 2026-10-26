"""Supervisor-level policy helpers.

This package is intentionally dependency-free: it carries decisions and
contracts that the API, the launcher and the Windows Host can share, without
importing FastAPI, SQLAlchemy, the audit log or the filesystem.

``session_policy`` is the opt-in business-session authorization core. It is
**not** wired into the API by this package; Track A owns the middleware and the
Host/Browser attach chain.
"""

from __future__ import annotations

from .session_policy import (
    ANONYMOUS_READ_PATHS,
    ENFORCE_ENV,
    SESSION_HEADER,
    STATIC_READ_PREFIXES,
    TOKEN_ENV,
    SessionDecision,
    SessionPolicy,
    normalise_path,
)

__all__ = [
    "ANONYMOUS_READ_PATHS",
    "ENFORCE_ENV",
    "SESSION_HEADER",
    "STATIC_READ_PREFIXES",
    "TOKEN_ENV",
    "SessionDecision",
    "SessionPolicy",
    "normalise_path",
]
