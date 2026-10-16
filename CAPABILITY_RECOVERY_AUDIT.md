# SRW 0.8.x Capability Recovery Audit — Convergence 08

## Development rule

v0.8.12-R2 remains the capability-completeness reference. Mature business capability is preserved first; UI simplification may hide complexity but must not delete evidence, lineage, privacy, calibration, operations, knowledge, intelligence, portability or release-verification semantics.

Target: **0.8.x capability density + selected v1 workflow improvements + clearer UI + stronger module boundaries.**

## Capability map

| v0.8.x capability family | Convergence 08 status | Current implementation / note |
|---|---|---|
| Current material / material revision truth | Recovered | versioned material source sets and current pointer |
| Evidence-first Claim → Fact → Judgment | Recovered | grounded review; Missing ≠ 0 |
| Source grounding / PDF viewer | Recovered and deepened | page/char/bbox grounding plus server-rendered highlighted PDF page |
| Privacy scoring view | Recovered | privacy projection in actual remote AI path |
| Candidate identity review / canonical merge | Recovered | review queue + preview + non-destructive canonical merge |
| Calibration / anchor cases / judgment review | Recovered | distinct second reviewer for Gold and correction queue |
| Ranked comparison | Recovered | only evidence-closed candidates are ranked |
| AI execution ledger | Recovered | provider/model/status/latency/hash/privacy metadata, no raw private payloads |
| Evaluation / judgment lineage | Recovered | carry-forward origin and source judgment lineage |
| Decision reaffirmation lineage | Recovered | context changes make old decisions historical; explicit human reaffirmation |
| Decision Operations lifecycle | Recovered | context-bound recommendations; human accept/start/complete; stale on context change |
| Formal feedback classification | Recovered | candidate facts / job requirements / conflicts + human review |
| Recruitment Planning | Recovered | HC/date/owner/channel plan and evidence/pipeline bottlenecks |
| Knowledge learning loop | Recovered | completed human-confirmed action → feedback draft → curation proposal |
| Controlled Knowledge Apply / rollback | Broadened in C08 | taxonomy role/specialization aliases + competency aliases; prepare/diff/digest/activate/exact rollback |
| High-risk Knowledge mutation | Guarded | CREATE_CANONICAL remains export-only |
| Recruitment Intelligence / sourcing channels | Recovered | measured funnel, cost, provenance, human-confirmation, market planning guardrails |
| ATS/channel import | Recovered | CSV Preview → digest-guarded atomic Commit |
| Market signals vs candidate scoring | Strengthened | market/channel signals remain planning-only |
| **Full project package portability** | **Recovered in C08** | project-scoped state + Source blobs; strict Preview/digest Commit; ID remap; historical contexts preserved |
| Five active Knowledge DBs | Preserved | inherited byte-for-byte from C07 at release build |
| Backup restore security | Strengthened | duplicate ZIP members, unsafe paths and expansion bounds rejected before SQLite read |
| CSV export security | Strengthened | Excel formula guards cover candidate and contact exports, including evidence summary fields |
| Verification / CI inventory | Recovered, parity partial | v0.8.12 725-test reference + **46 focused current tests** |
| Windows WPF/WebView2 Host ABI | Recovered | Host identity, runtime ready/info/shutdown and root frontend contract |
| Windows Host binary | Carrier-gated | exact v0.8.8 carrier required; no fabricated binary |
| Full v0.8.12 CI parity | Partial | remaining families are not falsely claimed executed |

## Convergence 08 correction

C08 restores two distinctions that were lost in the lean rewrite. First, provenance is useful only when a recruiter can inspect it, so PDF grounding now renders the verified evidence region rather than stopping at bbox metadata. Second, a project is a durable business object rather than a screen state: the new project package carries current project-scoped operational records and immutable source blobs together. On import all IDs are remapped, while old decision-context hashes remain historical; this deliberately forces reevaluation in the new context instead of manufacturing current truth.

Knowledge governance expands cautiously. Competency aliases are structurally simple enough for controlled apply, but canonical competency creation, profile mutation and other ontology-level writes remain export-only until their complete validation contracts are restored.

## Remaining recovery sequence

1. recover more high-value runtime/system/release gates from the 725-test reference;
2. broaden Controlled Knowledge Apply only where target-specific validation is complete;
3. deepen longitudinal ATS/source intelligence without feeding market signals into candidate scoring;
4. assemble with the exact v0.8.8 Windows carrier and run exact-artifact WPF/WebView2 smoke;
5. continue decomposing `fullworkbench.py` and legacy frontend only after capability parity is protected.
