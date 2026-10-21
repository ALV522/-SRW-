"""Task and role-template endpoints after extraction (ADR-0002 R2, third slice).

Transport-level regressions for the ten routes moved into
`api/routes/operations.py`. Task state transitions and template CRUD are their
own business rules and live in the Core; this file pins the HTTP contract, the
audit-free but state-changing task paths, and the ownership of the routes.

`GET /api/v1/dashboard` deliberately stays in the aggregate and is not asserted
here.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.fullworkbench import TaskRecord
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]
OPERATION_PATHS = {
    ("GET", "/api/v1/tasks"),
    ("GET", "/api/v1/tasks/{task_id:str}"),
    ("POST", "/api/v1/tasks/{task_id:str}/retry"),
    ("POST", "/api/v1/tasks/{task_id:str}/cancel"),
    ("GET", "/api/v1/templates"),
    ("POST", "/api/v1/templates"),
    ("DELETE", "/api/v1/templates/{template_id:str}"),
    ("PATCH", "/api/v1/templates/{template_id:str}"),
    ("POST", "/api/v1/projects/{project_id:str}/templates/from-current"),
    ("POST", "/api/v1/templates/{template_id:str}/apply/{project_id:str}"),
}


class OperationRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-operation-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(url)
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as session:
            session.add(TaskRecord(task_type="ocr", status="queued"))
            session.add(TaskRecord(task_type="asr", status="succeeded"))
        self.app = create_v1_app(
            url,
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def task_ids(self):
        listing = self.client.get("/api/v1/tasks").json()
        return {row["type"]: row["task_id"] for row in listing["tasks"]}

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in OPERATION_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), OPERATION_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.operations"})

    def test_task_listing_filters_and_paginates(self):
        listing = self.client.get("/api/v1/tasks").json()
        self.assertEqual(listing["total"], 2)
        self.assertEqual(listing["limit"], 50)
        self.assertEqual(listing["offset"], 0)

        filtered = self.client.get("/api/v1/tasks", params={"status": "queued"}).json()
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["tasks"][0]["type"], "ocr")

        typed = self.client.get("/api/v1/tasks", params={"type": "asr"}).json()
        self.assertEqual([row["type"] for row in typed["tasks"]], ["asr"])

        self.assertEqual(self.client.get("/api/v1/tasks", params={"limit": "nope"}).status_code, 409)

    def test_task_detail_and_cancel_then_retry_rules(self):
        task_id = self.task_ids()["ocr"]
        detail = self.client.get(f"/api/v1/tasks/{task_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["task_id"], task_id)

        cancelled = self.client.post(f"/api/v1/tasks/{task_id}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")

        # A cancelled task is terminal: retry must be refused by the Core.
        refused = self.client.post(f"/api/v1/tasks/{task_id}/retry")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("cancelled", refused.json()["detail"])

        # Cancelling an already-succeeded task is a no-op that reports the truth.
        done_id = self.task_ids()["asr"]
        noop = self.client.post(f"/api/v1/tasks/{done_id}/cancel")
        self.assertEqual(noop.status_code, 200)
        self.assertEqual(noop.json()["status"], "succeeded")

        self.assertEqual(self.client.get("/api/v1/tasks/missing").status_code, 404)

    def test_retry_requeues_a_failed_task(self):
        with self.factory.begin() as session:
            task = TaskRecord(task_type="ocr", status="failed", error_code="boom", error_message="synthetic")
            session.add(task)
            session.flush()
            task_id = task.id

        retried = self.client.post(f"/api/v1/tasks/{task_id}/retry")
        self.assertEqual(retried.status_code, 200, retried.text)
        payload = retried.json()
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["job_id"], "retry must attach a job for the worker")

    def test_template_crud_round_trip(self):
        created = self.client.post("/api/v1/templates",
                                   json={"name": "Synthetic template", "role_title": "Backend",
                                         "payload": {"criteria": [{"name": "c1"}]}})
        self.assertEqual(created.status_code, 200, created.text)
        template_id = created.json()["template_id"]

        listed = self.client.get("/api/v1/templates").json()["templates"]
        self.assertEqual([row["template_id"] for row in listed], [template_id])
        self.assertEqual(listed[0]["payload"], {"criteria": [{"name": "c1"}]})

        renamed = self.client.patch(f"/api/v1/templates/{template_id}", json={"name": "Renamed"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["name"], "Renamed")

        bad_payload = self.client.patch(f"/api/v1/templates/{template_id}", json={"payload": []})
        self.assertEqual(bad_payload.status_code, 409)

        deleted = self.client.delete(f"/api/v1/templates/{template_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.get("/api/v1/templates").json()["templates"], [])

    def test_template_validation_and_unknown_ids(self):
        self.assertEqual(self.client.post("/api/v1/templates", json={}).status_code, 409)
        self.assertEqual(self.client.patch("/api/v1/templates/missing", json={"name": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/templates/missing").status_code, 404)
        self.assertEqual(
            self.client.post("/api/v1/templates/missing/apply/project-missing", json={}).status_code, 404)
        self.assertEqual(
            self.client.post("/api/v1/projects/project-missing/templates/from-current",
                             json={"name": "x"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
