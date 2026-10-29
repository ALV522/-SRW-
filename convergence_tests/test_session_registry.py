"""Contract tests for the effect-free session registry (#43, Track C slice).

Everything here is synthetic: no real credential, workspace, database or HTTP
server is involved. The point is to pin the *deny* behaviour and the absence of
side effects before any production wiring exists.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from srw.supervisor.session_registry import (
    DENY_CLOCK,
    DENY_EXPIRED,
    DENY_FOREIGN_INSTANCE,
    DENY_MALFORMED,
    DENY_SCOPE,
    DENY_UNKNOWN,
    MAX_TOKEN_LENGTH,
    SessionDenied,
    SessionRegistry,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "backend" / "srw" / "supervisor" / "session_registry.py"
)


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class BrokenClock:
    def __call__(self) -> float:
        raise RuntimeError("monotonic clock unavailable")


class IssueAndAuthorizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.registry = SessionRegistry(clock=self.clock, ttl_seconds=60.0)

    def test_issued_token_authorises_its_scope_and_never_exposes_the_secret(self) -> None:
        token, session = self.registry.issue(["read", "write"])
        self.assertEqual(session.scopes, frozenset({"read", "write"}))
        self.assertEqual(token.count("."), 2)
        self.assertTrue(token.startswith("srw1."))
        secret = token.rsplit(".", 1)[1]
        self.assertEqual(len(secret), 64)  # 32 random bytes, hex
        self.assertNotIn(secret, repr(session))
        self.assertNotIn(secret, f"{session}")
        self.assertNotEqual(session.session_id, secret)
        granted = self.registry.authorize(token, "write")
        self.assertEqual(granted.session_id, session.session_id)

    def test_tokens_are_unpredictable_and_never_repeat(self) -> None:
        tokens = {self.registry.issue(["read"])[0] for _ in range(500)}
        self.assertEqual(len(tokens), 500)
        self.assertEqual(len({len(token) for token in tokens}), 1)

    def test_scope_outside_the_grant_is_denied(self) -> None:
        token, _ = self.registry.issue(["read"])
        with self.assertRaises(SessionDenied) as caught:
            self.registry.authorize(token, "write")
        self.assertEqual(caught.exception.reason, DENY_SCOPE)

    def test_empty_scope_names_are_a_configuration_error_not_a_silent_deny(self) -> None:
        for bad in ([""], ["  "], [1], "read"):
            with self.subTest(scopes=bad):
                with self.assertRaises(ValueError):
                    self.registry.issue(bad)

    def test_non_positive_or_nan_ttl_is_refused(self) -> None:
        for bad in (0, -1, float("nan")):
            with self.subTest(ttl=bad):
                with self.assertRaises(ValueError):
                    SessionRegistry(ttl_seconds=bad)


class DenialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.registry = SessionRegistry(clock=self.clock, ttl_seconds=60.0)

    def test_unknown_and_malformed_tokens_are_denied(self) -> None:
        _, session = self.registry.issue(["read"])
        exact = f"srw1.{session.instance_tag}." + "0" * 64
        cases = {
            "empty": "",
            "not-a-string": None,
            "too-long": "srw1." + "a" * MAX_TOKEN_LENGTH,
            "wrong-prefix": "bearer.abc.def",
            "one-part": "srw1",
            "two-part": "srw1.abc",
            "extra-part": "srw1.abc.def.ghi",
            "blank-tag": "srw1.." + "0" * 64,
            "blank-secret": f"srw1.{session.instance_tag}.",
            "well-shaped-but-unknown": exact,
        }
        for label, token in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(SessionDenied) as caught:
                    self.registry.authorize(token, "read")
                self.assertIn(caught.exception.reason, {DENY_MALFORMED, DENY_UNKNOWN})

    def test_revoked_credential_stops_authorising_and_revoke_is_idempotent(self) -> None:
        token, _ = self.registry.issue(["read"])
        self.assertIsNotNone(self.registry.authorize(token, "read"))
        self.assertTrue(self.registry.revoke(token))
        self.assertFalse(self.registry.revoke(token))
        for _ in range(2):  # replay after revoke stays denied, not just once
            with self.assertRaises(SessionDenied) as caught:
                self.registry.authorize(token, "read")
            self.assertEqual(caught.exception.reason, DENY_UNKNOWN)

    def test_revoke_all_drops_every_live_credential(self) -> None:
        tokens = [self.registry.issue(["read"])[0] for _ in range(3)]
        self.assertEqual(self.registry.revoke_all(), 3)
        self.assertEqual(len(self.registry), 0)
        for token in tokens:
            with self.assertRaises(SessionDenied):
                self.registry.authorize(token, "read")

    def test_expiry_is_exact_and_survives_repeated_checks(self) -> None:
        token, _ = self.registry.issue(["read"])
        self.clock.advance(59.999)
        self.assertIsNotNone(self.registry.authorize(token, "read"))
        self.clock.advance(0.001)  # exactly at expires_at: no longer valid
        for _ in range(2):  # verification is a read: the same denial repeats
            with self.assertRaises(SessionDenied) as caught:
                self.registry.authorize(token, "read")
            self.assertEqual(caught.exception.reason, DENY_EXPIRED)
        self.assertEqual(len(self.registry), 1, "authorize must not reclaim")
        self.assertEqual(self.registry.purge_expired(), 1)
        self.assertEqual(len(self.registry), 0)

    def test_purge_expired_only_drops_what_has_expired(self) -> None:
        self.registry.issue(["read"])
        self.clock.advance(30)
        fresh_token, _ = self.registry.issue(["read"])
        self.clock.advance(31)  # first expired (61s), second still live (31s)
        self.assertEqual(self.registry.purge_expired(), 1)
        self.assertIsNotNone(self.registry.authorize(fresh_token, "read"))

    def test_a_restarted_core_rejects_previous_credentials_before_any_lookup(self) -> None:
        token, _ = self.registry.issue(["read"])
        restarted = SessionRegistry(clock=self.clock, ttl_seconds=60.0)
        self.assertNotEqual(restarted.instance_tag, self.registry.instance_tag)
        with self.assertRaises(SessionDenied) as caught:
            restarted.authorize(token, "read")
        self.assertEqual(caught.exception.reason, DENY_FOREIGN_INSTANCE)
        self.assertEqual(len(restarted), 0, "a foreign token must not populate the table")

    def test_an_unusable_clock_denies_instead_of_authorising(self) -> None:
        registry = SessionRegistry(clock=BrokenClock(), ttl_seconds=60.0)
        with self.assertRaises(SessionDenied) as caught:
            registry.issue(["read"])
        self.assertEqual(caught.exception.reason, DENY_CLOCK)


class NoLeakAndNoSideEffectTests(unittest.TestCase):
    def test_no_denial_text_contains_the_presented_token(self) -> None:
        registry = SessionRegistry(clock=FakeClock(), ttl_seconds=60.0)
        token, session = registry.issue(["read"])
        secret = token.rsplit(".", 1)[1]
        registry.revoke(token)
        with self.assertRaises(SessionDenied) as caught:
            registry.authorize(token, "read")
        for text in (str(caught.exception), repr(caught.exception), repr(session), f"{session}"):
            self.assertNotIn(secret, text)
            self.assertNotIn(token, text)

    def test_module_has_no_io_audit_or_database_coupling(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        imported.discard("__future__")
        # Nothing that could write a log, a row, a file or a socket.
        self.assertEqual(imported, {"hmac", "secrets", "time", "dataclasses", "typing"})
        # Docstrings mention these words on purpose; only real calls matter.
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse(called & {"open", "print", "eval", "exec", "__import__"})

    def test_verification_uses_the_constant_time_primitive(self) -> None:
        # Count real calls, not text: a docstring mention must not satisfy this.
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        constant_time_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compare_digest"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "hmac"
        ]
        self.assertGreaterEqual(len(constant_time_calls), 3)
        # A plain equality on the tag/digest would leak a byte-by-byte oracle.
        source = MODULE_PATH.read_text(encoding="utf-8")
        for pattern in ("tag ==", "digest ==", "secret ==", "token =="):
            self.assertNotIn(pattern, source)


if __name__ == "__main__":
    unittest.main()
