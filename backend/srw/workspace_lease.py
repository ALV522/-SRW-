"""Single-writer workspace lease shared by every SRW carrier.

SRW has one authoritative Core per workspace (ADR-0001, DUAL_CARRIER_PLAN D1).
Before a carrier opens SQLite it must hold this lease. The lease is a lock
*directory* named ``app.lock`` inside the workspace ``data`` directory, created
with an atomic filesystem operation, holding an ``instance.json`` metadata file.

The on-disk shape is not invented here: it mirrors the schema-v2 lease that
``desktop/SRW.Desktop/Workspace/WorkspaceLease.cs`` already writes, so the WPF
Host and the local HTML/Browser Core contend on the *same* path with the *same*
atomic primitive (``CreateDirectoryW`` / ``os.mkdir``). Before this module the
browser entry only *looked* for ``app.lock`` and then took a different,
non-competing lock file, so a Host started while the browser Core was running
could acquire the workspace and both processes would write the same database.
That is the defect this contract closes.

Deliberate asymmetry: ``process_started_at_utc`` is written as ``null``.
The C# reader treats a null value on a live PID as "active" (it returns early
on missing process identity), which is fail-closed for this process. Writing a
value that the .NET reader compared with a >1 ms tolerance could make it delete
a *live* lease, which would be worse than leaving stale recovery to the PID
liveness rule. Stale recovery therefore relies on PID liveness on both sides.

Failure policy is fail-closed everywhere: an unreadable, foreign, symlinked or
corrupt lease is rejected instead of being cleared. Only a lease whose recorded
PID is provably gone, or a metadata-less directory older than
``FRESH_INCOMPLETE_WINDOW_SECONDS``, is recovered.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LEASE_DIRECTORY_NAME = "app.lock"
LEASE_METADATA_NAME = "instance.json"
LEASE_SCHEMA_VERSION = 2
FRESH_INCOMPLETE_WINDOW_SECONDS = 5.0
KNOWN_EDITIONS = ("windows", "local-web")

ABSENT = "absent"
ACTIVE = "active"
STALE = "stale"
FOREIGN = "foreign"
CORRUPT = "corrupt"

_RECOVERABLE = frozenset({STALE})


class WorkspaceLeaseError(RuntimeError):
    """Raised when the workspace cannot be taken as the single writer."""


def lease_directory(data_dir: Path | str) -> Path:
    return Path(data_dir) / LEASE_DIRECTORY_NAME


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_root_hash(data_dir: Path | str) -> str:
    normalised = os.path.normcase(os.path.abspath(str(data_dir)))
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def process_alive(pid: int) -> bool:
    """Best-effort liveness probe; ambiguous answers are treated as alive."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import psutil
    except Exception:
        psutil = None
    if psutil is not None:
        try:
            return bool(psutil.pid_exists(pid))
        except Exception:
            return True
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


@dataclass(frozen=True)
class LeaseHolder:
    pid: int
    edition: str
    instance_id: str
    started_at: str
    port: int
    data_dir: str
    schema_version: int

    def is_active(self) -> bool:
        return process_alive(self.pid)

    def describe(self) -> str:
        owner = self.edition or "unknown carrier"
        return f"{owner} pid {self.pid} since {self.started_at or 'unknown'}"


@dataclass(frozen=True)
class LeaseInspection:
    state: str
    holder: LeaseHolder | None = None
    detail: str = ""

    @property
    def blocks(self) -> bool:
        """True when the caller must not become the writer."""
        return self.state in (ACTIVE, FOREIGN, CORRUPT)

    @property
    def recoverable(self) -> bool:
        return self.state in _RECOVERABLE


def _parse_holder(payload: object) -> LeaseHolder | None:
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    port = payload.get("port")
    return LeaseHolder(
        pid=pid,
        edition=str(payload.get("edition") or ""),
        instance_id=str(payload.get("instance_id") or ""),
        started_at=str(payload.get("started_at") or ""),
        port=port if isinstance(port, int) and not isinstance(port, bool) else 0,
        data_dir=str(payload.get("data_dir") or ""),
        schema_version=payload.get("schema_version") if isinstance(payload.get("schema_version"), int) else 0,
    )


def inspect_lease(data_dir: Path | str) -> LeaseInspection:
    """Read-only lease inspection. Never creates, repairs or deletes anything."""
    path = lease_directory(data_dir)
    if path.is_symlink():
        return LeaseInspection(FOREIGN, detail="app.lock is a symbolic link")
    if not path.exists():
        return LeaseInspection(ABSENT)
    if not path.is_dir():
        return LeaseInspection(FOREIGN, detail="app.lock exists but is not a directory")
    metadata = path / LEASE_METADATA_NAME
    if metadata.is_symlink():
        return LeaseInspection(FOREIGN, detail="app.lock/instance.json is a symbolic link")
    if not metadata.is_file():
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return LeaseInspection(FOREIGN, detail="app.lock metadata is unreadable")
        if age < FRESH_INCOMPLETE_WINDOW_SECONDS:
            return LeaseInspection(ACTIVE, detail="another carrier is still initialising its lease")
        return LeaseInspection(STALE, detail="app.lock directory without instance.json")
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return LeaseInspection(CORRUPT, detail="app.lock/instance.json is not valid JSON")
    holder = _parse_holder(payload)
    if holder is None:
        return LeaseInspection(CORRUPT, detail="app.lock/instance.json has no usable pid")
    if holder.is_active():
        return LeaseInspection(ACTIVE, holder=holder)
    return LeaseInspection(STALE, holder=holder, detail=f"holding process {holder.pid} is gone")


