# E2 Status — Synthetic-Only Two-Browser Action Plan Concurrency

## Purpose

Prove the data-sharing topology for a future SRW Web and Windows EXE edition
without modifying the existing production backend, schema, releases or any
real user data.

E2a is an isolated laboratory. It reuses the **real** C11 Action Plan business
endpoint and its native audit behavior, but runs that Core only against a
one-time SQLite database containing synthetic candidates.

## Verified at commit 481162b65ffb612fd4509a76647c0b0e50302c6a

Source evidence: https://github.com/ALV522/-SRW-/actions/runs/39152520579

- Two independent Chromium browser contexts connect to the same disposable
  SRW backend and load the same candidate Action Plan.
- Both receive an `ETag` derived from the same current plan representation.
- First browser sends `PATCH` + `If-Match`, succeeds, persists through the
  actual C11 Action Plan endpoint, and appends a business audit event.
- Second browser sends the now-stale `If-Match` and receives HTTP **412**,
  leaving the winning write intact.
- Second browser re-fetches and saves successfully with a fresh version.
- Missing preconditions return HTTP **428**.
- Other candidate IDs, unrelated writes and unlisted/privileged GETs are
  rejected by the exploration bridge.
- Four E2 guard tests per OS and three dedicated E2 Chromium tests passed (two-client conflict, write allowlist and 390px responsive layout). Runtime smoke checks succeeded on Windows and Ubuntu.
- Windows batch entry `START_E2.cmd` executed from the actually assembled
  source demo package in CI.

## Not yet suitable for real users

The E2 proxy uses a per-process lock to serialize writes routed through E2.
It is **not a transactionally guarded SRW Core write**.

A direct current C11 backend client could write between E2's validation GET
and PATCH. Therefore E2 is NOT safe as a production multiwriter concurrency
contract, despite passing its isolated two-browser tests.

For real Web + EXE shared writes, the SRW Core must own persistent
`revision` / ETag updates, enforce the precondition atomically inside the
same transaction as business mutations, and audit only committed writes.

This distinction is fundamental: **E2a proven** does not imply **E2b done**.

## Source layout

- `e2_synthetic_bridge.py` — strict ID allowlist, ETag precondition and proxy lock;
- `e2-live.html` — website UI with conditional Action Plan form and conflict UX;
- `run_e2_demo.py` — creates disposable SRW backend and two fake candidates;
- `test_e2_synthetic.py` — fast E2 HTTP precondition/security tests;
- `browser_acceptance/test_e2_real_backend.py` — actual Chromium two-client tests;
- `START_E2.cmd` — Windows package entry, uses the same independent Python venv.

## Next milestones

1. Design and implement backend-owned revision CAS in a separate reviewed
   mainline development branch once native Core schema migration is ready;
2. Keep all E2 synthetic workloads isolated until the new transaction contract
   passes negative/stale/idempotency/audit tests;
3. Explore change-notification events/SSE only after conditional writes are sound;
4. Later attach a real Windows C11 EXE to one SRW Core, checking instance /
   data-scope identity and process lifecycle.
