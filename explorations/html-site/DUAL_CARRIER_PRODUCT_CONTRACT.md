# Dual Carrier Product Contract — Shared SRW Core, Web + Windows EXE

Status: architecture exploration. This document describes a target, **not**
an accepted Windows Native product or production service implementation.

## Core design conclusion

SRW can ship both a browser-based Web edition and a Windows EXE edition while
retaining one source of truth for recruiting records, raw materials, AI/OCR/ASR
jobs, Knowledge databases and human decisions.

On one machine, **one live SRW Core process must own the data directory**. The
browser and WebView2 are presentation clients of that same process, not two
independent SRW engines writing the same SQLite files.

## Current desktop lifecycle problem

Current Windows WPF Host implementation:

```
HostController.StartAsync()
  WorkspaceLease.Acquire(...)
  PortAllocator.AllocateLoopback()
  BackendProcess.Start(...)
  WebView2 -> http://127.0.0.1:<port>/

HostController.StopAsync()
  RequestShutdownAsync()
  terminate backend if needed
  WorkspaceLease.Dispose()
```

This is correct for a desktop application owned exclusively by its GUI, but it
is **not yet sufficient for independent Web + EXE co-existence**.

If a user opens the browser and then closes the EXE, the host currently shuts
down the backend, and the browser loses the shared Core. E1/E2 source tests do
not prove that this lifecycle problem has been solved.

There must be an explicit ownership decision before shipping dual carriers.

## Deployment option A — EXE owns backend (near-term simple)

- Windows EXE starts Core, holds exclusive data workspace lock.
- Browser attaches as a secondary client while EXE is running.
- Closing EXE intentionally stops the service; Web shows a reconnect screen.

Pros: no new supervisor or resident background process.

Cons: Web edition depends on EXE being open. This is an intermediate
coexistence mode, not independent Web + EXE availability.

## Deployment option B — detached local Core supervisor (preferred long-term)

- A dedicated local Core process acquires the workspace lease and owns SQLite.
- Both Web Browser and Windows EXE attach as clients.
- Closing EXE does not necessarily terminate Core if browser sessions remain.
- A tray/daemon/controller owns shutdown, migrations, upgrades and diagnostics.
- The EXE becomes a WebView2 carrier, plus native integrations.

Pros: genuinely independent carrier lifetimes, one database, one worker
scheduler and one Knowledge runtime.

Cons: requires process supervision, authenticated attach protocol, orphan
cleanup, upgrades, lock ownership and carefully bounded idle shutdown.

E4 has now proved a **synthetic independent-Core owner** with two detachable
browser origins and one SQLite store. This is not a production background
service, an accepted Windows Native Host or an authenticated attach protocol.
Do not promote the E4 controller to production before native packaging,
workspace lock supervision, API authorization and real GUI acceptance.

## Local service identity and trust

A local SRW Core needs:

```
RuntimeIdentity {
  product: SRW,
  release_id,
  core_version,
  schema_revision,
  instance_id,
  session_id,
  data_scope_id,
  api_contract_version,
  authenticated_attach_protocol_version
}
```

Two carriers may share a session only if their runtime identity, API version,
data scope and authorizations match. A second incompatible backend must be
rejected, not silently started against the same database.

The current EXE `app.lock/instance.json` already provides a useful port /
instance identity mechanism. E1 reads and cross-checks that metadata but
does not mutate it.

**Do not expose session tokens or raw lock metadata in Web pages, screenshots,
logs or downloadable support bundles.** Authenticated browser attach should
use a short-lived capability/session with local origin protection.

## Single source of truth

Authoritative business records:

- Project, Protocol Revision, published criteria;
- Candidate and identity lifecycle;
- Source, Material Revision, Blob and privacy projection;
- Claim confirmation and evidence lineage;
- Criterion Verification, Judgment and recalibration;
- Interview event and submitted Scorecard;
- Human Decision and Decision Context;
- Offer, contact and Candidate Action Plan;
- Knowledge DB identities, selection and rollback;
- task queues, OCR, ASR, AI provider execution and audit.

The browser and EXE may hold temporary UI state, but must never write an
independent persistent business database and then attempt naive replication.

## Concurrency and audit contract

E2a provides an experimental `ETag` + `If-Match` guard around synthetic
Action Plan mutations. It serializes writes made *through the single E2
facade instance*. It does not protect against a direct backend writer
interleaving between E2 read and write.

