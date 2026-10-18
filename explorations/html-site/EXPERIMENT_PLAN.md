# Experiment Plan

## E0 — static concept · implemented

Deliverable: `index.html`.

Purpose:
- test website-style information architecture,
- test full-page Candidate Workspace,
- test responsive layout,
- test navigation language,
- keep all data mocked.

Exit condition:
- the prototype can be opened directly with no build tool,
- the core recruiting path is understandable without reading documentation.

## E1 — read-only live adapter · prototype implemented, runtime acceptance pending

Add an API adapter that, when served under SRW, reads:
- `/api/v1/dashboard`
- `/api/v1/projects`
- project pipeline endpoints
- candidate summary/workspace endpoints

No POST/PATCH/PUT/DELETE calls in E1. The current E1 client enforces same-origin GET-only access and falls back to mock data when the SRW service is unavailable.

Exit condition:
- the exploratory frontend can display a real local database safely.

## E2 — candidate workflow mutations

Only after E1:
- contact/action plan,
- Claim review,
- criterion verification,
- interview scorecard,
- human decision,
- Offer actions.

Each mutation must reuse current backend invariants rather than reimplementing them in JavaScript.

## E3 — parity audit

Compare the HTML-first surface against the v0.8.12-R2 capability reference and current C11.

A capability is not considered recovered merely because a button exists. The full workflow, persistence, provenance, error handling and restart behavior must work.

## Non-goals

This exploration does not:
- replace the Windows portable effort,
- replace the main C11 branch,
- change schemas,
- change release identity,
- change current APIs,
- create a hosted SaaS,
- remove the local backend.

## E1 acceptance still required

The code exists, but E1 is not complete until it is mounted under a real SRW local origin and verified against a real database. Acceptance should check:

- dashboard payload renders without mock fallback;
- project list loads from `/api/v1/projects`;
- project pipeline and candidate list render from real data;
- Candidate Workspace renders Sources, Claims and Criteria from the same records visible in the EXE;
- opening Web and EXE concurrently shows the same persisted state;
- no write request is emitted by E1;
- browser refresh/restart does not create divergent state.

## E1 Windows adapter hardening (implemented; acceptance pending)

- dynamic-port discovery from the Windows Host's `app.lock/instance.json`;
- exact backend instance/session/version/data-scope match required for EXE mode;
- loopback-only, GET/HEAD-only, route allowlist, no redirect following;
- minimal Windows launcher: `run_e1_windows.cmd`;
- synthetic HTTP/lease/security unit tests on an isolated workflow;
- explicit LIVE vs MOCK status in the HTML UI;
- user-run procedure: `USER_ACTIONS_WINDOWS.md`.

E1 is accepted only after live Windows EXE + browser inspection with identical candidate/project state. The synthetic tests do not substitute for that acceptance.

## Source-build E1/E2 package and E2a acceptance (verified)

At commit `0e8eacbd20ae3e609d3161c84910ddeec8a4b3ce`:

- complete package assembled with all required runtime Python sources, HTML, fixtures, manifests and pinned dependencies;
- top-level E1 `START_HERE.cmd` / E2 `START_E2.cmd` actual Windows launch paths passed;
- Chromium shows live C11 project/candidate data, handles deep links and mobile viewport;
- E2a two synthetic clients can update real C11 Candidate Action Plan through the isolated facade; stale ETag mutation returns 412 and does not overwrite prior owner;
- backend audit events were tested;
- E1 remains GET-only; E2 forbids all other mutations and is started only by the disposable synthetic harness;
- E2b production transactional CAS inside the SRW Core remains **not implemented**, and Native WPF/WebView2 plus production Knowledge acceptance remain open.

The accepted artifact is a source-demo ZIP with separate Python dependency setup, **not** a Windows runtime/EXE release.
