"""SRW G1 repository governance contract: static, no external dependencies.

Checks truthful version policy binding and essential agent entry points.
PR body attestation does not prove someone read the documents; branch rules and review
must make this check a required merge gate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "AGENTS.md",
    "docs/PROJECT_OVERVIEW.md",
    "docs/PRODUCT_CHARTER.md",
    "docs/CAPABILITY_MATRIX.md",
    "docs/DEVELOPMENT_GOVERNANCE.md",
    "docs/VERSION_POLICY.md",
    "VERSION_POLICY.json",
    "docs/DUAL_CARRIER_PLAN.md",
    "docs/OWNER_GUIDE.md",
    "docs/ACCEPTANCE_PLAN.md",
    "docs/ROADMAP.md",
    "docs/RELEASE_PROCESS.md",
    ".github/pull_request_template.md",
    ".github/workflows/governance.yml",
)
PR_ATTESTATIONS = (
    "- [x] 已阅读 AGENTS.md 及指定必读治理文件",
    "- [x] 已核对准确源码 SHA、版本、Schema 和工件边界",
    "- [x] 已给出修改影响与相应业务/双端验收范围",
    "- [x] 不以源代码或浏览器通过冒充 Windows/发行通过",
)
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]+)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]+))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def validate(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for relative in REQUIRED:
        file = root / relative
        if not file.is_file() or file.is_symlink():
            problems.append(f"missing or symlink governance file: {relative}")
        elif not file.read_text(encoding="utf-8").strip():
            problems.append(f"empty governance file: {relative}")
    if problems:
        return problems

    instructions = (root / "AGENTS.md").read_text(encoding="utf-8")
    for mandatory in REQUIRED[:8]:
        if mandatory not in instructions:
            problems.append(f"AGENTS.md must reference required document: {mandatory}")

    try:
        policy = json.loads((root / "VERSION_POLICY.json").read_text(encoding="utf-8"))
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        build = json.loads((root / "BUILD_INFO.json").read_text(encoding="utf-8"))
        release = json.loads((root / "backend/srw/release_state.json").read_text(encoding="utf-8"))
        schema_source = (root / "backend/srw/runtime/db/schema.py").read_text(encoding="utf-8")
        match = re.search(r"V1_SCHEMA_REVISION\s*=\s*['\"]([^'\"]+)['\"]", schema_source)
        if match is None:
            raise ValueError("cannot extract actual V1_SCHEMA_REVISION")
        if policy.get("schema") != "srw.version-policy.v1":
            problems.append("VERSION_POLICY.json schema identity invalid")
        if policy.get("governance_revision") != "G1":
            problems.append("unexpected governance revision")
        if policy.get("current_runtime_version") != version:
            problems.append("VERSION_POLICY current_runtime_version differs from VERSION")
        if build.get("version") != version or release.get("version") != version:
            problems.append("VERSION_POLICY conflicts with BUILD_INFO or release_state")
        if policy.get("schema_revision") != match.group(1):
            problems.append("VERSION_POLICY schema_revision differs from actual code")
        upcoming = policy.get("next_product_version", "")
        if not isinstance(upcoming, str) or SEMVER.fullmatch(upcoming) is None:
            problems.append("next_product_version is not SemVer")
        if policy.get("next_version_status") == "proposed-not-effective" and upcoming == version:
            problems.append("proposed next_product_version already equals current VERSION")
        if policy.get("production_release") is not False and policy.get("release_channel") == "development":
            problems.append("development channel cannot claim production_release")
        if policy.get("dual_carrier_target") != ["windows-native", "local-web"]:
            problems.append("dual_carrier_target must contain both product carriers")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"invalid governance/version data: {exc}")
    return problems


def validate_pr_body(body: str) -> list[str]:
    return [f"PR must check exact attestation: {value}" for value in PR_ATTESTATIONS if value not in body]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-pr-body", action="store_true")
    args = parser.parse_args()
    errors = validate()
    if args.check_pr_body:
        errors += validate_pr_body(os.environ.get("PR_BODY", ""))
    if errors:
        for issue in errors:
            print(f"GOVERNANCE ERROR: {issue}")
        return 1
    print("SRW Governance G1 contract PASS; PR attestations are declarations, not proof of reading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
