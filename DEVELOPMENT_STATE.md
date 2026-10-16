# SRW Development State

## Stable source baseline

- Git baseline: `Convergence 08 capability recovery`
- Release metadata: `1.0.0-alpha10-convergence08`
- Schema: `v1_0014`
- Capability reference: `v0.8.12-R2`
- Reference test inventory: 725 v0.8.12 backend tests (reference only, not claimed executed)

## Active development line

Branch: `dev/convergence09`

Convergence 09 focuses on restoring **system/release integrity gates** before adding more surface features.

Implemented on the development branch:

- Local-only Host boundary for all HTTP requests.
- Same-origin browser mutation guard while preserving native/local API clients that omit `Origin`.
- Startup cleanup for SRW-owned interrupted backup/restore staging artifacts.
- Structured system diagnostics with database/data/frontend/task/backup/Knowledge checks.
- SQLite/thread/process resource-probe primitives derived from the v0.8.12 verification truth model.
- Release metadata/schema binding gate.
- Source-controlled minimal Knowledge fixtures, so GitHub CI does not require production Knowledge DB binaries.
- GitHub Actions source gate for Linux and Windows on Python 3.12.

Current local source regression: **55/55 PASS**.

## Product invariants retained

- Evidence-first assessment; Missing ≠ 0.
- Human final decision boundary.
- Material/protocol lineage and stale-decision semantics.
- Privacy-safe remote AI path.
- Source grounding and graphical PDF evidence inspection.
- Canonical identity review/merge.
- Calibration and two-reviewer Gold.
- Decision Operations / feedback / learning loop.
- Recruitment planning and channel intelligence separated from hiring rank.
- Controlled Knowledge Apply with exact rollback.
- Project package portability with historical context preservation.
- WPF/WebView2 Host ABI restored; exact native binary remains carrier-gated.

## Remaining high-priority debt

1. Restore additional runtime/system/release gates from the 725-test reference.
2. Expand the strict resource-residual gate to exact Windows/native-artifact verification and additional v0.8.12 probes.
3. Continue decomposition of `fullworkbench.py` and legacy frontend without capability loss.
4. Broaden Knowledge controlled apply only with complete target-specific validation.
5. Assemble exact Windows Native artifact when the audited v0.8.8 carrier is available and run Windows GUI smoke.
6. Validate ranking/extraction on a real anonymized resume corpus.

## Git workflow

- `main`: tested, merged development truth.
- `dev/convergenceXX`: active version integration branch.
- Focused branches may be used for larger isolated work.
- Pull requests must pass the GitHub Actions source gate before merge.
- Release tags and release artifacts are created only after release metadata and exact-artifact verification are closed.
