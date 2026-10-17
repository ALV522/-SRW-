# SRW Development State — Convergence 11

Version: `1.0.0-alpha10-convergence11`; schema `v1_0014`; capability reference `v0.8.12-R2`.

## Integrated capabilities

C08 business capabilities are retained. C09 supplies local-only Host and browser same-origin checks, known interrupted-backup cleanup, structured diagnostics, independent synthetic Knowledge fixtures, SQLite shutdown disposal and Ubuntu/Windows Python 3.12 regression gates. C10 adds a privacy-safe deterministic diagnostic support bundle with explicit exclusion of candidate content, Source blobs, database bytes, provider secrets and local filesystem paths. C11 changes the center of gravity from infrastructure to product workflow: the home dashboard now surfaces the decision workbench as an actionable queue, deduplicated to the highest-priority open action per candidate, and routes the operator directly into candidate evidence/decision or interview work.

Integration separates immutable C08 source history from the current complete source hash inventory. Windows file-handle checks now enumerate real process handles through psutil instead of returning an empty Linux-only /proc result. A real SQLite open/close test runs on each OS. Probe errors fail the run rather than manufacturing PASS.

The current suite contains 71 tests. Runtime counts and results are emitted by CI for the exact commit. This document does not substitute for that evidence. Release identity is C11 throughout; historical C08 metadata is preserved under verification/history/convergence08.

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
