"""The /api/v1 route inventory must stay in sync with its reviewed baseline (G1 contract).

Mirrors scripts/check_api_contract.py inside the source gate so route drift fails the
normal suite as well as the dedicated CI step. The check builds the app against
temporary directories only (charter A8) and never contacts a provider or workspace.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_api_contract as contract  # noqa: E402


class ApiContractInventoryTests(unittest.TestCase):
    def test_inventory_matches_reviewed_baseline(self):
        self.assertEqual(contract.collect_inventory(), contract.load_baseline())

    def test_check_exits_zero_on_current_baseline(self):
        self.assertEqual(contract.main([]), 0)

    def test_check_detects_route_drift(self):
        inventory = contract.collect_inventory()
        self.assertGreater(len(inventory), 100)
        with __import__("tempfile").TemporaryDirectory() as tmp:
            drifted = Path(tmp) / "drifted-inventory.txt"
            drifted.write_text(
                contract.render(inventory + ["GET /api/v1/rogue-route"]), encoding="utf-8"
            )
            self.assertEqual(contract.main(["--baseline", str(drifted)]), 1)

    def test_inventory_contains_core_product_surface(self):
        inventory = set(contract.collect_inventory())
        for expected in (
            "GET /api/v1/workbench",
            "POST /api/v1/projects",
            "GET /api/v1/candidates/{candidate_id:str}/workspace",
            "POST /api/v1/candidates/{candidate_id:str}/decision",
            "POST /api/v1/projects/{project_id:str}/knowledge/apply",
            "GET /api/v1/settings/providers",
            "POST /api/v1/runtime/shutdown",
        ):
            self.assertIn(expected, inventory)


if __name__ == "__main__":
    unittest.main()
