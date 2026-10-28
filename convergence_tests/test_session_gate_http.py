"""Approved test-only contract for the opt-in business session gate (#43).

These cases are **deliberately RED** on this tree. ``srw.supervisor.session_policy``
exists and is unit-tested (#145), but nothing consumes it yet, so an environment
with ``RECRUITMENT_SESSION_ENFORCE=1`` still serves every request below. Track A
approved these seven negative outcomes and the positive controls in
https://github.com/ALV522/-SRW-/issues/43#issuecomment-6415909730 and will take
one atomic RED -> GREEN integration PR for the middleware; this file must not be
merged on its own as "the gate works".

What is asserted is only what an operator can observe: HTTP status, response body
and unchanged SQLite rows. No middleware internals are named, so the eventual
implementation is free to sit anywhere in the stack.

The raw-ASGI cases exist because ``TestClient`` builds a header dict: a duplicate
``X-SRW-Session`` cannot be expressed through it, and a credential must never be
resolved by silently picking one of two contradictory values.
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
from srw.modules.fullworkbench import create_backup

ROOT = Path(__file__).resolve().parents[1]
SESSION_HEADER = "X-SRW-Session"
TOKEN = "synthetic-session-token-not-a-secret"
# A second value that the Core is not configured with. It is deliberately NOT
# named "revoked": token rotation/revocation lifecycle is Track A's production
# contract, and this fixture can only prove that an unconfigured value is refused.
OTHER_INVALID = "synthetic-other-token-not-a-secret"

ENFORCE_ENV = "RECRUITMENT_SESSION_ENFORCE"
TOKEN_ENV = "RECRUITMENT_SESSION_TOKEN"


class SessionGateHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(
            prefix="srw-session-gate-", ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.database = self.data / "srw_v1.db"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self._saved_env = {name: os.environ.get(name) for name in (ENFORCE_ENV, TOKEN_ENV)}
        self.addCleanup(self._restore_env)
        self.app = self._build_app(enforce=True)
        self.client = self.enterContext(TestClient(self.app))
        # A real project, created through the public API with a valid credential:
        # every negative case needs a genuine target that would otherwise succeed.
        created = self.client.post(
            "/api/v1/projects",
            json={"title": "Synthetic session gate", "role_title": "Analyst"},
            headers={SESSION_HEADER: TOKEN},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.project_id = created.json()["project_id"]

    # ------------------------------------------------------------- fixtures

    def _restore_env(self) -> None:
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _build_app(self, *, enforce: bool):
        if enforce:
            os.environ[ENFORCE_ENV] = "1"
            os.environ[TOKEN_ENV] = TOKEN
        else:
            os.environ.pop(ENFORCE_ENV, None)
            os.environ.pop(TOKEN_ENV, None)
        return create_v1_app(
            f"sqlite+pysqlite:///{self.database.as_posix()}",
            data_dir=self.data,
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def _count(self, table: str) -> int:
        connection = sqlite3.connect(self.database)
        try:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            connection.close()

    def _snapshot(self) -> dict[str, int]:
        return {table: self._count(table) for table in ("candidate", "project", "audit_event")}

    def _raw(self, *, method: str, target: str, headers: list[tuple[str, str]]) -> tuple[int, str]:
        """Call the ASGI app directly so duplicate/encoded headers stay intact."""

        path, _, query = target.partition("?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query.encode("ascii"),
            "root_path": "",
            "headers": [(name.lower().encode("latin1"), value.encode("latin1"))
                        for name, value in headers],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 54321),
        }
        messages: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, body.decode("utf-8", "replace")

    # ------------------------------------------------- 1. identifying reads

    def test_anonymous_info_is_rejected_without_identity(self) -> None:
        response = self.client.get("/api/v1/info")
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn("instance_id", response.text)
        self.assertNotIn("data_dir_identity", response.text)

    def test_anonymous_runtime_identity_is_rejected(self) -> None:
        for path in ("/api/v1/runtime/info", "/api/v1/runtime/live"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertNotIn("instanceId", response.text)
                self.assertNotIn("sessionId", response.text)
                self.assertNotIn("releaseId", response.text)

    def test_anonymous_backup_listing_is_rejected_without_names_or_bytes(self) -> None:
        backup = create_backup(self.data, self.database)
        response = self.client.get("/api/v1/system/backups")
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn(backup.name, response.text)
        self.assertNotIn("PK\\x03\\x04", response.text)

    # ------------------------------------------------------ 2. write access

    def test_anonymous_write_is_rejected_without_side_effects(self) -> None:
        before = self._snapshot()
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/candidates",
            json={"display_name": "Anonymous candidate must not exist"},
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self._snapshot(), before,
                         "a rejected anonymous write must not create rows or audit events")

    def test_unconfigured_token_is_rejected_without_side_effects(self) -> None:
        # Two unconfigured values, not a revocation test: rotation/revocation
        # semantics belong to the production lifecycle contract, not this fixture.
        for token in ("not-the-token", OTHER_INVALID):
            with self.subTest(token=token):
                before = self._snapshot()
                read = self.client.get(f"/api/v1/projects/{self.project_id}/candidates",
                                       headers={SESSION_HEADER: token})
                self.assertEqual(read.status_code, 401, read.text)
                write = self.client.post(
                    "/api/v1/projects",
                    json={"title": "Rejected by credential", "role_title": "Analyst"},
                    headers={SESSION_HEADER: token},
                )
                self.assertEqual(write.status_code, 401, write.text)
                self.assertEqual(self._snapshot(), before)

    # -------------------------------------------------- 3. origin provenance

    def test_cross_origin_metadata_is_rejected_even_with_valid_token(self) -> None:
        headers = {SESSION_HEADER: TOKEN}
        for site in ("same-site", "cross-site"):
            with self.subTest(site=site, method="GET"):
                response = self.client.get(
                    f"/api/v1/projects/{self.project_id}/candidates",
                    headers={**headers, "Sec-Fetch-Site": site})
                self.assertEqual(response.status_code, 403, response.text)
            with self.subTest(site=site, method="POST"):
                response = self.client.post(
                    "/api/v1/projects",
                    json={"title": "Cross-site write", "role_title": "Analyst"},
                    headers={**headers, "Sec-Fetch-Site": site},
                )
                self.assertEqual(response.status_code, 403, response.text)
        with self.subTest(origin="unlisted"):
            response = self.client.get(
                f"/api/v1/projects/{self.project_id}/candidates",
                headers={**headers, "Origin": "http://evil.example"})
            self.assertEqual(response.status_code, 403, response.text)

    # ----------------------------------------------------- 4. query tokens

    def test_query_token_is_rejected_including_encoded_names(self) -> None:
        cases = (
            f"session_token={TOKEN}",
            f"x-srw-session={TOKEN}",
            f"session%5ftoken={TOKEN}",
            f"x-srw-%252573ession={TOKEN}",
        )
        base = [("host", "testserver")]
        for query in cases:
            with self.subTest(query=query):
                status, body = self._raw(
                    method="GET", target=f"/api/v1/info?{query}", headers=base)
                self.assertEqual(status, 401, body)
                self.assertNotIn("instance_id", body)
                self.assertNotIn("data_dir_identity", body)

    def test_duplicate_session_headers_are_rejected(self) -> None:
        # A Python dict cannot represent two contradictory credentials, so this
        # goes straight to ASGI. Whichever value is "right", the request is ambiguous.
        status, body = self._raw(
            method="GET",
            target=f"/api/v1/projects/{self.project_id}/candidates",
            headers=[("host", "testserver"),
                     (SESSION_HEADER, TOKEN),
                     (SESSION_HEADER, "different-token")],
        )
        self.assertIn(status, (400, 401), body)
        self.assertNotIn("candidate", body.lower())

    def test_duplicate_identical_session_headers_are_rejected(self) -> None:
        # Repeating the same value is still a malformed credential envelope: two
        # headers mean the caller and the Core can disagree about which one counts.
        status, body = self._raw(
            method="GET",
            target=f"/api/v1/projects/{self.project_id}/candidates",
            headers=[("host", "testserver"),
                     (SESSION_HEADER, TOKEN),
                     (SESSION_HEADER, TOKEN)],
        )
        self.assertIn(status, (400, 401), body)
        self.assertNotIn("candidate", body.lower())

    def test_valid_header_does_not_excuse_a_query_credential(self) -> None:
        # A correct header must not launder a credential that is also in the URL:
        # the URL still lands in logs and history, so the request stays refused.
        for query in (f"session_token={TOKEN}", f"x-srw-%252573ession={TOKEN}"):
            with self.subTest(query=query):
                status, body = self._raw(
                    method="GET",
                    target=f"/api/v1/info?{query}",
                    headers=[("host", "testserver"), (SESSION_HEADER, TOKEN)],
                )
                self.assertEqual(status, 401, body)
                self.assertNotIn("instance_id", body)
                self.assertNotIn("data_dir_identity", body)

    # ------------------------------------------------------- 5. GREEN controls

    def test_default_off_keeps_native_originless_behaviour(self) -> None:
        # The Native Host sends no Origin and no token; with the gate absent the
        # request must behave exactly as today.
        app = self._build_app(enforce=False)
        with TestClient(app) as client:
            info = client.get("/api/v1/info")
            self.assertEqual(info.status_code, 200, info.text)
            self.assertIn("instance_id", info.text)
            created = client.post(
                "/api/v1/projects",
                json={"title": "Native write without token", "role_title": "Analyst"})
            self.assertEqual(created.status_code, 200, created.text)

    def test_bootstrap_reads_stay_anonymous_under_enforcement(self) -> None:
        for path in ("/health/live", "/api/v1/runtime/ready"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)

    def test_valid_token_with_same_origin_metadata_is_allowed(self) -> None:
        headers = {SESSION_HEADER: TOKEN, "Sec-Fetch-Site": "same-origin",
                   "Origin": "http://testserver"}
        read = self.client.get(
            f"/api/v1/projects/{self.project_id}/candidates", headers=headers)
        self.assertEqual(read.status_code, 200, read.text)
        write = self.client.post(
            "/api/v1/projects",
            json={"title": "Authorized same-origin", "role_title": "Analyst"},
            headers=headers,
        )
        self.assertEqual(write.status_code, 200, write.text)


if __name__ == "__main__":
    unittest.main()
