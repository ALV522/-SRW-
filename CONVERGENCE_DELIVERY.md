# SRW v1.0 Business Convergence 08 — 0.8 Capability Recovery

## Implemented

- Deepened Source Grounding into a graphical PDF page renderer. A grounded Claim opens the exact PDF page with its verified bbox highlighted; claim/source/page mismatch is rejected.
- Extended Controlled Knowledge Apply from taxonomy aliases to competency aliases, with target existence checks, alias-conflict blocking, semantic diff, exact digest activation and byte-exact rollback.
- Hardened backup restore against duplicate ZIP members and compressed/expanded size abuse before SQLite is read.
- Closed remaining CSV formula-injection edges in candidate evidence summaries and contact-list exports.
- Restored full project-package portability: project/candidate/material/evidence/decision/operations/interview/offer/feedback/planning state and referenced Source blobs are exported together. Import validates declared ZIP members and blob hashes, requires exact preview digest, remaps IDs, and preserves historical decision-context hashes so imported judgments/decisions cannot masquerade as current.
- Added 9 Convergence 08 recovery tests; cumulative convergence suite is **46/46 PASS**.
- Preserved the Convergence 07 Windows WPF/WebView2 Host ABI and exact-carrier gate.

## Verification boundary

The current build verifies source/HTTP behavior, PDF page rendering, knowledge apply/rollback, project-package round trip and tamper guards, export/restore safety, JavaScript syntax, Runtime/Knowledge inheritance and Host ABI. It still does not claim Windows WPF GUI acceptance without assembling from the exact audited v0.8.8 carrier and running the resulting artifact on Windows. External-provider live calls and real-corpus ranking calibration remain environment/data dependent.


## Convergence 10

- Release identity: `1.0.0-alpha10-convergence10`; schema remains `v1_0014`.
- Adds `GET /api/v1/system/diagnostics/export` for a deterministic privacy-safe support ZIP.
- Diagnostic bundle includes only normalized release/health/count metadata and an internal SHA-256 manifest.
- Explicit exclusions: candidate/resume content, Source blobs, database bytes, provider secrets and local paths.
- Adds three focused regression tests; cumulative source suite target is 68 tests.
- Adds a reviewed source-manifest generator; CI emits a candidate manifest but the integrity gate remains fail-closed.
- Portable/native artifacts remain outside this source-only delivery until embedded runtime, production Knowledge and exact Windows carrier acceptance are completed.


## Convergence 11 — Business Workflow Closure

- Release identity: `1.0.0-alpha10-convergence11`; schema remains `v1_0014`.
- Promotes the existing decision workbench from an internal service into the primary dashboard as an actionable business queue.
- Shows only the highest-priority current work item for each candidate, preserving the evidence/decision context rather than presenting raw task volume.
- Adds direct navigation from the dashboard into the relevant candidate evidence/decision workspace or interview workflow.
- Exposes the privacy-safe diagnostics ZIP from the settings UI instead of leaving it as an API-only capability.
- Adds three product-facing regression tests; cumulative source suite target is 71 tests.
- Keeps the next objective explicitly product-first: close complete recruiting workflows before additional infrastructure convergence.
