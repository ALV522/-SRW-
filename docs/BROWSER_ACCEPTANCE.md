# SRW Chromium business acceptance

This is a separate real-browser gate (three scenarios passed on main commit 69f60b9). It runs Chromium against the actual
Starlette HTTP server, distributed frontend JavaScript and a disposable SQLite
database. No HTTP responses or candidate/business actions are mocked.

## Scope

The initial real-browser acceptance covers:

1. Open the dashboard; create a recruiting project; use all four Job Setup
   wizard screens; save Draft; verify persisted recruitment context and that
   saving a draft did not publish it.
2. Create a candidate; publish pasted text material; verify Source persistence;
   save an operator-owned follow-up plan; create a draft Offer; verify that
   creating the Offer did not set pipeline stage to hired.
3. Schedule a candidate interview via the Process workspace and inspect the
   saved event using a real server API response.

Each case uses a new browser context and synthetic names. The server runs only
when SRW_SYNTHETIC_BROWSER_ACCEPTANCE=1, creates five minimal Knowledge
fixtures in a temporary directory, and must refuse an existing data directory.
No provider API key or production Knowledge is required. Tests do not send
private recruitment records to GitHub.

## CI command

The dedicated GitHub workflow installs pinned Playwright 1.56.0 and Chromium
on Ubuntu, then runs:

    python -m unittest discover -s browser_acceptance -p 'test_*.py' -v

Failures produce a synthetic server log and per-test screenshots in
artifacts/browser, uploaded from the matching exact commit. This workflow is
deliberately separate from the 106-test source/resource suite to avoid bringing
a heavyweight browser dependency into Windows source verification.

## Evidence boundary

This establishes selected Chromium UI/API/database click paths only. It does
not establish Microsoft WPF/WebView2 GUI behavior, external live AI/OCR/ASR
quality, full business regression, accessibility, or a packaged Windows build.
Do not label the 106 source tests plus Chromium cases as a percentage of
historical 725-test parity. This document does not claim the gate passed;
GitHub Actions on the exact source commit is the authority for that claim.

## Chromium-discovered regression

The first browser run identified that a candidate could upload text material before publishing the recruiting protocol, but the candidate workspace API returned HTTP 409 and the UI silently suppressed this failure. The acceptance fix preserves material visibility and the human decision gate: unpublished protocol means empty decision_context_hash, decision_ready=false, WAIT_FOR_INPUT and disabled decision submission. Browser and unit tests both cover this distinction.

## Offer creation and human Pipeline gate

Browser acceptance additionally checks that Offer creation is disabled before the candidate is in interview/offer stage, and that two deliberate human stage transitions (new -> shortlisted -> interview) enable the Offer Draft action. The server-side transition/Offer guard remains authoritative; a visible button may not bypass it.

## 2026-10-19 additional real browser scenarios

Two business workflow E2E tests are added: (04) independent immutable Interview Scorecards for two evaluators with preserved conflicting ratings, and (05) human Offer approval/send/accept transitions with illegal state skip rejected and no automatic hired/human decision. They use real Chromium UI interactions plus persisted C11 SQLite/API state, never fake API responses. Refer to [business scorecard/offer acceptance](BUSINESS_E2E_SCORECARD_OFFER.md). Five scenarios are **pending same-commit CI** until the new PR/main browser workflow is verified; the pre-existing three remain historical verified evidence. Desktop WPF/WebView2 business acceptance is separate.

## Protocol republish and stale human decision (E2E-07)

The additional Chromium acceptance creates a human-grounded Decision on a published project protocol, then **changes only the published protocol**, adding a mandatory verification-critical Criterion without changing candidate Source IDs. The prior Decision must become stale, the new criterion must block `advance` reaffirmation through both server API and UI until it is verified. This complements E2E-06 material-revision staleness. [Full test contract](BUSINESS_E2E_PROTOCOL_REVISION.md). It only counts as PASS after the corresponding exact-commit CI succeeds.
