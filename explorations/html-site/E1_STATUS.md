# E1 Verification Status — HTML-first Web / EXE Exploration

## Current scope

E1 is a read-only experiment on the isolated branch `explore/html-site-prototype`. It does not modify SRW production code or its Windows carrier.

The experiment now implements:

- E0 standalone HTML Mock prototype (`index.html`);
- E1 real SRW GET adapter (`e1-live.html`);
- live Product/Runtime instance identity validation in the browser;
- Windows Host dynamic-port discovery via `data/app.lock/instance.json`;
- EXE identity binding: instance, session, version and data scope;
- isolated loopback same-origin bridge (`serve_e1.py`);
- strict GET/HEAD and explicit API route allowlist;
- upstream redirect denial and proxy disabling;
- Windows entry script (`run_e1_windows.cmd`);
- synthetic end-to-end HTTP fixture/unit tests (`test_e1_bridge.py`);
- Windows user procedure (`USER_ACTIONS_WINDOWS.md`).

## Automated evidence (isolated sandbox workflow)

**PASS** — GitHub Actions run [39146507199](https://github.com/ALV522/-SRW-/actions/runs/39146507199).

- Ubuntu Python 3.12: **11 tests PASS**.
- Windows Python 3.12: **11 tests PASS**.
- Python compile checks PASS.
- E1 embedded JavaScript parses with Node 22.
- GET-only route, Host/Origin denial, dynamic EXE lease matching, redirect denial, project/candidate synthetic reads were exercised.
- No production data or provider secrets used.

This is not a claim that the Windows EXE GUI has been validated. This workflow runs independently of normal `main` CI, and documentation-only changes do not trigger it.

## Still awaiting real Windows runtime acceptance

- actual C11-compatible EXE launched with its correct data root;
- E1 attached to that EXE through its live lock file;
- E1 banner reads `LIVE · windows · GET-only`;
- Project and Candidate Workspace state matches what the EXE shows;
- EXE-side ordinary business change becomes visible after Web refresh;
- no duplicate SRW process/database/service started;
- Windows user action recorded in `DUAL_CARRIER_TEST.md`.

**Important:** The repository mainline's source/Chromium CI does not imply the current C11 Windows Native executable has passed production acceptance. Older v0.8.x carriers may not expose the full E1 v1 APIs.

## Next engineering gate

After real E1 acceptance, E2 may add a very small set of controlled mutations with concurrency protection and an audit trail. Do not activate Web Claim/Decision/Offer writes until that gate is met.

## User action

Follow [USER_ACTIONS_WINDOWS.md](USER_ACTIONS_WINDOWS.md).

If you have a compatible running EXE, open it and run the isolated `run_e1_windows.cmd` against the EXE's `data` folder. Report only the LIVE/MOCK badge and any redacted error.

If you have no compatible C11 Windows EXE, simply report that. We can test against a local source-run SRW service first. Do not attempt to force an old runtime/database into the new release.