class WorkspaceLease:
    """Exclusive single-writer lease over one SRW workspace ``data`` directory."""

    def __init__(self, data_dir: Path | str, *, edition: str, port: int = 0,
                 version: str = "", release_id: str = "", session_id: str = "",
                 instance_id: str | None = None):
        if edition not in KNOWN_EDITIONS:
            raise ValueError(f"lease edition must be one of {KNOWN_EDITIONS}, got {edition!r}")
        self.data_dir = Path(data_dir)
        self.directory = lease_directory(self.data_dir)
        self.metadata_path = self.directory / LEASE_METADATA_NAME
        self.edition = edition
        self.port = port
        self.version = version
        self.release_id = release_id
        self.session_id = session_id
        self.instance_id = instance_id or uuid.uuid4().hex
        self._owned = False

    @property
    def held(self) -> bool:
        return self._owned

    def acquire(self) -> "WorkspaceLease":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for attempt in (0, 1):
            try:
                os.mkdir(self.directory)
            except FileExistsError:
                inspection = inspect_lease(self.data_dir)
                if inspection.recoverable and attempt == 0 and self._recover(inspection):
                    continue
                raise WorkspaceLeaseError(self._blocked_message(inspection)) from None
            except OSError as exc:
                raise WorkspaceLeaseError(f"cannot create workspace lease {self.directory}: {exc}") from exc
            self._owned = True
            try:
                self._write_metadata()
            except Exception:
                self._discard_own_lease()
                raise
            return self
        raise WorkspaceLeaseError(self._blocked_message(inspect_lease(self.data_dir)))

    def update_port(self, port: int) -> None:
        self._require_owned()
        self.port = port
        self._write_metadata()

    def release(self) -> None:
        if not self._owned:
            return
        try:
            current = self._read_metadata()
            if isinstance(current, dict) and current.get("instance_id") == self.instance_id:
                (self.directory / LEASE_METADATA_NAME).unlink(missing_ok=True)
                os.rmdir(self.directory)
        except OSError:
            pass
        finally:
            self._owned = False

    def __enter__(self) -> "WorkspaceLease":
        if not self._owned:
            self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def describe(self) -> str:
        return f"{self.edition} pid {os.getpid()} instance {self.instance_id}"

    def _metadata(self) -> dict:
        return {
            "schema_version": LEASE_SCHEMA_VERSION,
            "pid": os.getpid(),
            "port": self.port,
            "version": self.version,
            "release_id": self.release_id,
            "instance_id": self.instance_id,
            "session_id": self.session_id,
            "edition": self.edition,
            "started_at": _now_utc(),
            "process_started_at_utc": None,
            "hostname": socket.gethostname(),
            "data_dir": os.path.abspath(str(self.data_dir)),
            "data_root_hash": _data_root_hash(self.data_dir),
        }

    def _write_metadata(self) -> None:
        target = self.directory / LEASE_METADATA_NAME
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(self._metadata(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)

    def _read_metadata(self):
        try:
            return json.loads((self.directory / LEASE_METADATA_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _recover(self, inspection: LeaseInspection) -> bool:
        """Clear a provably stale lease. Re-inspects to avoid deleting a fresh one."""
        if self.directory.is_symlink():
            return False
        current = inspect_lease(self.data_dir)
        if current.state != STALE:
            return False
        if inspection.holder is not None and current.holder is not None:
            if current.holder.instance_id != inspection.holder.instance_id:
                return False
        try:
            shutil.rmtree(self.directory)
        except OSError:
            return False
        return True

    def _discard_own_lease(self) -> None:
        self._owned = False
        try:
            (self.directory / LEASE_METADATA_NAME).unlink(missing_ok=True)
            os.rmdir(self.directory)
        except OSError:
            pass

    def _require_owned(self) -> None:
        if not self._owned:
            raise WorkspaceLeaseError("workspace lease is not held by this instance")

    def _blocked_message(self, inspection: LeaseInspection) -> str:
        if inspection.state == ACTIVE and inspection.holder is not None:
            return (
                "INSTANCE_ALREADY_RUNNING: app.lock is held by "
                f"{inspection.holder.describe()}; one workspace admits one writer only"
            )
        if inspection.state == ACTIVE:
            return f"INSTANCE_ALREADY_RUNNING: app.lock {inspection.detail or 'is initialising'}"
        return f"WORKSPACE_LEASE_UNUSABLE: app.lock {inspection.detail or inspection.state}"
