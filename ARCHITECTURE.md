# SRW Architecture Truth

## Product boundary

SRW is a local-first recruitment operations and decision-support workbench. `v0.8.12-R2` remains a capability-completeness reference, not the current source identity. UI or architecture simplification never authorizes removal of mature Evidence, Decision, Interview, Offer, Knowledge, AI/OCR/ASR, backup, privacy or provenance semantics.

The accepted architecture direction is defined by:

- [ADR-0001](docs/decisions/ADR-0001-single-authoritative-core.md): one authoritative Core for Windows and Local Browser;
- [ADR-0002](docs/decisions/ADR-0002-api-first-modular-monolith.md): API-first modular monolith and thin carriers;
- [API-first modular Core roadmap](docs/API_FIRST_MODULAR_CORE_ROADMAP.md): staged migration, not a rewrite.

## Architectural rule

**The Core is authoritative; clients consume contracts.**

```text
Windows WPF/WebView2       Local Browser       future CLI / Agent
          \                    |                    /
           +--------------- SRW API ---------------+
                              |
                     Application Use Cases
                              |
                           Domain
                              |
       +----------------------+----------------------+
       |                      |                      |
 SQLite / Blob          Jobs / Providers        Knowledge
       |                      |                      |
       +-------------- authoritative Workspace -----+
```

Business capabilities enter Domain/Application first, then receive an API contract, then are exposed by Windows/Browser clients. No carrier may become a second authority for Candidate, Evidence, Decision, Interview or Offer state.

## Logical layers

- `backend/srw/kernel`: IDs, hashing, clock and invariant primitives.
- `backend/srw/modules`: current domain/service foundation. Candidate, protocol, decision, identity, calibration, feedback, work, planning, knowledge and portability already live here; future changes should strengthen these boundaries instead of rebuilding them.
- future/gradual Application layer: operator use cases and transaction orchestration. It may be introduced incrementally around existing modules; a mass file move is not required.
- `backend/srw/api`: HTTP adapter/composition surface. It owns transport contracts, request/response serialization, errors, session/concurrency integration—not domain truth.
- `backend/srw/surfaces`: read-oriented projections/workspaces.
- `backend/srw/runtime`, `providers`, `evidence`, `importer`: infrastructure adapters for DB/schema, jobs, local boundary, backup, provider execution, grounding and intake.
- `frontend/dist`: retained Browser/WebView2 client. It will be decomposed behind a shared API client and feature boundaries without a framework rewrite.
- `desktop/SRW.Desktop`: Windows carrier. Its target responsibility is lifecycle, workspace/session, WebView2 and native integration, not recruitment rules.
- `convergence_tests`: source/API regression safety net.
- `browser_acceptance`: real Chromium operator-path evidence.
- `verification`: evidence records; historical evidence never becomes newly executed evidence.

## Current structural hotspots

On baseline `c0bc192e346ab16aeb6fa63e60a40c617274a188`:

- `backend/srw/api/fullworkbench.py`: ~126.8 KB / 1723 lines;
- `backend/srw/api/app.py`: ~38.6 KB / 737 lines;
- `frontend/dist/app.js`: ~128.8 KB;
- static scan of `backend/srw/api/*.py`: 141 `Route(...)` declarations / 129 distinct path templates.

These are migration targets, not evidence that the entire Core is unstructured. `backend/srw/modules/` already contains 17 business module directories. The required method is therefore gradual boundary extraction with preserved behavior.

## API contract boundary

Public interfaces correspond to operator/business use cases, not internal helper functions. Important mutations progressively document and test:

- request and response schemas;
- stable error semantics;
- resource/revision identity;
- CAS / If-Match / expected revision behavior;
- explicit human actor/confirmation requirements;
- audit and lineage effects;
- side effects such as Source, MaterialRevision, Job or Backup creation;
- local session/origin/privacy requirements;
- compatibility/deprecation policy.

A frontend may proactively disable an invalid action, but the Core must independently enforce the rule.

## Decision truth

The central semantic chain remains:

`Source → Claim → Evidence/Verification → Criterion Judgment → Assessment → Human Decision`

Important invariants:

1. Missing evidence is unknown, not zero.
2. AI proposals are not human decisions.
3. Material/protocol context changes make old judgments and decisions historical unless explicitly carried/reaffirmed under current gates.
4. Operational priority is not candidate ranking.
5. Market/channel intelligence is planning evidence, not candidate scoring input.
6. Privacy-safe AI projection is used on the actual remote-provider path.
7. Source grounding remains traceable to original material.

## One-workspace / one-writer authority

One SRW workspace has one authoritative Core writer and one authoritative Job Engine. Windows and Browser do not separately open the same SQLite for writes. Workspace lease, future Supervisor/session attachment, transaction revision/CAS, backup/restore interlocks and task idempotency are Core lifecycle concerns.

## Local security boundary

The HTTP surface remains local-only unless a future product decision explicitly changes scope. Local Host/Origin/session/CSRF protections must be enforced by the Core boundary. A loopback address alone is not an authorization model.

## Knowledge and provider boundary

Knowledge databases are governed artifacts, not UI-owned mutable scratch state. AI/OCR/ASR/embedding/document processing extend through code-level provider/capability contracts and the Job Engine. A dynamic plugin marketplace is not a current requirement, and no provider may bypass privacy projection, audit or HumanDecision boundaries.

## Refactoring policy

Use Strangler Refactoring:

1. inventory and contract-test current behavior;
2. migrate one business domain at a time;
3. keep URLs and Schema stable unless a separately approved migration requires change;
4. reuse existing domain/service/repository implementations;
5. run Source/API and applicable Chromium tests on the exact PR Head;
6. delete legacy aggregate code only after equivalent behavior is proven.

Do not build a parallel `new-core`, microservice set, second database, new frontend framework or separate repositories as prerequisites for this work.

## Release truth

`VERSION`, `BUILD_INFO.json`, `backend/srw/release_state.json`, `PORTABLE_MANIFEST.json`, `VERIFICATION_TRUTH.json` and Schema identity remain separately governed. Architecture changes do not imply a release promotion. Source, Browser, Windows WPF, Native/Portable and dual-carrier acceptance remain different claims.