E3 now separately demonstrates the next step **in a disposable real C11 Core**:
a synthetic Action Plan route uses SQLite `BEGIN IMMEDIATE` to verify a
persistent version, execute the existing business mutation and append its audit
record, then advance revision in **one transaction**. Two independent
SQLite Engine connections compete for the same version; one succeeds and the
other fails without a successful audit. It is not merged into the mainline
or exposed for real production data.

Production still must move the precondition into the **official** Core schema
and every business mutation path, with an additive model/API revision contract:

```
GET /api/v1/candidates/{id}/action-plan
ETag: "revision-17"

PATCH /api/v1/candidates/{id}/action-plan
If-Match: "revision-17"
{...}

=> HTTP 200 and ETag "revision-18", or HTTP 412 with no mutation
```

The DAL must atomically compare and increment a persistent revision. Audit
must record the actor and mutation only when that transaction commits.

A rejected conflict must not alter contact state or append a fake successful
business event. Human Decision, Offer transitions, merge and protocol publication
have higher-integrity semantics and require separate domain-specific guards.

## Cross-carrier refresh

Phase 1: a carrier re-fetches the affected read model after its own mutation
or after the user requests Refresh.

Phase 2: one Core provides a change cursor / SSE stream with entity type, ID
and revision. Clients invalidate data and fetch fresh read models.

Do not send private candidate details or AI provider credentials on a general
broadcast channel.

## Deployment modes

| Mode | Web | EXE | State authority |
|---|---|---|---|
| E1 isolated demo | read-only | no | disposable local Core |
| E2 isolated lab | synthetic Action Plan with proxy ETag | no | disposable local Core |
| E3 isolated lab | synthetic Action Plan with SQLite CAS | no | disposable local Core |
| E4 lifecycle lab | browser carrier | browser surrogate (not EXE) | one independent disposable Core |
| Desktop-owned Core | secondary | primary | EXE-owned local Core |
| Detached local Core | independent client | independent client | supervised local Core |
| Private server | authenticated network client | optional client | authenticated server Core |

Remote browser clients require TLS, authentication, explicit authorization,
CSRF/origin policy, workspace tenancy isolation, secure file access and a
privacy/compliance review. Merely opening a loopback port to the LAN is unsafe.

## Packaging boundary

Future artifacts should have separate, precise names:

- SRW Core (shared business service/source);
- SRW Web Edition (HTML/browser carrier + Core installer);
- SRW Windows Edition (WebView2 EXE + Core/runtime);
- SRW Synthetic Demo Source Bundle (experiment only).

The successful E1–E4 CI source package is **not** a Windows Native release,
even though its launchers run on Windows. E3/E4 prove SQLite transactional
concurrency and independent process ownership in disposable sandboxes, not
Windows WPF/WebView2 integration.

## Exit criteria for genuine dual-carrier acceptance

1. Embedded runtime, production Knowledge and Windows Native Host accepted.
2. One SRW Core with a known lock and data scope.
3. Browser and WebView2 attach to the exact same runtime identity.
4. Candidate, Source, Claim and criteria state identical in both.
5. A cross-carrier write is visible to the other client after refresh.
6. A stale concurrent write fails without mutating state or audit.
7. Browser remains usable across EXE close when detached Core mode is chosen.
8. Kill/restart, shutdown and crash recovery preserve DB and Blob consistency.
9. OCR/ASR/AI jobs are scheduled once, irrespective of carrier count.
10. No capability loss against the mature 0.8.x business reference.

Until all relevant items are evidenced, describe the current result as
HTML-first exploration / source-based browser acceptance rather than a
completed dual-carrier product.

## Evidence and remaining integration boundary

- [E3 experimental SQLite transaction](E3_ATOMIC_CAS.md)
- [E4 independent Core/dual browser carrier lifecycle](E4_SHARED_CORE.md)
- [Independent source CI and browser screenshots](https://github.com/ALV522/-SRW-/actions/runs/39189540086)

**Design progression:** E1 tests read API sharing; E2 tests conditional writes at the proxy; E3 moves conditional revision + C11 business/audit into a real SQLite transaction under a synthetic route; E4 proves UI processes can attach to one independently-owned Core and detach separately. None of these substitutes for accepted WPF Windows Native packaging, production Knowledge DBs, full 0.8.x feature coverage or production data migration.
