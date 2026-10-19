# SRW Development State — Convergence 11

Version: `1.0.0-alpha10-convergence11`; schema `v1_0014`; capability reference `v0.8.12-R2`.

## Integrated capabilities

C08 business capabilities are retained. C09 supplies local-only Host and browser same-origin checks, known interrupted-backup cleanup, structured diagnostics, independent synthetic Knowledge fixtures, SQLite shutdown disposal and Ubuntu/Windows Python 3.12 regression gates. C10 adds a privacy-safe deterministic diagnostic support bundle with explicit exclusion of candidate content, Source blobs, database bytes, provider secrets and local filesystem paths. C11 changes the center of gravity from infrastructure to product workflow: the home dashboard now surfaces the decision workbench as an actionable queue, deduplicated to the highest-priority open action per candidate, and routes the operator directly into candidate evidence/decision or interview work. The same dashboard now surfaces overdue and same-day candidate contacts plus completed interviews missing submitted feedback, with direct navigation back into the operational action. A unified review center makes pending identity reviews, judgment-correction reviews and unreviewed evidence claims actionable from the home screen. Judgment-correction review is now end-to-end: candidate context is visible and an operator can explicitly resolve the item with a required review note. Project home also derives one explicit next action from current business state, reducing the need to interpret internal modules or hunt across tabs. Candidate brief and project handoff views now present readable business summaries with a full JSON handoff download retained for transfer/audit; dashboard contact actions open the specific candidate action plan rather than a generic queue. The candidate workspace has been promoted from a modal into a full project surface with separate Evidence & Decision, Process & Follow-up, and Offer modes, while preserving the existing evidence, verification, decision, intake, OCR/ASR and Offer actions. Candidate-specific phone screens, interview scheduling/completion, independent Scorecards and reevaluation drafts are now directly available in Process & Follow-up. Job setup is now a true four-step guided Draft flow; state is preserved across steps, suggestions are rendered as readable cards, and no suggestion or setup action can silently publish the recruiting protocol. Criteria editing now preserves recruitment context, decision policy, criterion metadata, criterion weights and assessment-stage membership when saving the Draft.

Integration separates immutable C08 source history from the current complete source hash inventory. Windows file-handle checks now enumerate real process handles through psutil instead of returning an empty Linux-only /proc result. A real SQLite open/close test runs on each OS. Probe errors fail the run rather than manufacturing PASS.

The current suite contains 138 tests. Runtime counts and results are emitted by CI for the exact commit. This document does not substitute for that evidence. Release identity is C11 throughout; historical C08 metadata is preserved under verification/history/convergence08.

## Delivery

CI uploads source ZIP, SHA-256 sidecar, regression log and installed dependency versions. The source ZIP records its exact commit and manifest hash. Portable/native artifacts remain unbuilt in this source line. Windows source verification is not WPF GUI acceptance.

## Remaining work, in order

1. Continue business workflow closure against v0.8.12-R2: project setup, intake, screening, evidence review, interview, decision, offer, operations and handoff must each be usable without API knowledge.
2. Run the end-to-end UI acceptance plan and convert every concrete workflow break into a product defect with a regression test.
3. Recover/audit the embedded runtime and five production Knowledge DB assets for a fresh Portable assembly.
4. Assemble with the exact Windows carrier and run target-machine GUI acceptance.
5. Validate external providers and an anonymized resume corpus with human review.
6. Restore additional high-value gates from the historical 725-test inventory while avoiding infrastructure work that does not close a user-facing workflow.
7. Decompose large workbench/frontend modules only behind preserved behavioral coverage.
8. Complete historical Git/Release privacy audit (private visibility alone is not that audit).

## Git and release workflow

main contains reviewed, merged source. Integration/fix branches use PRs and both OS gates. Require current source integrity, release binding, compile, JavaScript syntax and resource regression before promotion. Publish/tag only the exact verified commit; document source versus Portable versus Native artifact type. See docs/RELEASE_PROCESS.md.

## P1 active queue and calendar correction

Current decision-work items exclude archived projects and rank globally by explicit business priority, not task-type spelling. Project-level workbench lookup is scoped at query time. The operational queue applies host-local calendar midnight for today's contacts and limits each preview category separately before sorting. Windows user-flow/GUI acceptance remains pending.

## Exact review item navigation

Identity and judgment review dashboard links now carry review_id, and Claim review links carry claim_id. The destination focus routine locates the exact active record, scrolls to it and highlights it; it reports stale/missing targets instead of silently showing an unrelated list. This is frontend source coverage until real browser E2E acceptance.

## Windows Portable input readiness

