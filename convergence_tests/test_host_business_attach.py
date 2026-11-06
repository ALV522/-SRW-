"""#43 M3B: native Host business Cookie attachment through the real Core HTTP app.

The Host lifecycle credential is never a business session. A trusted desktop
control client may exchange it for an independent revocable Cookie only when
opt-in ON; no browser request, duplicate header or query can do the exchange.
These tests use synthetic SQLite/Knowledge and the actual Starlette gateway.
Windows WPF GUI remains a separate, not-yet-run acceptance.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.business_session_gateway import (
    COOKIE_NAME, CSRF_COOKIE_NAME, HOST_ATTACH_PATH,
)
from test_session_gate_http import asgi_request

ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-host-lifecycle-secret"
ORIGIN = "http://testserver"


class HostBusinessAttachHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-m3b-host-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.db = self.data / "srw_v1.db"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self.app = self._make_app(enforce=True, mode="desktop", edition="windows", token=SECRET)
        self.client = self.enterContext(TestClient(self.app))

    def _make_app(self, *, enforce, mode, edition, token):
        env = {
            "RECRUITMENT_SESSION_ENFORCE": "1" if enforce else "0",
            "RECRUITMENT_RUNTIME_MODE": mode,
            "RECRUITMENT_EDITION": edition,
            "RECRUITMENT_SESSION_TOKEN": token,
        }
        with patch.dict(os.environ, env):
            return create_v1_app(
                f"sqlite+pysqlite:///{self.db.as_posix()}",
                data_dir=self.data, knowledge_dir=self.knowledge,
                frontend_dist=ROOT / "frontend" / "dist",
            )

    def _counts(self):
        with sqlite3.connect(self.db) as db:
            return (
                db.execute("SELECT COUNT(*) FROM project").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0],
            )

    def test_host_attaches_business_cookies_then_webview_can_read_and_write(self):
        # The readiness probe must work before any business session exists.
        self.assertEqual(self.client.get("/api/v1/runtime/ready").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/runtime/info").status_code, 401)
        before = self._counts()
        response = self.client.post(HOST_ATTACH_PATH, headers={"X-SRW-Session": SECRET})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"status": "attached"})
        cookies = response.headers.get_list("set-cookie")
        self.assertEqual(len(cookies), 2)
        self.assertTrue(any(COOKIE_NAME + "=" in c and "HttpOnly" in c
                            and "SameSite=Strict" in c for c in cookies))
        self.assertTrue(any(CSRF_COOKIE_NAME + "=" in c and "SameSite=Strict" in c
                            and "HttpOnly" not in c for c in cookies))
        self.assertNotIn(SECRET, response.text)
        self.assertNotIn("srw1.", response.text)
        self.assertEqual(self._counts(), before, "attachment must not write business/audit")
        csrf = self.client.cookies.get(CSRF_COOKIE_NAME)
        self.assertTrue(csrf)
        self.assertEqual(self.client.get("/api/v1/runtime/info").status_code, 200)
        written = self.client.post("/api/v1/projects",
                                   json={"title": "Synthetic WPF ON", "role_title": "Recruiter"},
                                   headers={"origin": ORIGIN, "X-SRW-CSRF": csrf})
        self.assertEqual(written.status_code, 200, written.text)
        self.assertEqual(self._counts(), (before[0] + 1, before[1] + 1))
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.get("/api/v1/projects").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/runtime/shutdown").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/runtime/business-logout",
                                          headers={"origin": ORIGIN,
                                                   "X-SRW-CSRF": csrf}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/runtime/info").status_code, 401)

    def test_host_attach_denials_do_not_mint_or_write(self):
        gateway = self.app.state.business_gateway
        before = self._counts()
        cases = [
            {},
            {"X-SRW-Session": "incorrect"},
            {"X-SRW-Session": SECRET, "Origin": ORIGIN},
            {"X-SRW-Session": SECRET, "Referer": ORIGIN + "/"},
            {"X-SRW-Session": SECRET, "Cookie": "unused=x"},
            {"X-SRW-Session": SECRET, "Sec-Fetch-Site": "same-origin"},
        ]
        for headers in cases:
            with self.subTest(headers=tuple(headers)):
                response = self.client.post(HOST_ATTACH_PATH, headers=headers)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertNotIn("set-cookie", response.headers)
                self.assertEqual(len(gateway.registry), 0)
                self.assertEqual(self._counts(), before)

        for credentials in ((SECRET.encode(), SECRET.encode()),
                            (b"incorrect", SECRET.encode())):
            status, body = asgi_request(
                self.app, method="POST", path=HOST_ATTACH_PATH,
                headers=[(b"host", b"testserver"),
                         (b"x-srw-session", credentials[0]),
                         (b"x-srw-session", credentials[1])],
            )
            self.assertEqual(status, 403, body)
            self.assertEqual(len(gateway.registry), 0)
        # Even a valid Host header cannot launder a credential in a query URL.
        response = self.client.post(HOST_ATTACH_PATH + "?session_token=synthetic",
                                    headers={"X-SRW-Session": SECRET})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(gateway.registry), 0)
        self.assertEqual(self._counts(), before)

    def test_browser_mode_and_default_off_never_mint_a_host_session(self):
        for enforced, mode, edition, token in (
            (True, "browser", "web", SECRET),
            (True, "desktop", "windows", ""),
            (False, "desktop", "windows", SECRET),
        ):
            with self.subTest(enforced=enforced, mode=mode, token=bool(token)):
                app = self._make_app(enforce=enforced, mode=mode,
                                     edition=edition, token=token)
                with TestClient(app) as client:
                    response = client.post(HOST_ATTACH_PATH,
                                           headers={"X-SRW-Session": SECRET})
                    self.assertIn(response.status_code, (403, 404))
                    self.assertNotIn("set-cookie", response.headers)
                    if not enforced:
                        self.assertEqual(client.get("/api/v1/runtime/info").status_code, 200)
                    else:
                        self.assertEqual(client.get("/api/v1/runtime/info").status_code, 401)


if __name__ == "__main__":
    unittest.main()
