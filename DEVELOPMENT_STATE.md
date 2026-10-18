# SRW Development State — Convergence 11

Version: `1.0.0-alpha10-convergence11`; schema `v1_0014`; capability reference `v0.8.12-R2`.

## Integrated capabilities

C08 business capabilities are retained. C09 supplies local-only Host and browser same-origin checks, known interrupted-backup cleanup, structured diagnostics, independent synthetic Knowledge fixtures, SQLite shutdown disposal and Ubuntu/Windows Python 3.12 regression gates. C10 adds a privacy-safe deterministic diagnostic support bundle with explicit exclusion of candidate content, Source blobs, database bytes, provider secrets and local filesystem paths. C11 changes the center of gravity from infrastructure to product workflow: the home dashboard now surfaces the decision workbench as an actionable queue, deduplicated to the highest-priority open action per candidate, and routes the operator directly into candidate evidence/decision or interview work. The same dashboard now surfaces overdue and same-day candidate contacts plus completed interviews missing submitted feedback, with direct navigation back into the operational action. A unified review center makes pending identity reviews, judgment-correction reviews and unreviewed evidence claims actionable from the home screen. Judgment-correction review is now end-to-end: candidate context is visible and an operator can explicitly resolve the item with a required review note. Project home also derives one explicit next action from current business state, reducing the need to interpret internal modules or hunt across tabs. Candidate brief and project handoff views now present readable business summaries with a full JSON handoff download retained for transfer/audit; dashboard contact actions open the specific candidate action plan rather than a generic queue. The candidate workspace has been promoted from a modal into a full project surface with separate Evidence & Decision, Process & Follow-up, and Offer modes, while preserving the existing evidence, verification, decision, intake, OCR/ASR and Offer actions. Candidate-specific phone screens, interview scheduling/completion, independent Scorecards and reevaluation drafts are now directly available in Process & Follow-up. Job setup is now a true four-step guided Draft flow; state is preserved across steps, suggestions are rendered as readable cards, and no suggestion or setup action can silently publish the recruiting protocol. Criteria editing now preserves recruitment context, decision policy, criterion metadata, criterion weights and assessment-stage membership when saving the Draft.

Integration separates immutable C08 source history from the current complete source hash inventory. Windows file-handle checks now enumerate real process handles through psutil instead of returning an empty Linux-only /proc result. A real SQLite open/close test runs on each OS. Probe errors fail the run rather than manufacturing PASS.

The current suite contains 109 tests. Runtime counts and results are emitted by CI for the exact commit. This document does not substitute for that evidence. Release identity is C11 throughout; historical C08 metadata is preserved under verification/history/convergence08.

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

## Chromium browser acceptance gate (proposed)

Added a separate Ubuntu real-Chromium/Playwright integration workflow, backed by a disposable local SQLite database and generated synthetic Knowledge fixtures. It exercises UI clicks through project creation, four-step Draft Job Setup, candidate text intake, action plan, interview scheduling and draft Offer, then checks persisted API results. This gate must pass on the exact PR and main commits before a browser-acceptance claim; WPF/WebView2 and real Windows Portable acceptance remain pending. See docs/BROWSER_ACCEPTANCE.md.

## Chromium-discovered candidate intake defect

The initial Chromium run exposed an HTTP 409 in candidate workspace when a newly collected and published material revision existed before job standards were published. This was incorrectly hidden as missing material by the UI. The read-only workspace now returns Source/Claim content and a blocked (empty) decision context until published protocol and material exist. Decision controls are disabled in that state; published-context calculation remains unchanged. Three additional source tests cover draft-only, post-publication and nonexistent candidate cases.