Added a non-destructive, source-level Portable input preflight for the exact inherited Windows carrier SHA, embedded runtime entrypoint and five externally audited Knowledge hashes with SQLite integrity/table checks. It fails closed with a machine-readable report when files are absent or mismatched. No runtime/Knowledge bytes are stored in Git and no Portable/Native artifact is declared built. The external manifest's provenance and exact Windows GUI acceptance remain separate manual gates.

## Native assembly hardening

Fixed the legacy assembler's source-root wildcard copy that could accidentally include workspace data, backups and local secrets. It now stages only SOURCE_MANIFEST-listed reviewed source, the exact carrier's inherited Host and separately preflighted runtime and five production Knowledge DBs; output filenames reflect C11 and mark unverified GUI status. The PowerShell script uses hostExe instead of PowerShell's reserved Host variable. No actual native binary has been produced or GUI accepted in CI.

## C11 backup manifest and restore integrity

Integrated the previously isolated backup-integrity implementation into the real backup and startup restore paths. New backup archives contain a SHA-256 manifest for the SQLite snapshot and Source blobs. Restore validates structure, member hashes, SQLite integrity, schema, limits, and disallowed paths before extracting into a temporary staging directory; tampering leaves the current database and pending marker untouched. Legacy archives remain readable under a restricted DB/blob-only layout and explicitly report weaker integrity. Automated synthetic roundtrip/tamper/restore coverage is added, but interrupt/crash injection and Windows exact-artifact validation remain pending.

## Final Native ZIP payload closure

Native packaging now requires an external audited manifest for every embedded Runtime file, stages only those files, and audits the entire resulting candidate ZIP against source, Runtime, Knowledge, and Host digests. Unexpected members, file tampering, and falsely claimed GUI acceptance block candidate assembly. Synthetic regressions are cross-platform. Real production assets and WPF/WebView2 acceptance remain unavailable in this source checkout.

The assembler now uses PowerShell hash checks to stage an isolated Runtime and reviewed source before launching any embedded Python. The launcher self-check uses temporary data outside the release tree rather than creating staged user data. Tests protect this ordering and launcher import side effects.

## Chromium browser acceptance gate (verified on 69f60b9)

Added a separate Ubuntu real-Chromium/Playwright integration workflow, backed by a disposable local SQLite database and generated synthetic Knowledge fixtures. It exercises UI clicks through project creation, four-step Draft Job Setup, candidate text intake, action plan, interview scheduling and draft Offer, then checks persisted API results. This gate passed 3 Chromium workflows on exact main commit 69f60b9. WPF/WebView2 and real Windows Portable acceptance remain pending. See docs/BROWSER_ACCEPTANCE.md.

## Chromium-discovered candidate intake defect

The initial Chromium run exposed an HTTP 409 in candidate workspace when a newly collected and published material revision existed before job standards were published. This was incorrectly hidden as missing material by the UI. The read-only workspace now returns Source/Claim content and a blocked (empty) decision context until published protocol and material exist. Decision controls are disabled in that state; published-context calculation remains unchanged. Three additional source tests cover draft-only, post-publication and nonexistent candidate cases.

The second browser run also revealed that the Offer create button was shown for an ineligible new candidate. It is now disabled unless the candidate is in interview or offer stage; Chromium acceptance verifies genuine human new -> shortlisted -> interview transitions before saving an Offer Draft. The backend stage guard is preserved.

## 2026-10-18 GitHub repository governance and historical ZIP audit

The root README has been consolidated as the current user/developer entry point; docs/REPOSITORY_GOVERNANCE.md now records the single `main` source trunk, historical branches, module map, CI/evidence, artifact kinds and delivery blockers. docs/history/ARCHIVE_CATALOG.md and LEGACY_ARCHIVES.json record the four uploaded historical ZIPs' exact SHA-256/size and explicitly state that original archive bytes were NOT uploaded to GitHub. Three packages contain large Knowledge databases and an alpha Web Portable additionally contains executable Runtime components. No production database content was treated as cleared for publishing. A read-only ZIP safety/hash tool and four isolated tests were added. The historical 725 test inventory remains reference only; current regression count is now 113 (pending exact-commit verification on this change).

## 2026-10-18 Legacy external dependency recovery and alternative Host build

