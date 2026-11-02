"""R1: hostile pairing text is a refusal, never an encoding exception.

The HTTP entry point refuses a non-ASCII body before the gateway is called, so
these cases exercise the second line of defence directly: ``pair()`` must not be
able to raise ``UnicodeEncodeError`` even if a future caller skips the parser.
No case may mint a session, consume an attempt or clear the pending code.
"""
from __future__ import annotations

import unittest

from srw.runtime.business_session_gateway import (
    DENY_BODY_TOO_LARGE,
    DENY_PAIRING,
    BusinessSessionGateway,
    PairingDenied,
    pairing_body_code,
)

NON_ASCII = ("中文", "café", "😀", "abc\u0080", "\ud800", "\udfff")


class PairingGatewayTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = BusinessSessionGateway()

    def test_non_ascii_code_is_refused_with_zero_side_effects(self):
        for presented in NON_ASCII:
            with self.subTest(presented=ascii(presented)):
                live = self.gateway.issue_pairing_code()
                sessions_before = len(self.gateway.registry)
                with self.assertRaises(PairingDenied) as raised:
                    self.gateway.pair(presented)
                self.assertEqual(raised.exception.reason, DENY_PAIRING)
                self.assertEqual(len(self.gateway.registry), sessions_before,
                                 "no session may be minted")
                self.assertTrue(self.gateway.has_pairing_code,
                                "a malformed attempt must not consume the live code")
                token, csrf = self.gateway.pair(live)
                self.assertTrue(token.startswith("srw1."))
                self.assertTrue(csrf)
                self.gateway.revoke(token)

    def test_non_string_code_is_refused(self):
        for presented in (None, 0, 1.5, True, b"abc", ["x"], {"code": "x"}, object()):
            with self.subTest(presented=type(presented).__name__):
                self.gateway.issue_pairing_code()
                with self.assertRaises(PairingDenied):
                    self.gateway.pair(presented)
                self.assertEqual(len(self.gateway.registry), 0)

    def test_overlong_ascii_code_is_refused_without_hashing_it(self):
        self.gateway.issue_pairing_code()
        with self.assertRaises(PairingDenied):
            self.gateway.pair("x" * 300)
        self.assertEqual(len(self.gateway.registry), 0)
        self.assertTrue(self.gateway.has_pairing_code)


class PairingBodyParserTests(unittest.TestCase):
    def assert_refused(self, payload: bytes, reason: str = DENY_PAIRING) -> None:
        with self.assertRaises(PairingDenied) as raised:
            pairing_body_code(payload)
        self.assertEqual(raised.exception.reason, reason)

    def test_legal_json_with_non_ascii_text_is_refused(self):
        for payload in ('{"code":"中文"}'.encode("utf-8"),
                        '{"code":"café"}'.encode("utf-8"),
                        '{"code":"😀"}'.encode("utf-8"),
                        b'{"code":"\\ud800"}',
                        b'{"code":"\\udfff"}',
                        b'{"code":"abc\\u0080"}'):
            with self.subTest(payload=payload):
                self.assert_refused(payload)

    def test_non_string_and_extra_keys_are_refused(self):
        for payload in (b'{"code":12345}', b'{"code":null}', b'{"code":true}',
                        b'{"code":[]}', b'{"code":{}}', b"[]", b'{"code":"ok","extra":1}',
                        b"", b"not json"):
            with self.subTest(payload=payload):
                self.assert_refused(payload)

    def test_invalid_utf8_is_refused(self):
        self.assert_refused(b'{"code":"\xff\xfe"}')

    def test_overlong_body_and_overlong_code_are_distinguished(self):
        self.assert_refused(b'{"code":"' + b"x" * 2000 + b'"}', DENY_BODY_TOO_LARGE)
        self.assert_refused(b'{"code":"' + b"x" * 300 + b'"}')

    def test_a_canonical_ascii_code_is_returned_unchanged(self):
        self.assertEqual(pairing_body_code(b'{"code":"abc-123_XYZ"}'), "abc-123_XYZ")


if __name__ == "__main__":
    unittest.main()
