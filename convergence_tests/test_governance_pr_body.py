"""Contract tests for the P4-disposition gate added to the PR body check.

These are structural tests: they prove the gate can tell "a disposition was
stated once, with a concrete pointer" from "nothing was said" or "three options
were left in the template". They cannot prove a fix is real, which is why the
gate's own message says so.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_governance_contract import (
    PR_ATTESTATIONS,
    validate_p4_disposition,
    validate_pr_body,
)

ROOT = Path(__file__).resolve().parents[1]
ATTESTED = "\n".join(PR_ATTESTATIONS)


def body_with(disposition: str) -> str:
    return f"{ATTESTED}\n\n{disposition}\n"


class DispositionAcceptedTests(unittest.TestCase):
    def test_fixed_with_a_pull_request_reference_is_accepted(self) -> None:
        self.assertEqual(validate_p4_disposition("- P4 处置：已修（#158）"), [])

    def test_registered_in_the_backlog_is_accepted(self) -> None:
        self.assertEqual(validate_p4_disposition("- P4 处置：已登记（#155 第 3 行）"), [])

    def test_explicit_risk_acceptance_needs_a_reason(self) -> None:
        self.assertEqual(
            validate_p4_disposition("- P4 处置：明确接受风险（成本高于收益：仅影响测试文案）"),
            [],
        )

    def test_full_width_colon_and_indentation_are_accepted(self) -> None:
        self.assertEqual(validate_p4_disposition("  * P4 处置：已修（commit dd6224a）"), [])

    def test_body_with_all_attestations_and_one_disposition_passes(self) -> None:
        self.assertEqual(validate_pr_body(body_with("- P4 处置：已修（#158）")), [])


class DispositionRejectedTests(unittest.TestCase):
    def test_missing_line_is_rejected(self) -> None:
        errors = validate_p4_disposition(ATTESTED)
        self.assertEqual(len(errors), 1)
        self.assertIn("P4 处置", errors[0])

    def test_template_placeholder_is_rejected(self) -> None:
        template = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
        errors = validate_p4_disposition(template)
        self.assertTrue(errors, "an untouched template must not satisfy the gate")

    def test_leaving_all_three_markers_is_rejected(self) -> None:
        errors = validate_p4_disposition(
            "- P4 处置：已修（#1）/ 已登记（#155）/ 明确接受风险（随便）"
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("exactly one", errors[0])

    def test_bare_marker_without_a_pointer_is_rejected(self) -> None:
        for value in ("已修", "已登记", "明确接受风险", "已修（）", "已修（ ）"):
            with self.subTest(value=value):
                self.assertTrue(validate_p4_disposition(f"- P4 处置：{value}"))

    def test_two_disposition_lines_are_rejected(self) -> None:
        errors = validate_p4_disposition(
            "- P4 处置：已修（#1）\n- P4 处置：已登记（#155）"
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("exactly one P4", errors[0])

    def test_unknown_marker_is_rejected(self) -> None:
        self.assertTrue(validate_p4_disposition("- P4 处置：以后再说"))

    def test_missing_attestation_still_fails(self) -> None:
        errors = validate_pr_body("- P4 处置：已修（#158）")
        self.assertEqual(len(errors), len(PR_ATTESTATIONS))


if __name__ == "__main__":
    unittest.main()
