# E1 Verification Status — HTML-first Web / EXE Exploration

## Current state (2026-10-19)

**E1 source-based Web acceptance: PASS for the tested scope.**

This means the isolated HTML frontend has been exercised in real Chromium against
the genuine C11 Starlette API, disposable SQLAlchemy/SQLite state, and synthetic
Knowledge fixtures. It does **not** mean a production Windows EXE exists or
that the dual carrier has passed real Windows WebView2 acceptance.

### Verified source snapshot

- Exploration commit: `ef351c526172cd87bfb3f7f61f63f05642c8d59f`
- Sandbox workflow: https://github.com/ALV522/-SRW-/actions/runs/39148706985
- All jobs: **PASS**
- Ubuntu synthetic Bridge/security regression: **12 tests PASS**
- Windows synthetic Bridge/security regression: **12 tests PASS**
- Ubuntu Chromium + real C11 backend + temporary SQLite: **6 tests PASS**
- Ubuntu source-based Web demo smoke: **PASS**
- Windows source-based Web demo smoke: **PASS**
- Python source compilation and Node inline JavaScript syntax: **PASS**

The Chromium run saves screenshots from real rendered synthetic-data pages in
GitHub Actions' downloadable artifact:
https://github.com/ALV522/-SRW-/actions/runs/39148706985

### Tested behaviors

1. **Actual API integration:** E1 loads the live `/health/ready`,
   `/api/v1/info`, `/api/v1/runtime/info`, Dashboard, Projects,
   Project Pipeline, active Candidates, Candidate Workspace and Candidate Brief.
2. **Actual persistent data:** the test creates a project, two synthetic candidates
   and a source document through genuine SRW endpoints; these records appear in Chromium.
3. **Shared data authority:** an external direct backend mutation changes a
   candidate from `new` to `shortlisted`; after browser refresh, E1 shows
   the changed stage from the same SQLite store.
4. **Cross-project directory:** real candidates from two projects can be
   searched/filtered and opened, using only existing project-scoped APIs.
   Client aggregation is explicitly capped at 500 visible candidates.
5. **Read-only guarantees:** bridge denies mutation methods, unlisted GET APIs,
   cross-site Origin/Host, wrong desktop lease, and upstream redirects.
6. **HTTP/1.1 regression:** rejected POST bodies no longer corrupt subsequent GETs.
7. **Mobile layout:** home, candidate directory and Candidate Workspace have
   no page-level horizontal overflow at a tested 390px viewport.
8. **EXE-free demo:** the source-only launcher starts a genuine C11 backend with
   disposable demo records and verifies live Web reads before exiting.
   The same smoke procedure passed on Ubuntu and Windows CI.

## Actual deliverables

- `index.html` — E0 single-file Mock design;
- `e1-live.html` — E1 real read-only Web UI;
- `serve_e1.py` — identity-protected loopback GET-only bridge;
- `run_e1_windows.cmd` — attach to a compatible existing Windows EXE;
- `run_e1_demo.py` — launch a genuine SRW backend using synthetic temporary data;
- `run_e1_demo_windows.cmd` — Windows script preparing its own Python 3.12
  virtual environment and opening the source-based Web demo;
- `test_e1_bridge.py` — 12 synthetic bridge/security/lease tests;
- `browser_acceptance/test_real_backend.py` — six real Chromium/API/SQLite tests;
- `DUAL_CARRIER_ARCHITECTURE.md` — long-term Web + EXE shared-core contract.

## What remains *unverified*

- real C11 Windows EXE/WPF/WebView2 GUI launch;
- E1 attached to an actual EXE's dynamic-port lease and verifying the same
  instance / session / data-scope ID;
- native runtime and production Knowledge packaging and trust;
- business-write flows in E1 (intentionally disabled);
- WebView2 concurrency and lifecycle with browser open simultaneously;
- full v0.8.x business parity, external live AI/OCR/ASR quality, and real-corpus quality;
- multi-device/private-server authentication, authorization and event-driven updates.

## Engineering boundary

No E1 code has been merged into `main`. Only exploration files and a branch-
specific GitHub Actions workflow were added. Normal mainline release, manifests,
schemas, frontend and backends remain untouched.

The primary next engineering gates are:
- E2 isolated controlled-write **design**, including optimistic concurrency
  and a reviewable allowlist (no production writes before review);
- distinct Web and EXE carrier contracts with data-scope/session identity;
- Windows Native packaging/executable validation when an accepted EXE exists.

## User action

**None required right now.**

If you want to evaluate the Web UI without waiting for the C11 EXE, follow
[USER_ACTIONS_NO_EXE.md](USER_ACTIONS_NO_EXE.md). You need Python 3.12 and internet
for first-time installation of pinned dependencies inside a separate exploration
virtual environment. All demo records are synthetic.

If a compatible C11 Windows EXE becomes available later, follow
[USER_ACTIONS_WINDOWS.md](USER_ACTIONS_WINDOWS.md) to verify true dual-carrier
interoperability without launching a competing SRW backend.
