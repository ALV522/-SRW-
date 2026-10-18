# E2 Controlled-Write Gate — Web/EXE Information Interoperability

## Prerequisite

E1 source-based Web acceptance has passed the scoped synthetic-data API,
Chromium and Windows source-startup checks. Real EXE/WebView2 acceptance remains
blocked on a usable current C11 Windows package.

E2 must not weaken or reuse the GET-only E1 bridge. E2 should be introduced as
a separate **synthetic-only experimental carrier**, on an isolated branch with
separate URL/port/process and disposable SQLite.

## Architectural finding

The current C11 endpoint for Candidate Action Plan is:

```
GET   /api/v1/candidates/{id}/action-plan
PATCH /api/v1/candidates/{id}/action-plan
```

The existing mutation is routed to `upsert_action_plan`. At present, the API
contract does not advertise an expected revision or `If-Match` CAS guard.
Consequently two open carriers could overwrite one another with stale updates.

This is manageable in a single-user modal but not a sufficient contract for
simultaneous Web + EXE writers.

## Phase E2a — synthetic-only two-client proof

- Start one real backend with disposable SQLite, like E1;
- open two independently isolated browser contexts (one imitates the desktop
  carrier, the other Web);
- test Action Plan GET/PATCH through the separate E2 bridge, **only against
  the synthetic backend started by the test harness**;
- prove a successful write by browser A appears in browser B after refresh;
- never start OCR/ASR or external AI in this gate;
- preserve audit fields and human-owned responsibility.

No real user workspace or existing EXE is eligible for E2a.

## Phase E2b — optimistic concurrency

Before allowing a real shared writable core, add a reusable write precondition:

1. Read entity state including an opaque revision or canonical `ETag`.
2. Submit mutation with the previously read revision.
3. Atomically verify the revision in the transaction.
4. Return `409 Conflict` or `412 Precondition Failed` when stale.
5. Refresh current state and require explicit operator reconciliation.
6. Append a durable audit event including actor, previous/current revision
   and reason where the domain requires it.

For human decisions, Claim review, Criterion Verification and Offer state
transitions, never allow silent last-write-wins.

## Phase E2c — carrier integration

The final Web and EXE should use the same backend command/API implementations.
Do not introduce Web-specific state mutation paths.

First operations to promote:
- Candidate follow-up/Action Plan;
- contact confirmation;
- Claim review and verification, only after CAS + audit gates.

Later operations:
- interviews/scorecards;
- manual decisions;
- protocol publication;
- identity merge;
- Offer state transitions.

Each must retain the existing business invariants, role boundaries,
decision-context hashing, explicit human actions and source/decision lineage.

## Real-time update channel

Start with re-fetch after every mutation. If simultaneous browsers become
routine, add a backend change cursor (or SSE) carrying only revision metadata.

A client seeing an update event should invalidate and re-fetch its view instead
of applying uncertain data from another carrier's local state.

## Trust and data layout

Same-machine Web + EXE: one writable SRW Core and one SQLite store. A second
SRW process must not bypass the EXE workspace lock.

Remote/private Web: a secured server-side Core with authorization and
network/TLS controls. That is a separate deployment/identity project.

Offline independent databases with two-way synchronization remain explicitly
out of scope. They would require durable entity IDs, replication metadata,
blob transfer, idempotency, conflict resolution and tombstone semantics.

## E2 completion criteria

- synthetic two-client writes persist and are visible in both views;
- a deliberate concurrent conflicting update is rejected;
- no unauthorized endpoint is reachable through the experiment;
- business actor/reason/audit survives restart;
- fail-closed on unsupported runtime/API schema versions;
- preserves Source/Claim/Judgment/Decision semantics;
- independent GitHub CI passes; no `main` mutation.

Only after this evidence should code be selectively reviewed for promotion
to the production Web + EXE development line.
