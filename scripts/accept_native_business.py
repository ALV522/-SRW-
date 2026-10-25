"""Independent Native embedded-Python business regression (synthetic data only).

This is not WPF UI automation and does not grant Windows product/RC/GA approval.
Use an EXTERNAL copy of this script with an immutable, already-extracted
source-built Native candidate. Never run tests in a real recruiting workspace.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Candidate contents are immutable and are independently enumerated; our own
# verifier imports must not write Python caches inside the candidate.
if __name__ == "__main__":
    sys.dont_write_bytecode = True
if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_payload import PayloadError
from scripts.verify_rebuilt_native import inspect_rebuilt

SCHEMA = "srw.native-embedded-business-acceptance.v1"
SUITES = {
    "project_protocol": "test_project_authoring_routes",
    "candidate_decision": "test_candidate_decision_routes",
    "interview_scorecard": "test_interview_routes",
    "offer_human_transition": "test_offer_routes",
    "reevaluation_cas": "test_reevaluation_routes",
    "restart_backup_restore": "test_real_restore_restart",
}
# Minimum counts are only a lower bound: missing modules are still failures,
# and no individual test may fail or error. They cannot be quietly skipped.
MIN_TESTS = {name: 1 for name in SUITES}
DRIVER_TAG = "SRW_SYNTHETIC_TEST_RESULT:"

DRIVER = r'''
import io
import json
import sys
import unittest
from pathlib import Path
root=Path(sys.argv[1]).resolve(strict=True)
module=sys.argv[2]
for p in (root / 'backend', root / 'scripts', root / 'convergence_tests', root):
    sys.path.insert(0, str(p))
loader=unittest.TestLoader()
suite=loader.loadTestsFromName(module)
buffer=io.StringIO()
result=unittest.TextTestRunner(stream=buffer, verbosity=1).run(suite)
# Deliberately never print test traces, test IDs, data rows, raw exceptions,
# filesystem paths, user-provided source material, or credentials.
print('SRW_SYNTHETIC_TEST_RESULT:' + json.dumps({
    'tests':result.testsRun,
    'failures':len(result.failures),
    'errors':len(result.errors),
    'skipped':len(result.skipped),
    'passed':result.wasSuccessful(),
}, separators=(',', ':')))
sys.exit(0 if result.wasSuccessful() else 3)
'''


def validated_result(output: str, code: int, *, suite: str) -> dict:
    """Fail closed if the child did not produce exactly one expected summary."""
    if suite not in SUITES:
        raise PayloadError("unrecognized embedded Native business suite")
    lines = [line[len(DRIVER_TAG):] for line in output.splitlines()
             if line.startswith(DRIVER_TAG)]
    if len(lines) != 1:
        raise PayloadError("embedded business test result missing or ambiguous")
    try:
        data = json.loads(lines[0])
    except (ValueError, TypeError) as exc:
        raise PayloadError("embedded business test result invalid JSON") from exc
    if not isinstance(data, dict) or set(data) != {"tests", "failures", "errors", "skipped", "passed"}:
        raise PayloadError("embedded business test result invalid shape")
    if any(type(data[key]) is not int or data[key] < 0
           for key in ("tests", "failures", "errors", "skipped")):
        raise PayloadError("embedded business counters invalid")
    if (type(data["passed"]) is not bool or code != 0 or not data["passed"]
            or data["failures"] or data["errors"] or data["skipped"]
            or data["tests"] < MIN_TESTS[suite]):
        raise PayloadError("embedded business test failed, skipped or incomplete: " + suite)
    return {"suite": suite, "status": "PASS", "tests": data["tests"]}


def run_embedded_regressions(root: Path, python: Path, *, timeout: int = 600) -> list[dict]:
    """Use only candidate runtime and candidate source in disposable workspaces.

    This function is also source-testable with a Python interpreter on CI,
    but only CLI `main` can issue a NATIVE_WINDOWS_PASS claim, on Windows and
    after verifying a real source-built Windows Native package/embedded EXE.
    """
    if not 60 <= timeout <= 1800:
        raise PayloadError("embedded Native business timeout outside safe limits")
    if not python.is_file() or python.is_symlink():
        raise PayloadError("embedded Python executable missing or linked")
    with tempfile.TemporaryDirectory(prefix="srw-native-business-regression-") as td:
        env = os.environ.copy()
        # Source regression cases instantiate their own further ephemeral data
        # roots. Force default workspace resolution to this disposable parent.
        env.update({
            "RECRUITMENT_DATA_DIR": str(Path(td) / "data"),
            "RECRUITMENT_FRONTEND_DIST": str(root / "frontend" / "dist"),
            "RECRUITMENT_KNOWLEDGE_DIR": str(Path(td) / "knowledge-not-present"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SRW_BACKGROUND_WORKER": "0",
        })
        results = []
        for name, module in SUITES.items():
            child = subprocess.run(
                [str(python), "-I", "-B", "-c", DRIVER, str(root), module],
                cwd=td, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
            )
            # Never expose stdout/stderr on error. The tests use synthetic data
            # but an attacker could still inject private content in a trace.
            results.append(validated_result(child.stdout, child.returncode, suite=name))
        return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--zip", type=Path, required=True)
    p.add_argument("--expected-zip-sha256", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    try:
        if os.name != "nt":
            raise PayloadError("Native embedded-business acceptance requires actual Windows")
        if not re.fullmatch(r"[0-9a-f]{64}", args.expected_zip_sha256):
            raise PayloadError("Native candidate SHA-256 must be explicit lowercase 64 hex")
        if args.root.is_symlink() or args.zip.is_symlink():
            raise PayloadError("Native candidate input symlink forbidden")
        root = args.root.resolve(strict=True)
        evidence = args.evidence.resolve()
        if (evidence.is_relative_to(root) or evidence.exists() or evidence.is_symlink()
                or evidence == args.zip.resolve()):
            raise PayloadError("Native business evidence must be a new file outside candidate")
        identity = inspect_rebuilt(
            root, archive=args.zip,
            expected_archive_sha256=args.expected_zip_sha256,
        )
        if identity["zip_sha256"] != args.expected_zip_sha256:
            raise PayloadError("candidate ZIP identity mismatch")
        results = run_embedded_regressions(root, root / "runtime" / "python.exe", timeout=args.timeout)
        output = {
            "schema": SCHEMA,
            "status": "NATIVE_EMBEDDED_BUSINESS_SOURCE_REGRESSIONS_PASS_UI_NOT_EVALUATED",
            "source_git_sha": identity["source_git_sha"],
            "candidate_sha256": args.expected_zip_sha256,
            "synthetic_data_only": True,
            "embedded_python_used": True,
            "suites": results,
            "tests_passed": sum(x["tests"] for x in results),
            "wpf_gui_operator_actions_accepted": False,
            "actual_native_end_to_end_ui_accepted": False,
            "provider_ocr_asr_accepted": False,
            "dual_carrier_accepted": False,
        }
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("x", encoding="utf-8") as fp:
            json.dump(output, fp, ensure_ascii=False, indent=2, sort_keys=True)
            fp.write("\n")
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except (PayloadError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_type": type(exc).__name__,
                          "wpf_gui_operator_actions_accepted": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
