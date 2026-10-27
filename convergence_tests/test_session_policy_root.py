"""Policy-level contract for the exact SPA root, before any middleware is wired.

Track A's integration finding (issue #43): the legacy WPF Host navigates to `/`,
and the SPA is registered at both `/` and `/v1`. A gate that only allowlists `/v1`
would return 401 on the Host's entrypoint even though the index page carries no
protected data. The future atomic GREEN therefore has to classify **exactly** `/`
as anonymous GET/HEAD and must not widen that to any other root path.

Deliberately RED for the allow case: the merged policy (#145) lists `/v1` and the
bootstrap endpoints, not `/`. The two negative cases are green today and must stay
green when the allow is added - the root entrypoint is not a licence to accept
`POST /` or to reopen `/api/v1/runtime/info`.

Test-only. No middleware, no route and no production policy change is made here.
"""
from __future__ import annotations

import unittest

from srw.supervisor.session_policy import SessionPolicy

TOKEN = "synthetic-policy-root-token-not-a-secret"


def enforced() -> SessionPolicy:
    return SessionPolicy(
        enforce=True, token=TOKEN, allowed_origins=("http://testserver",))


class RootEntrypointContractTests(unittest.TestCase):
    def test_root_get_and_head_are_anonymous_for_the_host_entrypoint(self) -> None:
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                decision = enforced().evaluate(method=method, raw_path="/")
                self.assertTrue(
                    decision.allowed,
                    f"{method} / serves the Host's SPA index and must stay anonymous",
                )

    def test_root_post_is_not_anonymous(self) -> None:
        decision = enforced().evaluate(method="POST", raw_path="/")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status_code, 401)

    def test_runtime_info_is_still_protected(self) -> None:
        # The allow must be exactly `/`: the identifying runtime endpoint stays
        # behind the session, otherwise the Host's startup probe becomes a leak.
        decision = enforced().evaluate(method="GET", raw_path="/api/v1/runtime/info")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status_code, 401)


if __name__ == "__main__":
    unittest.main()
