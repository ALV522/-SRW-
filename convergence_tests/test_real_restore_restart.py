"""Restore acceptance across REAL Core process shutdown/restart (synthetic data).

No mocked routes, production Knowledge, browser UI or WPF GUI. The test
exercises the standalone Core startup path that owns the workspace lease.

Shutdown timeout diagnosis (#159)
---------------------------------
``stop_server`` waits 15 s for the Core process to exit after
``POST /api/v1/runtime/shutdown`` returned 202. That wait failed once on
Windows (run 40807748969) and the recorded fact was only
``subprocess.TimeoutExpired``, which cannot distinguish "still shutting down"
from "deadlocked". The root cause stays UNKNOWN in #159; this module only makes
the *next* occurrence readable, without reopening the wait or touching Core
shutdown.

The helpers below are pure and deliberately weak: they read plain values (an
elapsed number, a ``poll()`` result, a lease state string, already-bounded raw
stderr bytes) and never touch the process. In particular nothing here calls
``communicate()`` on a Popen that is still running, because that would turn a
diagnostic into a second unbounded wait.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from knowledge_fixture import create_minimal_knowledge_tree
from srw.runtime.backup_truth import validate_backup_archive
from srw.workspace_lease import ABSENT, inspect_lease

ROOT = Path(__file__).resolve().parents[1]

#: How many raw stderr bytes we are willing to look at. Deliberately larger than
#: the output cap: redaction must see whole credentials first, and the byte bound
#: is applied *after* redaction. Applying the bound first can cut a credential in
#: half and leave its tail in the message, and `"/a" -> "<path>/a"` rewriting
#: makes the text grow, so a pre-redaction cap cannot bound the final size.
STDERR_READ_WINDOW_BYTES = 8192
#: Hard cap on what a failure message may carry, measured after redaction.
STDERR_TAIL_BYTES = 2048
STDERR_TAIL_LINES = 20

_REDACTED = "<redacted>"

#: Credential shapes we mint or accept. Replaced before any path rewriting so a
#: token inside a path-shaped string still disappears.
_CREDENTIAL_REWRITES = (
    (re.compile(r"\bsrw1\.[A-Za-z0-9_-]{1,64}\.[0-9a-fA-F]{8,}"), "srw1.<redacted>"),
    (re.compile(r"(?i)\b(bearer)\s+\S+"), r"\1 <redacted>"),
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-srw-session)(\s*[:=]\s*)\S+"),
     r"\1\2" + _REDACTED),
    (re.compile(r"(?i)\b(token|secret|password|passwd|api[_-]?key|access[_-]?key)"
                r"(\s*[:=]\s*)\S+"), r"\1\2" + _REDACTED),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{16,})\b"), _REDACTED),
)

#: ``NAME=value`` lines leak the whole environment one variable at a time.
_ENV_LINE = re.compile(r"(?m)^(\s*)([A-Z][A-Z0-9_]{2,})(\s*=\s*).*$")

#: Host filesystem paths. ``>`` is excluded on the left so an already-collapsed
#: ``<workspace>/...`` or ``<path>/...`` is not rewritten twice.
_WINDOWS_PATH = re.compile(r"(?<![\w:/>])([A-Za-z]:[\\/][^\s\"'<>|,;]*)")
_POSIX_PATH = re.compile(r"(?<![\w:/>])(/[A-Za-z0-9_.\-/]+)")

#: Route prefixes are part of the diagnosis, not a host path.
_ROUTE_PREFIXES = ("/api/", "/health", "/static", "/docs", "/openapi", "/redoc")


def _collapse_path(match: "re.Match[str]") -> str:
    """Keep the basename and a ``:line[:col]`` suffix, drop the directory."""
    raw = match.group(1)
    if raw.startswith(_ROUTE_PREFIXES):
        return raw
    suffix = ""
    located = re.match(r"^(.*?)(:\d+(?::\d+)?)$", raw)
    if located:
        raw, suffix = located.group(1), located.group(2)
    name = re.split(r"[\\/]", raw.rstrip("\\/"))[-1]
    return f"<path>/{name}{suffix}" if name else f"<path>{suffix}"


def _line_aligned_window(data: bytes, window: int) -> bytes:
    """Keep at most ``window`` trailing bytes, starting on a line boundary.

    Starting mid-line is what lets a credential be cut in half, so a partially
    captured first line is dropped entirely rather than half-reported. If the
    window contains no newline at all, the whole line is unrepresentable and
    nothing is kept.
    """
    if len(data) <= window:
        return data
    tail = data[len(data) - window:]
    newline = tail.find(b"\n")
    return b"" if newline < 0 else tail[newline + 1:]


def redact_stderr_text(text: str, *, workspace_root: str | Path | None = None) -> str:
    """Apply every redaction to ``text``. No length policy lives here."""
    if workspace_root is not None:
        root = str(workspace_root)
        for variant in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            if len(variant) > 1:
                text = text.replace(variant, "<workspace>")
    for pattern, replacement in _CREDENTIAL_REWRITES:
        text = pattern.sub(replacement, text)
    text = _ENV_LINE.sub(r"\1\2\3" + _REDACTED, text)
    text = _WINDOWS_PATH.sub(_collapse_path, text)
    text = _POSIX_PATH.sub(_collapse_path, text)
    return text


def bound_tail(text: str, *, limit: int = STDERR_TAIL_BYTES,
               max_lines: int = STDERR_TAIL_LINES) -> str:
    """Cap already-redacted text so no credential can be split by the cap.

    The bound is byte-exact: ``len(result.encode("utf-8")) <= limit`` even after
    path collapsing expands a line, and even when one line alone is longer than
    the whole budget (its tail is kept behind an ellipsis).
    """
    lines = text.splitlines()[-max(1, max_lines):]
    kept: list[str] = []
    used = 0
    for line in reversed(lines):
        cost = len(line.encode("utf-8")) + (1 if kept else 0)
        if used + cost <= limit:
            kept.append(line)
            used += cost
            continue
        if not kept:  # one line longer than the budget: keep its tail
            ellipsis = "…"
            room = limit - len(ellipsis.encode("utf-8"))
            if room > 0:
                tail = line.encode("utf-8")[-room:].decode("utf-8", "ignore")
                kept.append(ellipsis + tail)
        break
    return "\n".join(reversed(kept))


def redact_stderr_tail(raw: bytes | str, *, workspace_root: str | Path | None = None,
                       limit: int = STDERR_TAIL_BYTES,
                       max_lines: int = STDERR_TAIL_LINES) -> str:
    """Window, redact, then bound — in that order. Never raises on odd input."""
    data = raw.encode("utf-8", "replace") if isinstance(raw, str) else bytes(raw or b"")
    text = _line_aligned_window(data, STDERR_READ_WINDOW_BYTES).decode("utf-8", "replace")
    return bound_tail(redact_stderr_text(text, workspace_root=workspace_root),
                      limit=limit, max_lines=max_lines)


def read_stderr_tail(path: str | Path, *, workspace_root: str | Path | None = None,
                     window: int = STDERR_READ_WINDOW_BYTES,
                     limit: int = STDERR_TAIL_BYTES) -> str:
    """Read a bounded, line-aligned window through a *separate* handle.

    The Popen keeps its own write handle; reading by path never waits on the
    child and cannot consume its output.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - window))
            raw = handle.read(window)
    except OSError as exc:
        return f"unavailable:{type(exc).__name__}"
    if size > window:
        # We joined the stream mid-line; that partial line is dropped whole so a
        # credential can never survive as a suffix.
        newline = raw.find(b"\n")
        raw = b"" if newline < 0 else raw[newline + 1:]
    return redact_stderr_tail(raw, workspace_root=workspace_root, limit=limit)


