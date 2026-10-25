
> **G1 Local Web 入口**：本轮 Chromium E2E 使用 `scripts/start_local_web.py --synthetic --no-browser`，对真实 C11 Core+SQLite 操作；只能据准确 SHA 的 CI 判定 PASS。它不是 Windows WPF、正式独立 Web Portable、双端并发或真实 Provider 验收。

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

## Known flake: criterion row count after clicking "添加标准" (2026-10-21)

`test_07_published_protocol_change_invalidates_previous_human_decision` failed **once on main** `ce41239a860aff1ec2c2dc00ed030788c5af47ae` with `AssertionError: 1 != 2`, i.e. `.criterion-row` was expected to reach two rows after the add-criterion interaction and only one was present.

Investigation, in order:

1. The **same tree** had passed `chromium-real-browser-ubuntu` on PR head `f186e857fc633fb07b24bb7ca0bc007c39a11cd3`, so the merge itself introduced no behavioural change.
2. `POST /actions/runs/39636651612/rerun-failed-jobs` re-ran only the failed job and it passed. Main is green at that commit.
3. The failing step is `Run real-browser recruitment workflow acceptance`; the assertion is a row-count expectation immediately after a UI action whose persistence is asynchronous.

Classification: **timing flake in the acceptance test, not a product regression**. Recording it here rather than silently re-running, because a suite that intermittently reddens main erodes the value of every other green result.

Stabilisation direction (not yet implemented, needs its own PR with a browser re-run):

- Do not assert a container count immediately after a mutating click. Wait for the specific new row (by its label) or for the save acknowledgement the way #67 did for criteria persistence.
- Where a count assertion is unavoidable, first wait for the request that creates the row to settle, then assert the count.

Until that PR lands, treat a lone `1 != 2` on this test as a known flake **only after** confirming the same tree passed on the PR head or on a rerun; never fold it into a PASS claim without that evidence.

## Same test, second occurrence — and the fix (2026-10-25)

`test_07` reddened main `e663a383fe5e73571244ac0f990dd91fac7d6631` again with `AssertionError: 1 != 2`, this time on a **docs-only PR (#102, +89/−1)**, so the merge provably introduced no behavioural change.

Root cause is different from the 2026-10-21 occurrence and worth separating:

- the failing assertions were `len(draft.criteria) == 2` and `len(current.criteria) == 2`, read through the test process immediately after a UI save;
- the test deliberately installs a fetch shim that **delays the next draft PATCH by 300 ms** to prove the publish button is usable while a write is in flight. That delay widens exactly the window in which a single read can sample pre-write state;
- Playwright's `expect(...).to_have_count()` retries, so row-count assertions were never the problem here; plain `assertEqual` on a freshly fetched JSON body does not retry.

Fix shipped in the same PR as this note: `wait_for_json(path, predicate, timeout=8s)` polls the durable server state and fails with the last payload when the state never arrives. The assertion is not relaxed — a draft that permanently holds one criterion still fails, but the failure now says so explicitly instead of printing `1 != 2`.

Verification on the exact patch: `test_07` 3/3 consecutive passes; full browser suite 13/13 in 24.7 s locally.

Rule for future acceptance steps: **after a mutating UI action, never sample a JSON body once and assert a count.** Either await the specific response, or poll the durable state with a bounded timeout that reports the payload.

