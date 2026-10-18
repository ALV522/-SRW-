# Experiment Plan

## E0 — static concept

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

## E1 — read-only live adapter

Add an API adapter that, when served under SRW, reads:
- `/api/v1/dashboard`
- `/api/v1/projects`
- project pipeline endpoints
- candidate summary/workspace endpoints

No POST/PATCH/DELETE calls in E1.

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