Actual user-uploaded alpha10 Web Portable contains 1,611 embedded Windows Python 3.12 Runtime files (99,144,143 uncompressed bytes), including the public certifi CA trust store. v0.8.12-R2 contains five intact Knowledge SQLite DBs: integrity_check=ok; their SHA-256 hashes match same-name DBs in v0.8.10 source and alpha10 Web Portable. Recovered contents/manifest have been delivered as a separate UNVERIFIED external inputs ZIP (not stored in Git). Embedded Python packages match only 5/13 pinned current C11 requirements; eight are missing/outdated, so Native preflight now explicitly rejects an incompatible Runtime before assembly. The four current user archives do not include a compiled Windows Host; v0.8.10 Assembler contains an Application Overlay, not the exact Windows Portable carrier. A new GitHub Windows Host source-build CI gate attempts an unsigned framework-dependent WPF/WebView2 Host compilation from locked .NET inputs. Compilation and WPF GUI acceptance remain separate; see docs/LEGACY_RESOURCE_RECOVERY.md.

## Alternative source-built Windows Native assembly

A second, separate Windows Native assembly path has been implemented using the digest-bound WPF/WebView2 Host candidate from GitHub's Windows Host build workflow rather than the exact historical v0.8.8 carrier. The new assembler requires an exact matching Git source commit, source SHA manifest, restored/runtime-upgraded Python pinned to current C11 requirements, five Knowledge SQLite databases, and matching Host build provenance. The finished ZIP is re-opened for an exact allowlist/hash audit and remains explicitly UNVERIFIED_GUI. Four synthetic packaging and privacy regression tests were added. The existing historic carrier inheritance path is preserved. This is an unverified candidate builder: the historical alpha10 Python dependencies still need compatibility updates before actual candidate packaging, and WPF/WebView2 GUI acceptance is separate.

## Offline Windows Python wheel overlay (pending exact-commit acceptance)

Created an independently checksum-bound Windows/Python 3.12 wheelhouse CI and a fail-closed offline Runtime upgrade utility. Original alpha10 Runtime and five historical Knowledge databases remain untouched. Upgraded packages reside under `Lib/c11-overlay`, which is inserted before legacy `Lib/site-packages` in `python312._pth`. The utility requires all C11 pinned metadata versions and executes actual isolated `python.exe` imports before emitting a new runtime SHA inventory and `RUNTIME_UPGRADE_AUDIT.json`. The alternate Native assembler now refuses an overlay with no matching C11 runtime smoke audit. Added 7 source regressions (125 -> 132). Wheelhouse CI smoke cannot validate a private recovered old Runtime until the same user recovery inputs are present on an authorized Windows execution environment; WPF/WebView2 GUI and provider-live acceptance remain pending.

## 2026-10-19: Actual assembled C11 Native candidate, static-verified and GUI-unverified

Using actual same-source d8d032d Actions source, Windows WPF Host, 13 locked Windows wheels and the user's uploaded historical Runtime/five Knowledge DBs, assembled `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip` (101617623 bytes; SHA-256 27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb). Legacy Runtime bytes remain preserved; offline target win_amd64 wheel overlay was installed separately, 13/13 pinned metadata matches, 2332 Runtime hashes and five SQLite DBs pass; audited final ZIP has exactly 2629 expected SHA-bound members. No Windows embedded interpreter or WPF GUI was executed in the Linux staging environment. New `scripts/verify_prepared_native.py` provides immutable on-target source+runtime+Host+Knowledge verification, actual Windows Python import smoke and synthetic backend Host ABI/loopback readiness, with evidence outside candidate root; GUI manual acceptance remains mandatory. Added 6 synthetic regressions (132 -> 138). See `docs/PREPARED_NATIVE_WINDOWS_ACCEPTANCE.md`.

## 2026-10-19 Windows x64 user-provided real backend smoke PASS

On an actual user Windows x64 machine, the pinned d8d032d prepared package passed 273 source, 2332 Runtime, 5 Knowledge, 13 dependency and 15 Host member integrity checks, then ran embedded CPython 3.12.10 importing 13 C11 libraries, launched the real SRW loopback backend in an isolated synthetic workspace and validated the Host ABI/runtime identity. The saved `C11-Windows-smoke.json` states `WINDOWS_BACKEND_SMOKE_PASS_GUI_PENDING` / `gui_accepted=false`. A subsequent invocation on the same extracted root returned unreviewed file delta; the initial import smoke did not use `-B`, so generated bytecode is the leading hypothesis, not independently proven until inspecting the delta. This patch suppresses interpreter bytecode writes for smoke and new WPF Host, reports exact unexpected/missing paths without relaxing fail-closed SHA allowlists, and rejects evidence overwrite before executing. Regression count 138 -> 141; Windows GUI, provider/OCR/ASR and business operations remain unaccepted. See docs/WINDOWS_FIRST_SMOKE_RESULTS.md.
