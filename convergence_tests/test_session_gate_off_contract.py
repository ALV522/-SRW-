"""#43 conservative contract: the gate is OFF today, and the oracles can prove it.

Scope agreed with Track A: no middleware, no cookie/attach/token wiring, no change
to runtime/info or shutdown, and none of #148's deliberately-RED cases. These tests
only lock what is true on the current main so that the future atomic wiring PR has
to change them on purpose instead of drifting silently:

* D4 - with the flag absent (or any value but the literal "1"), the policy is inert
  and the real app keeps answering business writes without a session header;
* A9/A10 - the existing credential boundary: non-ASCII, control characters and
  over-long values are one fixed 401 rather than an exception or a distinguisher;
* the raw ASGI header shape - duplicate header names survive to ``scope["headers"]``,
  which a dict cannot express. This is the oracle the wiring PR must use; a test
  built on a dict would silently collapse the duplicates it is meant to inspect.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.supervisor.session_policy import (
    ENFORCE_ENV,
    MAX_TOKEN_LENGTH,
    SESSION_HEADER,
    TOKEN_ENV,
    SessionPolicy,
)

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "srw1." + "a" * 40


def decision(policy: SessionPolicy, *, method: str = "POST", path: str = "/api/v1/projects",
             headers: dict[str, str] | None = None):
    return policy.evaluate(method=method, raw_path=path, headers=headers or {})


class DefaultOffCompatibilityTests(unittest.TestCase):
    """D4: only the literal ``1`` may switch the gate on."""

    def test_policy_is_inert_for_every_value_but_the_literal_one(self):
        for environ in ({}, {ENFORCE_ENV: ""}, {ENFORCE_ENV: "0"}, {ENFORCE_ENV: "true"},
                        {ENFORCE_ENV: "yes"}, {ENFORCE_ENV: "02"}, {ENFORCE_ENV: " "}):
            with self.subTest(environ=environ):
                policy = SessionPolicy.from_environ(environ)
                self.assertFalse(policy.enforce)
                result = decision(policy)
                self.assertTrue(result.allowed, result.reason)
                self.assertEqual(result.reason, "enforcement_disabled")

    def test_literal_one_enables_and_then_requires_a_credential(self):
        policy = SessionPolicy.from_environ({ENFORCE_ENV: "1", TOKEN_ENV: TOKEN})
        self.assertTrue(policy.enforce)
        denied = decision(policy)
        self.assertFalse(denied.allowed)
        self.assertEqual((denied.status_code, denied.reason),
                         (401, "session_token_required"))
        allowed = decision(policy, headers={SESSION_HEADER: TOKEN})
        self.assertTrue(allowed.allowed, allowed.reason)

    def test_real_app_still_accepts_a_business_write_without_a_session_header(self):
        # The Windows carrier talks to loopback with no Origin and no token; the
        # default must not break it. Asserted against the real ASGI app, not a stub.
        with tempfile.TemporaryDirectory(prefix="srw-gate-off-") as directory:
            root = Path(directory)
            (root / "data").mkdir(parents=True)
            app = create_v1_app(
                f"sqlite+pysqlite:///{(root / 'data' / 'off.db').as_posix()}",
                data_dir=root / "data",
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                frontend_dist=ROOT / "frontend" / "dist",
            )
            with TestClient(app) as client:
                created = client.post("/api/v1/projects",
                                      json={"title": "Synthetic OFF compat",
                                            "role_title": "Backend"})
                self.assertEqual(created.status_code, 200, created.text)
                info = client.get("/api/v1/runtime/info")
                self.assertEqual(info.status_code, 200, info.text)
                self.assertIn("instanceId", info.json())


class CredentialBoundaryTests(unittest.TestCase):
    """A9/A10: untrusted header text stays a bounded, uniform 401."""

    def enforced(self, token: str = TOKEN) -> SessionPolicy:
        return SessionPolicy(enforce=True, token=token)

    def test_non_ascii_credential_is_denied_as_invalid_not_raised(self):
        result = decision(self.enforced(), headers={SESSION_HEADER: "srw1.密码🔒"})
        self.assertFalse(result.allowed)
        self.assertEqual((result.status_code, result.reason), (401, "session_token_invalid"))

    def test_control_characters_and_spaces_are_denied(self):
        for value in ("srw1.\ttoken", "srw1. token", "srw1.\ntoken", "srw1.\x00token"):
            with self.subTest(value=value[:8]):
                result = decision(self.enforced(), headers={SESSION_HEADER: value})
                self.assertEqual((result.status_code, result.reason),
                                 (401, "session_token_invalid"))

    def test_overlong_credential_is_denied_at_the_length_boundary(self):
        longest = "a" * MAX_TOKEN_LENGTH
        policy = self.enforced(token=longest)
        self.assertTrue(decision(policy, headers={SESSION_HEADER: longest}).allowed)
        too_long = "a" * (MAX_TOKEN_LENGTH + 1)
        result = decision(policy, headers={SESSION_HEADER: too_long})
        self.assertEqual((result.status_code, result.reason), (401, "session_token_invalid"))

    def test_missing_and_wrong_credentials_have_distinct_reasons(self):
        policy = self.enforced()
        missing = decision(policy)
        wrong = decision(policy, headers={SESSION_HEADER: "srw1." + "b" * 40})
        self.assertEqual(missing.reason, "session_token_required")
        self.assertEqual(wrong.reason, "session_token_invalid")

    def test_enforced_without_a_configured_token_fails_closed(self):
        result = decision(SessionPolicy(enforce=True, token=""))
        self.assertEqual((result.status_code, result.reason),
                         (401, "session_token_not_configured"))


class RawHeaderShapeTests(unittest.TestCase):
    """The wiring PR must be able to see duplicate header names, so prove they survive."""

    def test_duplicate_header_names_reach_the_real_asgi_scope(self):
        with tempfile.TemporaryDirectory(prefix="srw-raw-headers-") as directory:
            root = Path(directory)
            (root / "data").mkdir(parents=True)
            app = create_v1_app(
                f"sqlite+pysqlite:///{(root / 'data' / 'raw.db').as_posix()}",
                data_dir=root / "data",
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                frontend_dist=ROOT / "frontend" / "dist",
            )
            captured: dict[str, list[tuple[bytes, bytes]]] = {}

            async def capture(scope, receive, send):
                # A test-side wrapper only: the production app is unchanged.
                if scope["type"] == "http":
                    captured["headers"] = list(scope["headers"])
                await app(scope, receive, send)

            with TestClient(capture) as client:
                response = client.get(
                    "/health/live",
                    headers=[(SESSION_HEADER, "first"), (SESSION_HEADER, "second")],
                )
            self.assertEqual(response.status_code, 200, response.text)
            values = [value for name, value in captured.get("headers", [])
                      if name.lower() == SESSION_HEADER.lower().encode()]
            self.assertEqual(values, [b"first", b"second"],
                             "duplicate header names must survive to scope['headers']")

    def test_a_dict_would_collapse_them_which_is_why_the_raw_test_exists(self):
        collapsed = dict([(SESSION_HEADER, "first"), (SESSION_HEADER, "second")])
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[SESSION_HEADER], "second")


if __name__ == "__main__":
    unittest.main()
