"""API contract safety net for the API-first modular Core (R1, Issue #63).

These tests freeze what SRW already promises its clients before any route is
moved out of `api/fullworkbench.py`. They do not prove business invariants;
they prove that the transport surface cannot drift silently while it is being
refactored.

The authoritative route table comes from a real application instance built on a
disposable synthetic workspace, so a route added in any module is visible here
even if it is not declared in `app.py`.
"""
from __future__ import annotations

import gc
import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from scripts import api_inventory
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "verification" / "api_contract"


def load(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def error_form(response) -> str:
    try:
        payload = response.json()
    except Exception:
        return "plain_text"
    if (isinstance(payload, dict) and isinstance(payload.get("detail"), str)
            and isinstance(payload.get("error"), dict)
            and isinstance(payload["error"].get("code"), str)):
        return "envelope"
    return "json_other"


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="srw-api-contract-")
        root = Path(cls._tmp.name)
        url = f"sqlite+pysqlite:///{(root / 'contract.db').as_posix()}"
        cls.app = create_v1_app(
            url,
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        cls.routes = api_inventory.collect_routes(cls.app)

    @classmethod
    def tearDownClass(cls):
        # create_v1_app owns its engine internally; drop the references so the
        # SQLite handle is released before the temporary directory is removed.
        cls.app = None
        cls.routes = None
        gc.collect()
        cls._tmp.cleanup()

    def test_live_route_table_matches_the_frozen_inventory(self):
        frozen = load("inventory.json")
        expected = {(row["method"], row["path"]) for row in frozen["routes"]}
        actual = {(row["method"], row["path"]) for row in self.routes}
        added = sorted(actual - expected)
        removed = sorted(expected - actual)
        self.assertEqual(
            (added, removed), ([], []),
            "API surface changed. Adding or removing a route is a client contract change: "
            "regenerate verification/api_contract/inventory.json in the same PR and say why. "
            f"added={added[:10]} removed={removed[:10]}",
        )

    def test_inventory_covers_every_live_route_exactly_once(self):
        frozen = load("inventory.json")
        self.assertEqual(frozen["route_count"], len(self.routes))
        self.assertEqual(len({(r["method"], r["path"]) for r in self.routes}), len(self.routes),
                         "the live route table must not register the same method+path twice")

    def test_every_route_names_an_owning_module(self):
        orphans = [row for row in self.routes if not row["owner"]]
        self.assertEqual(orphans, [], "every route must be attributable to a module")
        foreign = [row for row in self.routes
                   if not (row["owner"].startswith("srw.") or row["owner"].startswith("scripts."))]
        self.assertEqual(foreign, [], "routes must be owned by Core or carrier code, not by tests")

    def test_every_route_is_classified_into_a_business_domain(self):
        unclassified = sorted({row["path"] for row in self.routes if row["domain"] == "other"})
        self.assertEqual(unclassified, [],
                         "add the new resource to DOMAIN_KEYWORDS in scripts/api_inventory.py "
                         "so route moves stay attributable to a domain")

    def test_frontend_literals_all_resolve_to_registered_routes(self):
        calls = api_inventory.collect_frontend_calls(self.routes)
        unresolved = [call for call in calls if call["matched_path"] is None]
        self.assertEqual(
            unresolved, [],
            "the browser calls a path no route serves; update the frontend or the route. "
            f"unresolved={[c['literal'] for c in unresolved][:10]}",
        )

    def test_mutation_surface_cannot_grow_without_classification(self):
        frozen = load("mutations.json")
        classified = {(row["method"], row["path"]) for row in frozen["classified"]}
        live = {(row["method"], row["path"]) for row in self.routes if row["mutation"]}
        unclassified = live - classified
        self.assertLessEqual(
            len(unclassified), frozen["baseline_unclassified"],
            "a new mutating route was added without an entry in "
            "verification/api_contract/mutations.json. Classify it (use case, concurrency, "
            "audit, human actor) or raise the baseline explicitly in review. "
            f"unclassified={sorted(unclassified)[:10]}",
        )

    def test_observable_error_contract_is_unchanged(self):
        client = TestClient(self.app)
        errors = load("errors.json")
        for case in errors["cases"]:
            with self.subTest(case=case["case"]):
                method = case["method"].lower()
                kwargs = {"json": case.get("body")} if "body" in case else {}
                response = getattr(client, method)(case["path"], **kwargs)
                self.assertEqual(response.status_code, case["status"], case["note"])
                self.assertEqual(error_form(response), case["form"],
                                 f"{case['case']}: error shape changed; update "
                                 f"verification/api_contract/errors.json in the same PR")

    def test_structured_errors_keep_the_standard_envelope(self):
        client = TestClient(self.app)
        response = client.post("/api/v1/projects", json={})
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIsInstance(payload.get("detail"), str)
        self.assertEqual(payload["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
