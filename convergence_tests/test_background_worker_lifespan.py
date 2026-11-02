"""#41 P0: the application lifespan itself must start and stop the task worker.

Before this fix ``install_full_workbench_routes`` registered the worker with
``app.add_event_handler("startup", ...)`` while ``create_v1_app`` supplies an
explicit ``lifespan`` context. Starlette 0.52 ignores ``on_startup`` in that
case, so ``SRW_BACKGROUND_WORKER=1`` was dead code: a queued task stayed
``queued`` forever in both carriers.

These cases go through the real TestClient lifespan, the real HTTP queueing
endpoint and the real SQLite ``task_record`` row. They never call
``app.state.srw_run_worker_once`` - a manual call would hide exactly the defect
this file exists to pin down.
"""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
WORKER_ENV = "SRW_BACKGROUND_WORKER"
SAMPLE_TEXT = b"five years of python backend work, sqlite and http apis"


class BackgroundWorkerLifespanTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="srw-worker-life-",
                                                ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.database = self.data / "srw_v1.db"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self._saved = os.environ.get(WORKER_ENV)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._saved is None:
            os.environ.pop(WORKER_ENV, None)
        else:
            os.environ[WORKER_ENV] = self._saved

    def _build_app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{self.database.as_posix()}",
            data_dir=self.data, knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def _queue_extraction(self, client: TestClient) -> str:
        project = client.post("/api/v1/projects",
                              json={"title": "worker-life", "role_title": "Engineer"})
        self.assertEqual(project.status_code, 200, project.text)
        candidate = client.post(
            f"/api/v1/projects/{project.json()['project_id']}/candidates",
            json={"display_name": "worker-life"})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        candidate_id = candidate.json()["candidate_id"]
        ingested = client.post(
            f"/api/v1/candidates/{candidate_id}/files",
            json={"filename": "note.txt", "media_type": "text/plain",
                  "base64": base64.b64encode(SAMPLE_TEXT).decode("ascii")})
        self.assertEqual(ingested.status_code, 200, ingested.text)
        queued = client.post(f"/api/v1/candidates/{candidate_id}/evidence/extract-task",
                             json={"source_id": ingested.json()["source_id"]})
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["task_status"], "queued")
        return queued.json()["task_id"]

    def _task(self, task_id: str) -> tuple[str, int] | None:
        if not self.database.exists():
            return None
        connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT status, attempt_count FROM task_record WHERE id = ?",
                (task_id,)).fetchone()
        finally:
            connection.close()
        return (str(row[0]), int(row[1])) if row else None

    def _wait_until(self, task_id: str, predicate, timeout: float = 15.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self._task(task_id)
            if last is not None and predicate(last[0]):
                return last
            time.sleep(0.1)
        return last

    def _live_workers(self) -> list[threading.Thread]:
        return [t for t in threading.enumerate() if t.name == "srw-task-worker" and t.is_alive()]

    def test_enabled_worker_drains_the_queue_without_a_manual_call(self):
        os.environ[WORKER_ENV] = "1"
        app = self._build_app()
        with TestClient(app) as client:
            task_id = self._queue_extraction(client)
            status, attempts = self._wait_until(
                task_id, lambda s: s not in ("queued", "running"))
            # No provider is configured in this workspace: waiting_provider is
            # the correct degradation, and it proves the worker actually ran.
            self.assertEqual(status, "waiting_provider",
                             f"task stayed {status!r}; the worker never picked it up")
            self.assertGreaterEqual(attempts, 1)
            self.assertTrue(getattr(app.state, "srw_worker_thread", None) is not None)
        self.assertFalse(app.state.srw_worker_thread.is_alive(),
                         "the worker must stop before the lifespan returns")

    def test_disabled_worker_never_starts_and_leaves_the_task_queued(self):
        os.environ[WORKER_ENV] = "0"
        app = self._build_app()
        with TestClient(app) as client:
            task_id = self._queue_extraction(client)
            time.sleep(1.5)
            self.assertEqual(self._task(task_id), ("queued", 0))
            self.assertFalse(getattr(app.state, "srw_worker_thread", None) is not None)
        self.assertEqual(self._live_workers(), [])

    def test_repeated_lifespan_does_not_duplicate_the_worker(self):
        os.environ[WORKER_ENV] = "1"
        app = self._build_app()
        for cycle in (1, 2):
            with TestClient(app):
                self.assertEqual(len(self._live_workers()), 1,
                                 f"cycle {cycle} must have exactly one live worker")
                self.assertTrue(app.state.srw_worker_thread.is_alive())
            self.assertFalse(app.state.srw_worker_thread.is_alive())
            self.assertEqual(self._live_workers(), [],
                             f"cycle {cycle} left a worker thread behind")

    def test_shutdown_joins_the_worker_and_releases_the_database(self):
        os.environ[WORKER_ENV] = "1"
        app = self._build_app()
        with TestClient(app) as client:
            self._queue_extraction(client)
            self.assertTrue(app.state.srw_worker_thread.is_alive())
        self.assertFalse(app.state.srw_worker_thread.is_alive())
        self.assertTrue(getattr(app.state, "srw_worker_shutdown_complete", False),
                        "shutdown must report whether the worker really stopped")
        moved = self.database.with_name("srw_v1.moved.db")
        self.database.rename(moved)  # Windows refuses while a handle is open
        moved.rename(self.database)


if __name__ == "__main__":
    unittest.main()
