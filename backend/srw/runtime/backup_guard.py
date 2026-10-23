"""Backup/restore mutex (ADR-0003 T8).

While a backup or a restore schedule runs, the workspace is not in a
consistent-write state: the other carrier's mutations and new attachments are
refused with 409 backup_in_progress instead of racing the file operations.
The Supervisor is the single writer, so an in-process guard is sufficient;
the restore execution itself still happens before the database opens.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager


class BackupGuard:
    """Reentrant hold/release guard with a human-readable reason."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._depth = 0
        self._reason = ""

    @property
    def active(self) -> bool:
        with self._lock:
            return self._depth > 0

    def status(self) -> dict:
        with self._lock:
            return {"active": self._depth > 0, "reason": self._reason}

    @contextmanager
    def hold(self, reason: str):
        with self._lock:
            self._depth += 1
            self._reason = str(reason)[:80]
        try:
            yield
        finally:
            with self._lock:
                self._depth -= 1
                if self._depth == 0:
                    self._reason = ""
