# SRW — Business Convergence 11

SRW is a local-first recruitment operations and decision-support workbench. **v0.8.12-R2 remains the capability-completeness reference.** Preserve evidence, lineage, privacy, calibration, operations and knowledge governance while improving workflow usability.

## Current source baseline

- Version: `1.0.0-alpha10-convergence11`; schema: `v1_0014` (unchanged).
- C08 capability recovery is retained: PDF evidence highlighting, controlled knowledge aliases and exact rollback, project-package portability, guarded backup/CSV export, identity review, assessment, decision operations and planning.
- C09 adds local Host/same-origin boundaries, diagnostics, interrupted-backup cleanup, application shutdown disposal, and self-contained test Knowledge fixtures.
- Integration retains current-source SHA-256 verification alongside the immutable C08 inventory, cross-platform SQLite file-handle probes, pinned test dependencies and reproducible source archives.
- C10 adds a deterministic privacy-safe diagnostic ZIP endpoint. The bundle exposes release/schema/check/resource metadata only and explicitly excludes candidate content, source blobs, database bytes, provider secrets and local paths.
- C11 starts product workflow closure: the dashboard now exposes a prioritized per-candidate business queue, with one highest-value next action per candidate and direct navigation into the relevant candidate or interview workflow. The dashboard also brings overdue and same-day contacts plus pending interview-feedback execution work into a direct action queue. A unified review center routes identity review, judgment-correction review and unreviewed evidence claims back to their human review surfaces; judgment-correction items can now be explicitly resolved with a required human note. Each project home now derives a single next operational action from published criteria, intake/material state, decision work, evidence review, interview feedback/scheduling and Offer follow-up. Candidate briefs and project handoff are rendered as operator-facing summaries instead of raw JSON, while the complete handoff payload remains downloadable for transfer/audit. The candidate workspace is now a full project page rather than a large modal, with dedicated Evidence & Decision, Process & Follow-up, and Offer sections. The process surface now embeds candidate-specific phone/interview scheduling, completion actions, independent Scorecards and reevaluation drafts instead of forcing a jump back to the project-wide flow page. Job setup is now a real four-step guided Draft workflow—role basics, employment plan, owners/business context, and review—and system suggestions render as readable draft cards that require explicit human insertion, save and publish. The criteria editor now preserves recruiting Draft semantics instead of rebuilding a reduced payload: recruitment context, decision policy, criterion metadata, weights and multi-stage assignments survive editing. The settings surface exposes the privacy-safe diagnostics export directly.

## Verify from a clean checkout

Requires Python 3.12 and Node.js 22. Create/activate a virtual environment, then run:

```sh
python -m pip install -r requirements-ci.txt
python scripts/check_source_integrity.py
python scripts/check_release_truth.py
python scripts/run_convergence_verification.py
```

The current suite contains **105 source regression tests**. Actual PASS evidence is the GitHub Actions run for the exact commit, on both Ubuntu and Windows. CI enables `SRW_TEST_RESOURCE_STRICT=1` and uploads logs. Historical C08 reports remain under `verification/`; they are not current-run evidence. The 725-test v0.8.12 inventory is a reference, not a claim of full parity.

## Delivery boundary

This repository and its CI ZIP are **source artifacts**, not standalone Portable installers. The embedded Windows Python runtime and five production Knowledge databases are not included. Test fixtures are synthetic and must not be installed as production Knowledge.

`START.bat` targets a complete Portable assembly. `BUILD_WINDOWS_NATIVE.bat` additionally requires the audited exact v0.8.8 Windows carrier. Source CI on Windows does not certify WPF/WebView2 GUI behavior. External-provider live calls and real-corpus calibration remain pending.

See [development state](DEVELOPMENT_STATE.md), [release procedure](docs/RELEASE_PROCESS.md), [acceptance plan](docs/ACCEPTANCE_PLAN.md), and [architecture](ARCHITECTURE.md).

C11 P1 queue correctness: exclude archived projects from decision work, sort across candidates by explicit business priority, use local calendar midnight instead of a rolling 24-hour window for today's contacts, and keep overdue/contact/feedback preview categories represented.

C11 review routing: dashboard identity, judgment and Claim review entries carry their exact record IDs to the destination, scrolling to and highlighting the intended row; stale targets display a human-readable message. Browser click-path acceptance is still pending.

### Windows Portable input preflight

Run `python scripts/portable_input_preflight.py` against the separately supplied v0.8.8 Windows carrier, embedded Python runtime and five audited production Knowledge DBs. The default external manifest path is `PRODUCTION_KNOWLEDGE.sha256` (five SHA-256 lines relative to `knowledge/active`). A missing carrier, runtime or trusted manifest yields exit code 2 and a machine-readable BLOCKED report. This check does not generate a ZIP, verify the provenance of an externally supplied manifest, or certify the Windows GUI. Do not add production Knowledge data or private candidate records to Git.

The native assembly candidate uses a source-manifest allowlist instead of copying the entire project root, and stages only the explicitly supplied runtime, five audited Knowledge DBs and exact inherited Host. The output is labelled UNVERIFIED until target-Windows GUI and workflow acceptance; do not use it as a signed or certified release.

### Native payload checks

The Windows Native assembler requires a separately audited PRODUCTION_RUNTIME.sha256 inventory of intended embedded Python files. Runtime staging copies only inventory-listed, hash-matched entries; unlisted local backups or private data remain excluded. The finished ZIP is inspected independently for exact source, Runtime, Knowledge and inherited Host files with SHA-256 checks and an explicit UNVERIFIED_GUI release status. External inventory provenance, an actual Windows executable build and GUI acceptance are still pending.
