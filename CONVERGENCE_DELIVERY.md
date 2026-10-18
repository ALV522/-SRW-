> **历史累计交付日志（非当前验收证据）**：本文保留 C08–C11 的演进和旧版本数据；当前源测试为 113 项（新增历史包审计测试），真实浏览器场景 3 项。最终提交及对应 Actions 结果以 [README](README.md) / [DEVELOPMENT_STATE](DEVELOPMENT_STATE.md) 为准。

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
- Adds an operational action center for overdue and same-day candidate contacts plus completed interviews still missing submitted feedback.
- Adds a unified review center for candidate identity review, judgment-correction review and unreviewed AI / Source Claims, with direct navigation back to human review surfaces.
- Closes judgment-correction review as a real product workflow: candidate context is shown, error labels are human-readable, and open review items can be explicitly resolved with an audited human note.
- Reorders the project navigation around the recruiting workflow and adds a project-level next-action engine covering criteria, intake/material completeness, evidence/decision work, interview feedback/scheduling and Offer follow-up.
- Replaces raw-JSON candidate brief/project handoff modals with readable operator summaries; project handoff still offers the complete JSON payload as a deliberate download.
- Makes dashboard contact actions candidate-specific by opening the exact action plan rather than the generic contact queue.
- Promotes Candidate Workspace from a large modal into a full project page with dedicated Evidence & Decision, Process & Follow-up, and Offer sections; candidate business context and core actions stay visible without stacking nested modals.
- Embeds candidate-specific phone/interview records, scheduling/completion, independent Scorecards and reevaluation drafts into Process & Follow-up, while retaining the project-wide flow page for cross-candidate coordination.
- Rebuilds Job Setup as a real four-step Draft wizard (role basics → employment plan → owners/business context → review). System/Knowledge suggestions are readable draft cards and only enter the criteria editor after an explicit human action; publishing remains separate.
- Criteria editing now preserves recruitment context, decision policy, existing criterion metadata, positive weights and assessment-stage membership instead of reconstructing a reduced Draft.
- Exposes the privacy-safe diagnostics ZIP from the settings UI instead of leaving it as an API-only capability.
- Adds twelve product-facing regression tests; cumulative source suite target is 80 tests.
- Keeps the next objective explicitly product-first: close complete recruiting workflows before additional infrastructure convergence.

## C11 P1 active queue correctness

- Exclude archived projects from decision work; prioritize conflicts before verification by explicit rank, and query scoped project workbench instead of materializing all projects.
- Correct today's contacts from rolling 24-hour horizon to local calendar day; balance overdue, feedback and today preview categories.
- Add two regression tests, target 82 total after PR #17's 80-test baseline. Exact CI remains the source of pass evidence.

## C11 P1 exact review navigation

- Pass review_id and claim_id from the review queue to their destination views.
- Mark exact identity/judgment and Claim records, scroll/highlight and focus their action controls; surface stale items.
- Add one focused regression (83 tests overall). Live WebView2 click-path acceptance still required.

## C11 Portable dependency preflight

- Add `scripts/portable_input_preflight.py` to inventory exact inherited carrier SHA, embedded Python and five Knowledge DBs against an external audited hash manifest.
- Fail closed on missing/mismatched inputs, malformed manifest, SQLite errors or missing required Knowledge search tables; do not package synthetic fixture data.
- Two synthetic source-level regressions, 85-test target. Actual runtime, Knowledge authenticity, native packaging and WPF/WebView2 GUI remain unverified.

## C11 Native assembler source allowlist

- Remove unsafe staging of all root contents; use reviewed source hashes and separately supplied runtime/Knowledge/Host assets only.
- Fix PowerShell reserved `$Host` variable collision; use current versioned UNVERIFIED candidate name rather than stale C07 release filename.
- Add Windows PowerShell parse/source-contract test; 86-test target. No actual native assembly or WPF GUI acceptance claim.
