"""Carrier-side attach client (ADR-0003 S1/S5).

A carrier (WPF Host, local-web launcher, browser tab) never holds the workspace
lease itself in supervisor mode. It probes the lease: a live supervisor lease
means the Core already runs and the carrier only attaches; anything else means
this carrier derives a detached Supervisor process and then attaches to it. The
derived process outlives the carrier, so closing one carrier never kills the
Core for the others (acceptance T5).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from srw.workspace_lease import inspect_lease

SUPERVISOR_EDITION = "supervisor"
DEFAULT_SPAWN_TIMEOUT_SECONDS = 30.0
_ATTACH_PATH = "/api/v1/supervisor/attach"
_STATUS_PATH = "/api/v1/supervisor/status"
_HEARTBEAT_PATH = "/api/v1/supervisor/heartbeat"
_DETACH_PATH = "/api/v1/supervisor/detach"


class SupervisorUnavailable(RuntimeError):
    """The workspace cannot be served through a Supervisor."""


@dataclass(frozen=True)
class SupervisorHandle:
    base_url: str
    attach_id: str
    token: str
    instance_id: str
    spawned: bool

    def heartbeat(self) -> dict:
        return _post(self.base_url + _HEARTBEAT_PATH, {"attach_id": self.attach_id, "token": self.token})

    def detach(self) -> dict:
        return _post(self.base_url + _DETACH_PATH, {"attach_id": self.attach_id, "token": self.token})

    def __enter__(self) -> "SupervisorHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.detach()
        except SupervisorUnavailable:
            # The Supervisor is gone; nothing to detach from.
            pass


def _post(url: str, payload: dict, timeout: float = 10.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise SupervisorUnavailable(f"{url} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SupervisorUnavailable(f"{url} unreachable: {exc}") from exc


def _get(url: str, timeout: float = 5.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SupervisorUnavailable(f"{url} unreachable: {exc}") from exc


def free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _spawn_detached(
    data_root: Path,
    *,
    port: int,
    database: Path | None,
    frontend_dist: Path | None,
    knowledge_root: Path | None,
    idle_grace_seconds: float,
) -> subprocess.Popen:
    backend_dir = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-m",
        "srw.supervisor.runtime",
        "--data-root",
        str(data_root),
        "--port",
        str(port),
        "--idle-grace-seconds",
        str(idle_grace_seconds),
    ]
    if database is not None:
        command += ["--database", str(database)]
    if frontend_dist is not None:
        command += ["--frontend-dist", str(frontend_dist)]
    if knowledge_root is not None:
        command += ["--knowledge-root", str(knowledge_root)]
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(backend_dir) + (os.pathsep + existing if existing else "")
    kwargs: dict = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _wait_until_ready(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _get(base_url + _STATUS_PATH, timeout=2.0)
            return
        except SupervisorUnavailable:
            time.sleep(0.25)
    raise SupervisorUnavailable(f"supervisor at {base_url} did not become ready within {timeout:.0f}s")


def _attach(base_url: str, *, carrier: str, edition: str) -> SupervisorHandle:
    payload = _post(base_url + _ATTACH_PATH, {"carrier": carrier, "edition": edition})
    return SupervisorHandle(
        base_url=base_url,
        attach_id=str(payload.get("attach_id") or ""),
        token=str(payload.get("token") or ""),
        instance_id=str(payload.get("instance_id") or ""),
        spawned=False,
    )


def ensure_supervisor(
    data_root: Path | str,
    *,
    carrier: str,
    edition: str = "local-web",
    database: Path | None = None,
    frontend_dist: Path | None = None,
    knowledge_root: Path | None = None,
    idle_grace_seconds: float = 300.0,
    spawn_timeout: float = DEFAULT_SPAWN_TIMEOUT_SECONDS,
) -> SupervisorHandle:
    """Attach to the workspace Supervisor, deriving a detached one when absent.

    Raises SupervisorUnavailable when another (non-supervisor) carrier holds the
    workspace lease, preserving today's single-writer semantics.
    """
    root = Path(data_root)
    data_dir = root / "data"
    inspection = inspect_lease(data_dir)
    if inspection.state == "active" and inspection.holder is not None:
        holder = inspection.holder
        if holder.edition != SUPERVISOR_EDITION:
            raise SupervisorUnavailable(
                f"INSTANCE_ALREADY_RUNNING: app.lock is held by {holder.describe()}; "
                "one workspace admits one writer only"
            )
        if holder.port:
            base_url = f"http://127.0.0.1:{holder.port}"
            try:
                _wait_until_ready(base_url, timeout=5.0)
                return _attach(base_url, carrier=carrier, edition=edition)
            except SupervisorUnavailable:
                # Lease says supervisor but nothing answers: treat as crashed and re-derive.
                pass
    elif inspection.state in ("foreign", "corrupt"):
        raise SupervisorUnavailable(f"WORKSPACE_LEASE_UNUSABLE: app.lock {inspection.detail or inspection.state}")

    port = free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    _spawn_detached(
        root,
        port=port,
        database=database,
        frontend_dist=frontend_dist,
        knowledge_root=knowledge_root,
        idle_grace_seconds=idle_grace_seconds,
    )
    _wait_until_ready(base_url, timeout=spawn_timeout)
    handle = _attach(base_url, carrier=carrier, edition=edition)
    return SupervisorHandle(
        base_url=handle.base_url,
        attach_id=handle.attach_id,
        token=handle.token,
        instance_id=handle.instance_id,
        spawned=True,
    )
