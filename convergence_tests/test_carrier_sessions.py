"""One-time carrier sessions: CSRF/Origin enforcement and revocation (ADR-0003 S3).

Three layers: the in-memory SessionRegistry (tokens never leave memory, an
optional persist hook receives secret-free projections), its wiring into the
Supervisor lifecycle (attach issues, detach/silence/exit revoke), and the
ASGI middleware matrix (loopback-only origins, session + CSRF required on
mutations, attach and health exempt).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.supervisor.service import SessionRegistry, SupervisorService


class _FakeClock:
    def __init__(self, now: float = 500.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SessionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        self.persisted: list[tuple[str, dict]] = []
        self.registry = SessionRegistry(
            persist=lambda action, record: self.persisted.append((action, record)), clock=self.clock
        )

    def _issue(self) -> object:
        return self.registry.issue(
            attach_id="attach-1", supervisor_instance_id="sup-1", edition="local-web", carrier="carrier-a"
        )

    def test_issue_validate_and_csrf(self):
        session = self._issue()
        validated = self.registry.validate(session.session_id, session.session_token)
        self.assertIsNotNone(validated)
        self.assertTrue(self.registry.csrf_ok(validated, session.csrf_token))
        self.assertFalse(self.registry.csrf_ok(validated, "wrong"))
        self.assertIsNone(self.registry.validate(session.session_id, "wrong-token"))
        self.assertIsNone(self.registry.validate("ghost", session.session_token))

    def test_persist_hook_receives_secret_free_projections(self):
        session = self._issue()
        action, record = self.persisted[0]
        self.assertEqual(action, "issue")
        self.assertEqual(record["session_id"], session.session_id)
        self.assertNotIn("session_token", record)
        self.assertNotIn("csrf_token", record)

        self.registry.revoke(session.session_id, "detached")
        action, record = self.persisted[-1]
        self.assertEqual(action, "revoke")
        self.assertEqual(record["revoked_reason"], "detached")

    def test_revoked_session_no_longer_validates(self):
        session = self._issue()
        self.assertTrue(self.registry.revoke(session.session_id, "detached"))
        self.assertIsNone(self.registry.validate(session.session_id, session.session_token))
        self.assertFalse(self.registry.revoke(session.session_id, "again"))

    def test_revoke_attach_and_all(self):
        first = self.registry.issue(attach_id="a1", supervisor_instance_id="s", edition="", carrier="c")
        second = self.registry.issue(attach_id="a1", supervisor_instance_id="s", edition="", carrier="c")
        third = self.registry.issue(attach_id="a2", supervisor_instance_id="s", edition="", carrier="c")
        self.assertEqual(self.registry.revoke_attach("a1", "detached"), 2)
        self.assertIsNone(self.registry.validate(first.session_id, first.session_token))
        self.assertIsNone(self.registry.validate(second.session_id, second.session_token))
        self.assertIsNotNone(self.registry.validate(third.session_id, third.session_token))
        self.assertEqual(self.registry.revoke_all("supervisor_exit"), 1)
        self.assertEqual(self.registry.active_views(), [])


class SupervisorSessionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        self.service = SupervisorService(idle_grace_seconds=60.0, attach_timeout_seconds=30.0, clock=self.clock)

    def test_attach_issues_session_detach_revokes_it(self):
        attachment = self.service.attach(carrier="carrier-a", edition="local-web")
        session = attachment.session
        self.assertTrue(session.session_id and session.csrf_token)
        validated = self.service.sessions.validate(session.session_id, session.session_token)
        self.assertIsNotNone(validated)

        self.service.detach(attachment.attach_id, attachment.token)
        self.assertIsNone(self.service.sessions.validate(session.session_id, session.session_token))

    def test_silent_carrier_revokes_its_session(self):
        attachment = self.service.attach(carrier="carrier-a")
        self.clock.advance(31.0)
        self.assertEqual(self.service.expire_stale(), [attachment.attach_id])
        self.assertIsNone(
            self.service.sessions.validate(attachment.session.session_id, attachment.session.session_token)
        )

    def test_shutdown_revokes_every_session(self):
        first = self.service.attach(carrier="carrier-a")
        second = self.service.attach(carrier="carrier-b")
        self.service.begin_shutdown()
        self.assertIsNone(self.service.sessions.validate(first.session.session_id, first.session.session_token))
        self.assertIsNone(self.service.sessions.validate(second.session.session_id, second.session.session_token))


class CarrierSessionMiddlewareTests(unittest.TestCase):
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
            enforce_carrier_sessions=True,
        )
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        self.client = client

    def _attach(self) -> dict:
        response = self.client.post("/api/v1/supervisor/attach", json={"carrier": "mw-test", "edition": "local-web"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _session_headers(self, session: dict) -> dict:
        return {
            "X-SRW-Session": session["session_id"],
            "X-SRW-Token": session["session_token"],
            "X-SRW-CSRF": session["csrf_token"],
        }

    def test_mutation_without_session_is_refused(self):
        response = self.client.post("/api/v1/projects", json={"title": "无会话", "role_title": "分析师"})
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["error"]["code"], "carrier_session_required")

    def test_mutation_with_wrong_csrf_is_refused(self):
        session = self._attach()
        headers = self._session_headers(session)
        headers["X-SRW-CSRF"] = "not-the-token"
        response = self.client.post(
            "/api/v1/projects", json={"title": "错误 CSRF", "role_title": "分析师"}, headers=headers
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"]["code"], "csrf_token_mismatch")

    def test_mutation_with_valid_session_and_csrf_passes(self):
        session = self._attach()
        response = self.client.post(
            "/api/v1/projects",
            json={"title": "会话写入", "role_title": "分析师"},
            headers=self._session_headers(session),
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_non_loopback_origin_is_refused_even_for_reads(self):
        session = self._attach()
        response = self.client.get(
            "/api/v1/projects", headers={**self._session_headers(session), "Origin": "http://evil.example"}
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"]["code"], "origin_not_allowed")

    def test_reads_and_attach_and_health_are_exempt(self):
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        self.assertEqual(self._attach()["session_id"] != "", True)

    def test_detached_session_can_no_longer_write(self):
        session = self._attach()
        self.client.post(
            "/api/v1/supervisor/detach", json={"attach_id": session["attach_id"], "token": session["token"]}
        )
        response = self.client.post(
            "/api/v1/projects", json={"title": "已撤销", "role_title": "分析师"}, headers=self._session_headers(session)
        )
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
