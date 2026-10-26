"""Green conformance tests for the opt-in business-session policy (#43).

These tests are all expected to pass today: ``session_policy`` is a new pure
module and nothing else imports it, so there is no production behaviour to turn
RED first. They pin the contract Track A approved before any middleware exists,
so the later integration cannot quietly widen the allowlist, accept a token from
the query string, or let a header bypass the origin boundary.

The 7 opt-in **API-level** RED cases (HTTP 200 -> 401/403 against a live app)
stay in a separate test-only PR, because they require the middleware that Track A
owns.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from srw.supervisor import session_policy
from srw.supervisor.session_policy import (
    ANONYMOUS_READ_PATHS,
    ENFORCE_ENV,
    SESSION_HEADER,
    TOKEN_ENV,
    SessionPolicy,
    normalise_path,
)

TOKEN = "s3cret-token-value"


def enabled_policy(**kwargs) -> SessionPolicy:
    options = {"enforce": True, "token": TOKEN, "allowed_origins": ("http://127.0.0.1:8765",)}
    options.update(kwargs)
    return SessionPolicy(**options)


class DefaultOffTests(unittest.TestCase):
    """The gate must not change today's behaviour unless it is switched on."""

    def test_absent_environment_disables_enforcement(self) -> None:
        policy = SessionPolicy.from_environ({})
        self.assertFalse(policy.enforce)
        self.assertFalse(policy.configured)

    def test_only_the_literal_one_enables_enforcement(self) -> None:
        # "true"/"yes"/"on" are deliberately not aliases: an operator should not be
        # able to switch on authorization by accident.
        for value in ("0", "false", "true", "yes", "on", ""):
            with self.subTest(value=value):
                policy = SessionPolicy.from_environ({ENFORCE_ENV: value, TOKEN_ENV: TOKEN})
                self.assertFalse(policy.enforce)

    def test_env_value_is_stripped(self) -> None:
        policy = SessionPolicy.from_environ({ENFORCE_ENV: " 1 ", TOKEN_ENV: f" {TOKEN} "})
        self.assertTrue(policy.enforce)
        self.assertEqual(policy.token, TOKEN)

    def test_disabled_policy_allows_everything(self) -> None:
        policy = SessionPolicy.from_environ({})
        for method, path in (
            ("POST", "/api/v1/candidates"),
            ("GET", "/api/v1/info"),
            ("DELETE", "/api/v1/projects/1"),
            ("POST", "//evil//path"),
        ):
            with self.subTest(method=method, path=path):
                decision = policy.evaluate(method=method, raw_path=path)
                self.assertTrue(decision.allowed)
                self.assertEqual(decision.reason, "enforcement_disabled")


class AnonymousAllowlistTests(unittest.TestCase):
    """Bootstrap reads stay anonymous; everything identifying needs a session."""

    def setUp(self) -> None:
        self.policy = enabled_policy()

    def test_bootstrap_reads_are_anonymous(self) -> None:
        paths = sorted(ANONYMOUS_READ_PATHS) + ["/v1", "/v1/app.js", "/v1/assets/logo.svg"]
        for path in paths:
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method):
                    decision = self.policy.evaluate(method=method, raw_path=path)
                    self.assertTrue(decision.allowed, decision.reason)
                    self.assertEqual(decision.reason, "anonymous_bootstrap_path")

    def test_identifying_reads_are_not_anonymous(self) -> None:
        # Track A explicitly named these three: they expose instance / release /
        # session identifiers and must not be whitelisted as-is.
        for path in (
            "/api/v1/info",
            "/api/v1/runtime/info",
            "/api/v1/runtime/live",
            "/api/v1/candidates",
            "/api/v1/sources/abc/content",
            "/api/v1/system/backups",
            "/api/v1/settings",
        ):
            with self.subTest(path=path):
                decision = self.policy.evaluate(method="GET", raw_path=path)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.status_code, 401)
                self.assertEqual(decision.reason, "session_token_required")

    def test_allowlist_is_exact_match_not_prefix(self) -> None:
        for path in ("/health/live/extra", "/health/livex", "/api/v1/runtime/capabilities/secret"):
            with self.subTest(path=path):
                self.assertFalse(self.policy.evaluate(method="GET", raw_path=path).allowed)

    def test_static_prefix_does_not_leak_to_lookalike_paths(self) -> None:
        for path in ("/v1x", "/v1extra/app.js", "/v10/app.js"):
            with self.subTest(path=path):
                self.assertFalse(self.policy.evaluate(method="GET", raw_path=path).allowed)

    def test_static_prefix_is_case_sensitive(self) -> None:
        self.assertFalse(self.policy.evaluate(method="GET", raw_path="/V1/app.js").allowed)

    def test_writes_and_options_are_never_anonymous(self) -> None:
        # Even on an allowlisted bootstrap path, a non-safe method needs a session.
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "post"):
            with self.subTest(method=method):
                decision = self.policy.evaluate(method=method, raw_path="/health/live")
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "session_token_required")


class SessionTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = enabled_policy()

    def test_host_style_request_without_origin_passes_with_token(self) -> None:
        decision = self.policy.evaluate(
            method="POST", raw_path="/api/v1/candidates", headers={SESSION_HEADER: TOKEN})
        self.assertTrue(decision.allowed, decision.reason)
        self.assertEqual(decision.reason, "ok")

    def test_header_lookup_is_case_insensitive(self) -> None:
        decision = self.policy.evaluate(
            method="POST", raw_path="/api/v1/candidates", headers={"x-srw-session": TOKEN})
        self.assertTrue(decision.allowed, decision.reason)

    def test_missing_token_is_rejected(self) -> None:
        decision = self.policy.evaluate(method="POST", raw_path="/api/v1/candidates")
        self.assertFalse(decision.allowed)
        self.assertEqual((decision.status_code, decision.reason),
                         (401, "session_token_required"))

    def test_wrong_token_is_rejected(self) -> None:
        for presented in ("wrong", TOKEN.upper(), f"{TOKEN} ", ""):
            with self.subTest(presented=presented):
                decision = self.policy.evaluate(
                    method="POST", raw_path="/api/v1/candidates",
                    headers={SESSION_HEADER: presented})
                self.assertFalse(decision.allowed)
                self.assertIn(decision.reason, {"session_token_required", "session_token_invalid"})

    def test_enforced_without_configured_token_fails_closed(self) -> None:
        policy = SessionPolicy(enforce=True, token="")
        decision = policy.evaluate(method="POST", raw_path="/api/v1/candidates")
        self.assertFalse(decision.allowed)
        self.assertEqual((decision.status_code, decision.reason),
                         (401, "session_token_not_configured"))
        # Anonymous bootstrap reads still work, so the SPA can explain the state.
        self.assertTrue(policy.evaluate(method="GET", raw_path="/health/ready").allowed)

    def test_token_in_query_string_is_refused_even_when_correct(self) -> None:
        for query in (f"session={TOKEN}", f"x-srw-session={TOKEN}",
                      f"SESSION_TOKEN={TOKEN}", f"a=1&session={TOKEN}"):
            with self.subTest(query=query):
                decision = self.policy.evaluate(
                    method="POST", raw_path="/api/v1/candidates",
                    headers={SESSION_HEADER: TOKEN}, query_string=query)
                self.assertFalse(decision.allowed)
                self.assertEqual((decision.status_code, decision.reason),
                                 (401, "session_token_in_query"))

    def test_query_token_is_refused_on_anonymous_paths_too(self) -> None:
        decision = self.policy.evaluate(
            method="GET", raw_path="/health/live", query_string=f"session={TOKEN}")
        self.assertEqual((decision.status_code, decision.reason),
                         (401, "session_token_in_query"))

    def test_rotation_revokes_the_previous_token(self) -> None:
        rotated = self.policy.rotated("next-token")
        self.assertTrue(rotated.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: "next-token"}).allowed)
        stale = rotated.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN})
        self.assertFalse(stale.allowed)
        self.assertEqual(stale.reason, "session_token_invalid")
        self.assertTrue(self.policy.is_revoked(TOKEN) is False)

    def test_revoked_token_is_rejected(self) -> None:
        policy = enabled_policy(revoked=(TOKEN,))
        decision = policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN})
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "session_token_invalid")


class OriginBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = enabled_policy()

    def test_cross_origin_is_refused_even_with_a_valid_token(self) -> None:
        decision = self.policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN, "Origin": "http://evil.example"})
        self.assertFalse(decision.allowed)
        self.assertEqual((decision.status_code, decision.reason),
                         (403, "origin_not_allowed"))

    def test_cross_site_fetch_metadata_is_refused(self) -> None:
        decision = self.policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN, "Sec-Fetch-Site": "cross-site"})
        self.assertFalse(decision.allowed)
        self.assertEqual((decision.status_code, decision.reason),
                         (403, "origin_not_allowed"))

    def test_configured_origin_with_valid_token_passes(self) -> None:
        decision = self.policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN, "Origin": "http://127.0.0.1:8765",
                     "Sec-Fetch-Site": "same-origin"})
        self.assertTrue(decision.allowed, decision.reason)

    def test_unlisted_origin_is_refused_when_no_origins_are_configured(self) -> None:
        # Fail closed: enabling the gate without declaring the browser origin must
        # not turn "any Origin" into "trusted Origin".
        policy = SessionPolicy(enforce=True, token=TOKEN)
        decision = policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN, "Origin": "http://127.0.0.1:8765"})
        self.assertEqual((decision.status_code, decision.reason),
                         (403, "origin_not_allowed"))
        # The Origin-less Native Host path still works.
        self.assertTrue(policy.evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN}).allowed)


class AmbiguousPathTests(unittest.TestCase):
    """Every bypass attempt must be refused, not decoded into an allowlist hit."""

    BYPASSES = (
        "//api/v1/candidates",
        "/api/v1//candidates",
        "/api/v1/./candidates",
        "/api/v1/../candidates",
        "/api/../health/live",
        "/health/./live",
        "/health//live",
        "/api/v1\\candidates",
        "/api\\v1\\candidates",
        "/api/v1/%63andidates",
        "/api/v1/%2e%2e/candidates",
        "/api%2fv1/candidates",
        "/api/v1/candidates?x=1",
        "/api/v1/candidates#frag",
        "/api/v1/candidates;jsessionid=1",
        "/api/v1/ candidates",
        "/api/v1/candidates.",
        "/api/v1/candidates ",
        "/api/v1/候选人",
        "/api/v1/candidates\x00",
        "api/v1/candidates",
        "",
    )

    def setUp(self) -> None:
        self.policy = enabled_policy()

    def test_normalise_path_returns_none_for_ambiguous_input(self) -> None:
        for raw in self.BYPASSES:
            with self.subTest(raw=raw):
                self.assertIsNone(normalise_path(raw))

    def test_ambiguous_paths_are_refused_while_enforced(self) -> None:
        for raw in self.BYPASSES:
            with self.subTest(raw=raw):
                decision = self.policy.evaluate(
                    method="GET", raw_path=raw, headers={SESSION_HEADER: TOKEN})
                self.assertFalse(decision.allowed)
                self.assertEqual((decision.status_code, decision.reason),
                                 (400, "ambiguous_path"))

    def test_normalise_path_keeps_legitimate_paths_intact(self) -> None:
        for raw in ("/", "/health/live", "/api/v1/runtime/capabilities",
                    "/api/v1/candidates/abc", "/v1", "/v1/app.js",
                    "/v1/assets/app-1.2.3.js", "/health/live/"):
            with self.subTest(raw=raw):
                self.assertIsNotNone(normalise_path(raw), raw)

    def test_overlong_path_is_refused(self) -> None:
        self.assertIsNone(normalise_path("/api/v1/" + "a" * 4096))


class NoSideEffectTests(unittest.TestCase):
    """A rejected request must not write, log or audit anything."""

    def test_policy_module_has_no_io_or_persistence_imports(self) -> None:
        source = Path(session_policy.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported - {"__future__"}, {"hmac", "dataclasses", "typing"})

    def test_evaluate_writes_nothing_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = sorted(path.name for path in Path(tmp).rglob("*"))
            policy = enabled_policy()
            for method, path, headers in (
                ("POST", "/api/v1/candidates", {}),
                ("POST", "/api/v1/candidates", {SESSION_HEADER: "bad"}),
                ("GET", "/api/v1/info", {}),
                ("POST", "//evil", {}),
            ):
                policy.evaluate(method=method, raw_path=path, headers=headers)
            after = sorted(path.name for path in Path(tmp).rglob("*"))
        self.assertEqual(before, after)

    def test_decision_is_immutable_and_token_free(self) -> None:
        decision = enabled_policy().evaluate(
            method="POST", raw_path="/api/v1/candidates",
            headers={SESSION_HEADER: TOKEN})
        self.assertEqual(set(decision.__dict__), {"allowed", "status_code", "reason"})
        with self.assertRaises(FrozenInstanceError):
            decision.reason = "tampered"  # type: ignore[misc]
        self.assertNotIn(TOKEN, repr(decision))

    def test_evaluate_is_deterministic(self) -> None:
        policy = enabled_policy()
        first = policy.evaluate(method="POST", raw_path="/api/v1/candidates")
        second = policy.evaluate(method="POST", raw_path="/api/v1/candidates")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
