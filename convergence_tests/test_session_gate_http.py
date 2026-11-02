"""#43 M3A: the opt-in business session gate, observed only through HTTP.

Migrated from the closed #148 test-only contract: every case asserts a status
code, a response body and unchanged SQLite rows. No middleware internals are
named, so the gate may sit anywhere in the stack. Raw ASGI is used where a
``TestClient`` cannot express the attack: two ``Cookie`` headers, two CSRF
headers, a percent-encoded credential in the query string.

The credential model is the M3A one: an HttpOnly business session cookie minted
only by a single-use pairing code, plus a same-origin CSRF token. The old
single-token ``X-SRW-Session`` header is deliberately *not* a business
credential here; it remains the Host lifecycle secret on its own route.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.business_session_gateway import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER,
    PAIRING_PATH,
    LOGOUT_PATH,
    BusinessSessionGateway,
)
from srw.supervisor.session_registry import SessionRegistry

ROOT = Path(__file__).resolve().parents[1]
ENFORCE_ENV = "RECRUITMENT_SESSION_ENFORCE"
TOKEN_ENV = "RECRUITMENT_SESSION_TOKEN"
LIFECYCLE_SECRET = "synthetic-lifecycle-secret-not-a-business-token"
ORIGIN = "http://testserver"


def asgi_request(app, *, method: str, path: str, headers: list[tuple[bytes, bytes]],
                 body: bytes = b"", query: bytes = b"") -> tuple[int, bytes]:
    """Send one raw ASGI request so duplicate headers survive unchanged."""
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": path, "raw_path": path.encode("latin1"), "query_string": query,
        "root_path": "", "headers": headers,
        "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 54321),
    }
    sent: list[dict] = []
    delivered = False

    async def receive() -> dict:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, payload


class BusinessSessionGateHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="srw-m3a-", ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.database = self.data / "srw_v1.db"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self._saved = {name: os.environ.get(name) for name in (ENFORCE_ENV, TOKEN_ENV)}
        self.addCleanup(self._restore_env)
        self.app = self._build_app(enforce=True)
        self.client = self.enterContext(TestClient(self.app))
        self.gateway: BusinessSessionGateway = self.app.state.business_gateway
        self.business = self._pair(self.client)

    # ------------------------------------------------------------- fixtures
    def _restore_env(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _build_app(self, *, enforce: bool):
        if enforce:
            os.environ[ENFORCE_ENV] = "1"
            os.environ[TOKEN_ENV] = LIFECYCLE_SECRET
        else:
            os.environ.pop(ENFORCE_ENV, None)
            os.environ.pop(TOKEN_ENV, None)
        return create_v1_app(
            f"sqlite+pysqlite:///{self.database.as_posix()}",
            data_dir=self.data, knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def _pair(self, client: TestClient) -> dict:
        code = self.gateway.issue_pairing_code()
        response = client.post(PAIRING_PATH, json={"code": code})
        self.assertEqual(response.status_code, 200, response.text)
        # The token must never appear in the JSON body; only the CSRF value may.
        self.assertNotIn("srw1.", response.text)
        csrf = client.cookies.get(CSRF_COOKIE_NAME)
        self.assertTrue(csrf)
        return {"X-SRW-CSRF": csrf, "origin": ORIGIN}

    def _count(self, table: str) -> int:
        with sqlite3.connect(self.database) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def _audit_count(self) -> int:
        return self._count("audit_event")

    # ------------------------------------------------------- anonymous (N1-N4)
    def test_anonymous_reads_of_business_surfaces_are_rejected(self):
        self.client.cookies.clear()
        for path in ("/api/v1/info", "/api/v1/runtime/info", "/api/v1/projects",
                     "/api/v1/workbench", "/api/v1/system/backups"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertNotIn("instance_id", response.text)

    def test_anonymous_write_is_rejected_without_side_effects(self):
        self.client.cookies.clear()
        projects, audits = self._count("project"), self._audit_count()
        response = self.client.post("/api/v1/projects",
                                    json={"title": "anonymous", "role_title": "Analyst"},
                                    headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual((self._count("project"), self._audit_count()), (projects, audits))

    def test_unknown_and_foreign_session_cookies_are_rejected(self):
        other = BusinessSessionGateway()  # a different Core instance
        foreign_token, _ = other.pair(other.issue_pairing_code())
        for token in ("srw1.badtag.deadbeef", foreign_token, "not-a-token"):
            with self.subTest(token=token[:14]):
                self.client.cookies.clear()
                self.client.cookies.set(COOKIE_NAME, token)
                response = self.client.get("/api/v1/projects")
                self.assertEqual(response.status_code, 401, response.text)

    # ----------------------------------------------------------- origin/CSRF
    def test_cross_site_metadata_is_rejected_even_with_a_valid_cookie(self):
        for origin in ("http://evil.example", "null", ORIGIN.replace("testserver", "evil")):
            with self.subTest(origin=origin):
                response = self.client.post(
                    "/api/v1/projects", json={"title": "cross", "role_title": "x"},
                    headers={**self.business, "origin": origin})
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self._count("project"), 0)

    def test_missing_or_wrong_csrf_is_rejected(self):
        cases = {
            "missing": {"origin": ORIGIN},
            "wrong": {**self.business, "X-SRW-CSRF": "wrong-value"},
        }
        for label, headers in cases.items():
            with self.subTest(label=label):
                response = self.client.post(
                    "/api/v1/projects", json={"title": label, "role_title": "x"}, headers=headers)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self._count("project"), 0)

    # --------------------------------------------------- credentials in URL
    def test_credential_in_the_query_is_refused_even_with_a_valid_cookie(self):
        for query in ("session_token=abc", "x-srw-session=abc", "session=abc",
                      "session%5Ftoken=abc", "X-SRW-Session=abc"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/v1/projects?{query}")
                self.assertIn(response.status_code, (400, 401), response.text)

    # ------------------------------------------------- raw ASGI duplicates
    def test_duplicate_cookie_headers_are_rejected(self):
        cookie = f"{COOKIE_NAME}={self.client.cookies.get(COOKIE_NAME)}"
        for headers in (
            [(b"host", b"testserver"), (b"cookie", cookie.encode()), (b"cookie", cookie.encode())],
            [(b"host", b"testserver"), (b"cookie", cookie.encode()),
             (b"cookie", b"srw_business_session=srw1.other.deadbeef")],
        ):
            with self.subTest(headers=len(headers)):
                status, _ = asgi_request(self.app, method="GET", path="/api/v1/projects",
                                         headers=headers)
                self.assertEqual(status, 400)

    def test_duplicate_csrf_headers_are_rejected(self):
        csrf = self.business["X-SRW-CSRF"].encode()
        cookie = f"{COOKIE_NAME}={self.client.cookies.get(COOKIE_NAME)}".encode()
        body = json.dumps({"title": "dup", "role_title": "x"}).encode()
        status, _ = asgi_request(
            self.app, method="POST", path="/api/v1/projects", body=body,
            headers=[(b"host", b"testserver"), (b"cookie", cookie), (b"origin", ORIGIN.encode()),
                     (b"content-type", b"application/json"),
                     (CSRF_HEADER.encode(), csrf), (CSRF_HEADER.encode(), csrf)])
        self.assertEqual(status, 403)
        self.assertEqual(self._count("project"), 0)

    # ------------------------------------------------------------- positive
    def test_valid_cookie_and_csrf_read_and_write(self):
        self.assertEqual(self.client.get("/api/v1/info").status_code, 200)
        info = self.client.get("/api/v1/runtime/info")
        self.assertEqual(info.status_code, 200, info.text)
        self.assertNotIn("srw1.", info.text, "a token must never be echoed back")
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        created = self.client.post("/api/v1/projects",
                                   json={"title": "paired", "role_title": "Analyst"},
                                   headers=self.business)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(self._count("project"), 1)
        # Project creation does not emit an audit event in this product, so the
        # zero-side-effect cases above assert the audit row count *unchanged*
        # rather than expecting one here.

    # ------------------------------------------------------------- lifecycle
    def test_business_cookie_cannot_shut_the_core_down(self):
        response = self.client.post("/api/v1/runtime/shutdown", headers=self.business)
        self.assertIn(response.status_code, (401, 403), response.text)
        self.assertIsNone(self.app.state.shutdown_callback,
                          "a refused shutdown must not select the shutdown callback")

    def test_lifecycle_secret_still_works_without_a_business_cookie(self):
        self.client.cookies.clear()
        seen = []
        self.app.state.shutdown_callback = lambda: seen.append(True)
        response = self.client.post("/api/v1/runtime/shutdown",
                                    headers={"X-SRW-Session": LIFECYCLE_SECRET})
        # The route answers 202 {"status": "shutting_down"} for the Host carrier.
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(seen, [True])

    # ---------------------------------------------------------- invalidation
    def test_logout_revokes_and_the_cookie_stops_working(self):
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        logout = self.client.post(LOGOUT_PATH, headers=self.business)
        self.assertEqual(logout.status_code, 200, logout.text)
        self.assertIn(self.client.get("/api/v1/projects").status_code, (401, 403))

    def test_expired_session_is_rejected_at_http_level(self):
        now = [1000.0]
        self.gateway._registry = SessionRegistry(clock=lambda: now[0], ttl_seconds=30)
        self.client.cookies.clear()
        self._pair(self.client)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        now[0] += 31
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 401)

    def test_cookie_from_a_previous_core_instance_is_rejected(self):
        token = self.client.cookies.get(COOKIE_NAME)
        self.client.cookies.clear()
        # A fresh app is a restarted Core: same database, new instance tag.
        restarted = self._build_app(enforce=True)
        with TestClient(restarted) as client:
            client.cookies.set(COOKIE_NAME, token)
            self.assertEqual(client.get("/api/v1/projects").status_code, 401)

    # --------------------------------------------------------------- pairing
    def test_pairing_code_is_single_use_and_never_echoed(self):
        code = self.gateway.issue_pairing_code()
        first = self.client.post(PAIRING_PATH, json={"code": code})
        self.assertEqual(first.status_code, 200)
        self.assertNotIn(code, first.text)
        self.assertNotIn("srw1.", first.text)
        reuse = self.client.post(PAIRING_PATH, json={"code": code})
        self.assertEqual(reuse.status_code, 401)
        wrong = self.client.post(PAIRING_PATH, json={"code": "not-the-code"})
        self.assertEqual(wrong.status_code, 401)
        # A wrong shape must not be accepted either.
        for payload in ({"token": code}, {"code": code, "extra": 1}, {}):
            with self.subTest(payload=sorted(payload)):
                self.assertEqual(self.client.post(PAIRING_PATH, json=payload).status_code, 401)

    def test_oversized_pairing_body_is_refused(self):
        response = self.client.post(PAIRING_PATH, json={"code": "x" * 2000})
        self.assertEqual(response.status_code, 413)

    # -------------------------------------------- R1: hostile pairing payloads
    def test_non_ascii_pairing_bodies_are_refused_without_side_effects(self):
        """Legal JSON may still hold non-ASCII text or a lone surrogate escape.

        ``str.encode('ascii')`` on that text used to raise ``UnicodeEncodeError``
        from an anonymous endpoint, i.e. a 500. It must be a 401 with no session,
        no attempt consumed and no business row written.
        """
        live = self.gateway.issue_pairing_code()
        before = (self._count("project"), self._audit_count(), len(self.gateway.registry))
        bodies = {
            "utf8-chinese": '{"code":"中文"}'.encode("utf-8"),
            "utf8-emoji": '{"code":"😀"}'.encode("utf-8"),
            "utf8-accent": '{"code":"café"}'.encode("utf-8"),
            "lone-surrogate": b'{"code":"\\ud800"}',
            "invalid-utf8": b'{"code":"\xff\xfe"}',
            "not-a-string": b'{"code":12345}',
            "null": b'{"code":null}',
            "array": b"[]",
            "overlong-code": b'{"code":"' + b"x" * 300 + b'"}',
        }
        for label, body in bodies.items():
            with self.subTest(label=label):
                response = self.client.post(PAIRING_PATH, content=body,
                                            headers={"content-type": "application/json"})
                self.assertEqual(response.status_code, 401, response.text)
                self.assertIn("pairing_rejected", response.text)
                self.assertNotIn("Traceback", response.text)
                self.assertNotIn(live, response.text)
                self.assertNotIn("srw1.", response.text)
        self.assertEqual(
            (self._count("project"), self._audit_count(), len(self.gateway.registry)),
            before, "a refused pairing body must not write a row or mint a session")
        # The malformed attempts did not burn the live code either.
        accepted = self.client.post(PAIRING_PATH, json={"code": live})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_non_ascii_csrf_header_is_refused_without_a_500(self):
        """``hmac.compare_digest`` raises on non-ASCII ``str``; refuse instead."""
        cookie = f"{COOKIE_NAME}={self.client.cookies.get(COOKIE_NAME)}".encode()
        body = json.dumps({"title": "non-ascii-csrf", "role_title": "x"}).encode()
        for value in (b"\xfc\xfc", "\u4e2d".encode("utf-8")):
            with self.subTest(value=value):
                status, payload = asgi_request(
                    self.app, method="POST", path="/api/v1/projects", body=body,
                    headers=[(b"host", b"testserver"), (b"cookie", cookie),
                             (b"origin", ORIGIN.encode()),
                             (b"content-type", b"application/json"),
                             (CSRF_HEADER.encode(), value)])
                self.assertEqual(status, 403, payload)
        self.assertEqual(self._count("project"), 0)

    # ------------------------------------------------- default OFF regression
    def test_default_off_keeps_the_credential_free_behaviour(self):
        off_app = self._build_app(enforce=False)
        self.assertIsNone(off_app.state.business_gateway)
        with TestClient(off_app) as client:
            self.assertEqual(client.get("/api/v1/info").status_code, 200)
            self.assertEqual(client.get("/api/v1/projects").status_code, 200)
            created = client.post("/api/v1/projects",
                                  json={"title": "off-mode", "role_title": "Analyst"})
            self.assertEqual(created.status_code, 200, created.text)
            self.assertNotIn(CSRF_COOKIE_NAME, client.cookies)
            self.assertNotIn(COOKIE_NAME, client.cookies)


if __name__ == "__main__":
    unittest.main()
