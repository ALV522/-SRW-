"""Restore acceptance across REAL Core process shutdown/restart (synthetic data).

No mocked routes, production Knowledge, browser UI or WPF GUI. The test
exercises the standalone Core startup path that owns the workspace lease.
"""
from __future__ import annotations

import hashlib
import json
import os
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
        try:
            result = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.fail("Core failed to stop gracefully before lease-release validation")
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
