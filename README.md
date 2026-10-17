# SRW — Business Convergence 09

SRW is a local-first recruitment operations and decision-support workbench. **v0.8.12-R2 remains the capability-completeness reference.** Preserve evidence, lineage, privacy, calibration, operations and knowledge governance while improving workflow usability.

## Current source baseline

- Version: `1.0.0-alpha10-convergence09`; schema: `v1_0014` (unchanged).
- C08 capability recovery is retained: PDF evidence highlighting, controlled knowledge aliases and exact rollback, project-package portability, guarded backup/CSV export, identity review, assessment, decision operations and planning.
- C09 adds local Host/same-origin boundaries, diagnostics, interrupted-backup cleanup, application shutdown disposal, and self-contained test Knowledge fixtures.
- Integration adds current-source SHA-256 verification alongside the immutable C08 inventory, cross-platform SQLite file-handle probes, pinned test dependencies and reproducible source archives.

## Verify from a clean checkout

Requires Python 3.12 and Node.js 22. Create/activate a virtual environment, then run:

```sh
python -m pip install -r requirements-ci.txt
python scripts/check_source_integrity.py
python scripts/check_release_truth.py
python scripts/run_convergence_verification.py
```

The current suite contains **65 source regression tests**. Actual PASS evidence is the GitHub Actions run for the exact commit, on both Ubuntu and Windows. CI enables `SRW_TEST_RESOURCE_STRICT=1` and uploads logs. Historical C08 reports remain under `verification/`; they are not current-run evidence. The 725-test v0.8.12 inventory is a reference, not a claim of full parity.

## Delivery boundary

This repository and its CI ZIP are **source artifacts**, not standalone Portable installers. The embedded Windows Python runtime and five production Knowledge databases are not included. Test fixtures are synthetic and must not be installed as production Knowledge.

`START.bat` targets a complete Portable assembly. `BUILD_WINDOWS_NATIVE.bat` additionally requires the audited exact v0.8.8 Windows carrier. Source CI on Windows does not certify WPF/WebView2 GUI behavior. External-provider live calls and real-corpus calibration remain pending.

See [development state](DEVELOPMENT_STATE.md), [release procedure](docs/RELEASE_PROCESS.md), [acceptance plan](docs/ACCEPTANCE_PLAN.md), and [architecture](ARCHITECTURE.md).
