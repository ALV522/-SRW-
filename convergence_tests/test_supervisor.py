"""Core Supervisor attach protocol and lifecycle (ADR-0003 S1/S5).

Four layers:
1. SupervisorServiceTests - pure lifecycle logic with an injectable clock;
2. SupervisorHttpBoundaryTests - the attach protocol through create_v1_app;
3. SupervisorLeaseTests - the supervisor edition on the shared workspace lease;
4. SupervisorProcessTests - a real detached Supervisor subprocess: attach, serve
   traffic, survive the first carrier's detach, and self-exit after the idle
   grace period (acceptance T5/T7 shape).

No real provider or candidate content is used; workspaces are disposable
temporary directories.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.supervisor.client import SupervisorUnavailable, ensure_supervisor, free_loopback_port
from srw.supervisor.service import (
    InvalidToken,
    SupervisorService,
    SupervisorShuttingDown,
    UnknownAttachment,
)
from srw.workspace_lease import WorkspaceLease, WorkspaceLeaseError, inspect_lease


class _FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SupervisorServiceTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        self.service = SupervisorService(idle_grace_seconds=300.0, attach_timeout_seconds=90.0, clock=self.clock)

    def test_attach_heartbeat_detach_refcount(self):
        first = self.service.attach(carrier="carrier-a", edition="local-web")
        second = self.service.attach(carrier="carrier-b", edition="windows")
        self.assertEqual(self.service.status().attachments, 2)
        self.assertIsNone(self.service.status().idle_deadline)

        status = self.service.heartbeat(first.attach_id, first.token)
        self.assertEqual(status.attachments, 2)

        status = self.service.detach(second.attach_id, second.token)
        self.assertEqual(status.attachments, 1)
        # One attachment still holds the Core: no idle deadline yet.
        self.assertIsNone(status.idle_deadline)
        self.assertFalse(self.service.idle_exit_due())

        status = self.service.detach(first.attach_id, first.token)
        self.assertEqual(status.attachments, 0)
        self.assertIsNotNone(status.idle_deadline)
        self.assertEqual(status.idle_deadline, self.clock.now + 300.0)

    def test_new_attach_cancels_pending_idle_exit(self):
        first = self.service.attach(carrier="carrier-a")
        self.service.detach(first.attach_id, first.token)
        self.assertFalse(self.service.idle_exit_due())

        self.clock.advance(299.0)
        self.assertFalse(self.service.idle_exit_due())
        revived = self.service.attach(carrier="carrier-b")
        self.assertIsNone(self.service.status().idle_deadline)
        self.assertFalse(self.service.idle_exit_due())
        self.service.detach(revived.attach_id, revived.token)

        self.clock.advance(300.0)
        self.assertTrue(self.service.idle_exit_due())

    def test_silent_carrier_is_auto_detached_and_starts_idle_grace(self):
        attachment = self.service.attach(carrier="crashed-carrier")
        self.clock.advance(91.0)
        expired = self.service.expire_stale()
        self.assertEqual(expired, [attachment.attach_id])
        status = self.service.status()
        self.assertEqual(status.attachments, 0)
        self.assertEqual(status.idle_deadline, self.clock.now + 300.0)

    def test_heartbeat_keeps_attachment_alive(self):
        attachment = self.service.attach(carrier="chatty-carrier")
        for _ in range(5):
            self.clock.advance(60.0)
            self.service.heartbeat(attachment.attach_id, attachment.token)
        self.assertEqual(self.service.expire_stale(), [])
        self.assertEqual(self.service.status().attachments, 1)

    def test_unknown_attachment_and_token_mismatch_are_rejected(self):
        attachment = self.service.attach(carrier="carrier-a")
        with self.assertRaises(UnknownAttachment):
            self.service.heartbeat("no-such-attach", attachment.token)
        with self.assertRaises(InvalidToken):
            self.service.heartbeat(attachment.attach_id, "wrong-token")
        with self.assertRaises(InvalidToken):
            self.service.detach(attachment.attach_id, "")

    def test_shutdown_rejects_new_attachments(self):
        self.service.begin_shutdown()
        with self.assertRaises(SupervisorShuttingDown):
            self.service.attach(carrier="late-carrier")
        self.assertTrue(self.service.status().shutting_down)

    def test_attachment_views_never_leak_tokens(self):
        attachment = self.service.attach(carrier="carrier-a")
        views = self.service.attachment_views()
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]["attach_id"], attachment.attach_id)
        self.assertNotIn("token", views[0])


class SupervisorHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.service = SupervisorService(idle_grace_seconds=120.0)
        app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            supervisor_service=self.service,
        )
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        self.client = client

    def test_attach_heartbeat_detach_roundtrip(self):
        response = self.client.post("/api/v1/supervisor/attach", json={"carrier": "boundary-test", "edition": "local-web"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["attach_id"])
        self.assertTrue(body["token"])
        self.assertEqual(body["instance_id"], self.service.instance_id)

        beat = self.client.post("/api/v1/supervisor/heartbeat", json={"attach_id": body["attach_id"], "token": body["token"]})
        self.assertEqual(beat.status_code, 200, beat.text)
        self.assertEqual(beat.json()["attachments"], 1)

        status = self.client.get("/api/v1/supervisor/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["attachments"], 1)
        self.assertEqual(status.json()["attachment_list"][0]["carrier"], "boundary-test")

        detached = self.client.post("/api/v1/supervisor/detach", json={"attach_id": body["attach_id"], "token": body["token"]})
        self.assertEqual(detached.status_code, 200, detached.text)
        self.assertEqual(detached.json()["attachments"], 0)
        self.assertIsNotNone(detached.json()["idle_deadline"])

    def test_bad_token_and_unknown_attachment_are_rejected(self):
        created = self.client.post("/api/v1/supervisor/attach", json={"carrier": "boundary-test"}).json()
        bad_token = self.client.post("/api/v1/supervisor/heartbeat", json={"attach_id": created["attach_id"], "token": "nope"})
        self.assertEqual(bad_token.status_code, 403, bad_token.text)
        unknown = self.client.post("/api/v1/supervisor/detach", json={"attach_id": "ghost", "token": "nope"})
        self.assertEqual(unknown.status_code, 404, unknown.text)

    def test_runtime_info_exposes_supervisor_block(self):
        info = self.client.get("/api/v1/runtime/info")
        self.assertEqual(info.status_code, 200, info.text)
        self.assertIn("supervisor", info.json())
        self.assertEqual(info.json()["supervisor"]["instance_id"], self.service.instance_id)

    def test_runtime_info_without_supervisor_service_has_no_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_v1_app(
                f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}",
                data_dir=root / "data",
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            )
            with TestClient(app) as client:
                info = client.get("/api/v1/runtime/info")
        self.assertEqual(info.status_code, 200, info.text)
        self.assertNotIn("supervisor", info.json())


class SupervisorLeaseTests(unittest.TestCase):
    def test_supervisor_edition_is_a_known_lease_holder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lease = WorkspaceLease(root / "data", edition="supervisor", port=8765)
            lease.acquire()
            try:
                inspection = inspect_lease(root / "data")
                self.assertEqual(inspection.state, "active")
                self.assertEqual(inspection.holder.edition, "supervisor")
                self.assertEqual(inspection.holder.port, 8765)
                # A carrier cannot take the lease while the Supervisor holds it.
                with self.assertRaises(WorkspaceLeaseError) as ctx:
                    WorkspaceLease(root / "data", edition="local-web").acquire()
                self.assertIn("INSTANCE_ALREADY_RUNNING", str(ctx.exception))
            finally:
                lease.release()
            self.assertEqual(inspect_lease(root / "data").state, "absent")


class SupervisorProcessTests(unittest.TestCase):
    """Real detached Supervisor subprocess lifecycle (acceptance T5/T7 shape)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spawned_pid = None
        os.environ["SRW_BACKGROUND_WORKER"] = "0"

    def _attach(self, carrier: str):
        handle = ensure_supervisor(
            self.root,
            carrier=carrier,
            database=self.root / "data" / "srw_v1.db",
            frontend_dist=Path(__file__).resolve().parents[1] / "frontend" / "dist",
            knowledge_root=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
            idle_grace_seconds=6.0,
            spawn_timeout=45.0,
        )
        self.spawned_pid = None  # pid discovery is via the lease below
        return handle

    def test_supervisor_lifecycle_attach_serve_survive_detach_self_exit(self):
        first = self._attach("carrier-a")
        self.assertTrue(first.attach_id)

        # The Core is the Supervisor: lease says so and business traffic works.
        inspection = inspect_lease(self.root / "data")
        self.assertEqual(inspection.state, "active")
        self.assertEqual(inspection.holder.edition, "supervisor")

        import urllib.request

        with urllib.request.urlopen(first.base_url + "/api/v1/runtime/info", timeout=10) as response:
            info = json.loads(response.read().decode("utf-8"))
        self.assertIn("supervisor", info)
        self.assertEqual(info["supervisor"]["instance_id"], first.instance_id)

        # Second carrier attaches to the SAME Supervisor (no re-derive).
        second = ensure_supervisor(
            self.root,
            carrier="carrier-b",
            idle_grace_seconds=6.0,
            spawn_timeout=15.0,
        )
        self.assertFalse(second.spawned)
        self.assertEqual(second.instance_id, first.instance_id)

        # Carrier A closes: the Supervisor must survive for carrier B (T5).
        first.detach()
        time.sleep(1.0)
        inspection = inspect_lease(self.root / "data")
        self.assertEqual(inspection.state, "active", "Supervisor died with the first carrier")
        self.assertEqual(inspection.holder.edition, "supervisor")

        beat = second.heartbeat()
        self.assertEqual(beat["attachments"], 1)

        # Last carrier detaches: the Supervisor self-exits after the grace period.
        second.detach()
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if inspect_lease(self.root / "data").state == "absent":
                break
            time.sleep(0.5)
        self.assertEqual(inspect_lease(self.root / "data").state, "absent", "Supervisor did not self-exit")

    def test_ensure_supervisor_refuses_when_another_carrier_holds_the_lease(self):
        with tempfile.TemporaryDirectory() as other:
            holder = WorkspaceLease(self.root / "data", edition="local-web", port=1234)
            holder.acquire()
            self.addCleanup(holder.release)
            with self.assertRaises(SupervisorUnavailable) as ctx:
                ensure_supervisor(self.root, carrier="late-carrier", spawn_timeout=5.0)
            self.assertIn("INSTANCE_ALREADY_RUNNING", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