def safe_lease_state(data_dir: str | Path, *, inspection=None) -> str:
    """Lease state as an enumerable string; a broken inspection is named, not raised."""
    inspect = inspection if inspection is not None else inspect_lease
    try:
        return str(inspect(data_dir).state)
    except Exception as exc:  # a diagnostic must never replace the real failure
        return f"unavailable:{type(exc).__name__}"


def describe_shutdown_timeout(*, elapsed_seconds: float, returncode: int | None,
                              lease_state: str, stderr_tail: str) -> str:
    """Render the bounded facts a future shutdown timeout needs to be judgeable."""
    try:
        elapsed = float(elapsed_seconds)
        rendered_elapsed = f"{elapsed:.3f}"
    except (TypeError, ValueError):
        rendered_elapsed = "unavailable"
    process = "alive" if returncode is None else f"exited({returncode})"
    tail = stderr_tail if isinstance(stderr_tail, str) else str(stderr_tail)
    if not tail.strip():
        tail = "<empty>"
    indented = "\n".join("    " + line for line in tail.splitlines())
    return (
        "Core did not exit within the bounded shutdown window (#159)\n"
        f"  elapsed_seconds={rendered_elapsed}\n"
        f"  process={process}\n"
        f"  lease={lease_state}\n"
        "  stderr_tail:\n"
        f"{indented}"
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RealProcessRestoreAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-process-restore-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = dict(os.environ)
        self.env.update({
            "RECRUITMENT_DATA_DIR": str(self.data),
            "RECRUITMENT_FRONTEND_DIST": str(ROOT / "frontend" / "dist"),
            "RECRUITMENT_KNOWLEDGE_DIR": str(knowledge),
            "PYTHONPATH": os.pathsep.join((str(ROOT / "backend"), str(ROOT / "scripts"))),
        })
        self.processes: list[subprocess.Popen] = []
        self.addCleanup(self.stop_any_processes)
        self.stderr = (self.root / "backend.stderr.log").open("w+b")
        self.addCleanup(self.stderr.close)

    def stop_any_processes(self):
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=5)

    def make_process(self) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "scripts" / "run_local.py"),
             "--host", "127.0.0.1", "--port", str(self.port),
             "--edition", "web", "--workspace-lock", "backend"],
            cwd=ROOT, env=self.env, stdout=subprocess.DEVNULL,
            stderr=self.stderr,
        )
        self.processes.append(proc)
        return proc

    def start_server(self) -> subprocess.Popen:
        proc = self.make_process()
        for _ in range(120):
            if proc.poll() is not None:
                self.fail(f"Core failed early, returncode={proc.returncode}")
            try:
                with urllib.request.urlopen(self.base + "/health/ready", timeout=.4) as ready:
                    if ready.status == 200:
                        return proc
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.1)
        self.fail("Core did not become ready after a bounded startup window")

    def api(self, method: str, path: str, payload: dict | None = None) -> dict:
        raw = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=raw, method=method,
            headers={"Content-Type": "application/json"} if payload is not None else {},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            self.assertEqual(response.status, 202 if path == "/api/v1/runtime/shutdown" else 200)
            return json.loads(response.read())

    def stop_server(self, proc: subprocess.Popen) -> None:
        self.api("POST", "/api/v1/runtime/shutdown", {})
        started = time.monotonic()
        try:
            result = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            # Sample *before* failing: the four original assertions stay exactly
            # as they were, and the extra facts are bounded and redacted.
            self.fail(describe_shutdown_timeout(
                elapsed_seconds=time.monotonic() - started,
                returncode=proc.poll(),
                lease_state=safe_lease_state(self.data),
                stderr_tail=read_stderr_tail(self.stderr.name, workspace_root=self.root),
            ))
        self.assertEqual(result, 0)
        self.assertEqual(inspect_lease(self.data).state, ABSENT)

    def make_project(self, name: str) -> str:
        result = self.api("POST", "/api/v1/projects", {
            "title": name, "role_title": "Synthetic analyst",
            "brief_summary": "Disposable restart-only acceptance",
        })
        return result["project_id"]

    def live_ids(self) -> set[str]:
        return {row["project_id"] for row in self.api("GET", "/api/v1/projects")["projects"]}

    def test_backup_scheduled_then_tampered_restart_blocked_and_exact_retry_restores(self):
        first = self.start_server()
        retained = self.make_project("synthetic retained project")
        blob = self.data / "blobs" / "source" / "evidence"
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b"original verified evidence")
        name = self.api("POST", "/api/v1/system/backups", {})["filename"]
        archive = self.data / "backups" / name
        original_zip = archive.read_bytes()
        self.assertTrue(validate_backup_archive(archive)["manifest_present"])

        removed_after_restore = self.make_project("synthetic later project")
        blob.write_bytes(b"later evidence must be reverted")
        later_blob = self.data / "blobs" / "later" / "new"
        later_blob.parent.mkdir(parents=True)
        later_blob.write_bytes(b"later source must be removed")
        self.assertEqual(self.live_ids(), {retained, removed_after_restore})
        plan = self.api("POST", f"/api/v1/system/backups/{name}/restore", {})
        self.assertTrue(plan["restart_required"])
        self.assertEqual(plan["sha256"], hashlib.sha256(original_zip).hexdigest())
        marker = self.data / "pending_restore.json"
        self.assertTrue(marker.is_file())
        self.stop_server(first)

        # The archive changes *after* the API approved the plan. Startup must
        # fail closed and may not touch the live database or remove its marker.
        original_db = (self.data / "srw_v1.db").read_bytes()
        archive.write_bytes(original_zip + b"synthetic post-approval tamper")
        denied = self.make_process()
        try:
            status = denied.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.fail("Tampered restore unexpectedly started and kept the Core alive")
        self.assertNotEqual(status, 0)
        self.assertEqual((self.data / "srw_v1.db").read_bytes(), original_db)
        self.assertTrue(marker.is_file())
        self.assertEqual(inspect_lease(self.data).state, ABSENT)

        # Restore the independently retained archive bytes, without weakening
        # manifest/hash rules or rewriting the pending marker. Then retry.
        archive.write_bytes(original_zip)
        recovered = self.start_server()
        self.assertEqual(self.live_ids(), {retained})
        self.assertEqual(blob.read_bytes(), b"original verified evidence")
        self.assertFalse(later_blob.exists())
        self.assertFalse(marker.exists())
        pre_restore = list((self.data / "backups").glob("pre_restore-*.zip"))
        self.assertEqual(len(pre_restore), 1)
        self.assertTrue(validate_backup_archive(pre_restore[0])["manifest_present"])
        self.stop_server(recovered)


if __name__ == "__main__":
    unittest.main()
