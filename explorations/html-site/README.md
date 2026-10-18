# SRW HTML Site Exploration

This directory is an isolated product experiment. It is intentionally **not part of the SRW release source, build, verification truth, portable assembly, or mainline delivery**.

Branch: `explore/html-site-prototype`

## Why this experiment exists

SRW already has a browser-rendered frontend, but the current product is still structured around the historical local application architecture: Python backend, static frontend assets, Windows host, and several generations of convergence code.

This experiment asks a narrower product question:

> Can SRW be presented and operated primarily as an HTML website-style application, while preserving the local-first database, OCR/ASR, AI provider, evidence provenance, audit and Windows portable capabilities?

The answer appears to be **yes, with an important qualification**: HTML can become the primary product surface, but a pure static HTML file cannot replace the local SRW service for SQLite, files, OCR/ASR, background jobs, provider secrets, Knowledge DBs and evidence provenance.

## Isolation contract

Nothing in this directory may be imported by production code.

This branch will not be merged into `main` as-is. Any idea that proves useful must later be reimplemented or selectively ported through an ordinary reviewed product branch.

No release identity files, source manifests, schemas, backend routes, portable manifests or current frontend files are modified by this exploration.

The current GitHub Source Gate is configured for pushes to `main` and pull requests targeting `main`. This branch therefore does not consume normal mainline CI unless a PR is deliberately opened.

## Prototype

Open `index.html` directly in a browser.

When opened from `file://`, it uses built-in mock data and behaves as a product concept prototype.

When served from the SRW application's own origin, it attempts to read `/api/v1/dashboard`. This is deliberately read-only in the experiment. No production mutation API is invoked.

## Questions being tested

1. Can the whole product feel like a coherent website instead of a desktop program with embedded pages?
2. Can navigation be simplified around recruiter jobs rather than internal modules?
3. Can Candidate Workspace become the central full-page object in the product?
4. Can local-first operation remain invisible to the user while the UI behaves like a modern web application?
5. Can we eventually make the same frontend usable in three carriers:
   - local browser,
   - Windows WebView2 shell,
   - optional remote/private deployment?
6. Which current capabilities are coupled to the Windows host and therefore cannot be moved into browser code?

## Preliminary conclusion

The technically sound direction is **not** "convert SRW into one giant standalone HTML file."

The strongest architecture is:

```
Browser / WebView2
       |
       | HTTP on loopback / same origin
       v
Static HTML + CSS + JavaScript
       |
       v
SRW Local Application Service
       |
       +-- SQLite
       +-- source/blob storage
       +-- OCR / ASR workers
       +-- AI providers and secrets
       +-- Knowledge databases
       +-- evidence / decision / audit services
```

This keeps the usability and portability advantages of a website while preserving the capabilities that made the 0.8.x line valuable.

## Current experiment status — E1 + E2 synthetic lab

**Verified** at exploration commit `0e8eacbd20ae3e609d3161c84910ddeec8a4b3ce`:
[isolated E1/E2 GitHub Actions](https://github.com/ALV522/-SRW-/actions/runs/39151649763).

- Ubuntu and Windows: **15 E1/package tests + 3 E2 guard tests** per OS, PASS.
- Real Chromium + C11 API + disposable SQLite: **9 tests**, PASS.
- Windows: actual `START_HERE.cmd --smoke` and `START_E2.cmd --smoke` executed successfully end to end, including E1's independent Python virtual environment.
- Published a SHA-256-inventoried complete source demo artifact with both launchers.
- E1 browser: cross-project candidates, candidate workspaces, mobile layout and direct URL history.
- E2: two real Chromium client contexts, one actual C11 Action Plan business write, second stale write rejected as HTTP 412, then refreshed second write succeeds; C11 audit events present.
- No official Native WPF/WebView2 C11 EXE, real Windows host acceptance or full 0.8.x parity is claimed.

## **Download the complete Windows demo ZIP (recommended)**

[Download the verified E1/E2 source demo artifact from GitHub Actions](https://github.com/ALV522/-SRW-/actions/runs/39151649763/artifacts/12144953435).

You need a logged-in GitHub account with access to this private repository.

1. Download the Actions artifact ZIP.
2. Extract the **whole ZIP** to its own folder.
3. Run **`START_HERE.cmd`** for E1 read-only real-core Web.
4. Optionally run **`START_E2.cmd`** for E2 **synthetic-only** Action Plan write-conflict lab.

Python 3.12 and internet for first-time pinned-dependency installation are required;
both launchers create a separate environment. No real user data is opened and
all sample SQLite/Knowledge records are disposable.

**Do not download only the nested launcher CMD.** The original user-reported
failure was reproduced in Windows CI and required both canonical source
packaging and Windows batch path fixes.

Instructions: [USER_ACTIONS_NO_EXE.md](USER_ACTIONS_NO_EXE.md).
Evidence: [E1_STATUS.md](E1_STATUS.md).
Synthetic E2 scope: [E2_STATUS.md](E2_STATUS.md).
Architecture: [DUAL_CARRIER_PRODUCT_CONTRACT.md](DUAL_CARRIER_PRODUCT_CONTRACT.md).

## Run E1 on Windows (same EXE, same database)

The EXE uses a **dynamically allocated loopback port**, recorded in the live
`data/app.lock/instance.json` lease. Do not assume port 8765.

1. Download the exploration branch into a directory **separate from your EXE/Portable installation**.
2. Keep a compatible SRW Windows EXE running.
3. Drag its `data` folder onto `run_e1_windows.cmd`, or double-click the BAT and provide that directory.
4. The bridge validates the EXE lease's port, version, instance ID, session ID and data-root identity against the running backend.
5. Only after validation, a browser opens with `LIVE · windows · GET-only`.

Or run it manually:

```powershell
py -3 serve_e1.py --data-root "C:\\Path\\To\\SRW\\data" --port 0 --open-browser
```

For a running non-EXE SRW local service, specify its actual port:

```powershell
py -3 serve_e1.py --upstream http://127.0.0.1:8000 --port 0 --open-browser
```

That last mode tests the Web surface but does **not** prove an EXE connection.

All bridge routes are GET/HEAD-only, explicitly allowlisted and served on loopback.
It cannot create a second SRW process or change the existing SQLite/Blob store.

Read **[USER_ACTIONS_WINDOWS.md](USER_ACTIONS_WINDOWS.md)** for the minimal steps
and what to report afterward. Do not share `instance.json` or real candidate data.

## Automated synthetic checks

An exploration-only workflow at `.github/workflows/html-site-sandbox.yml` runs
`python -m unittest discover -s explorations/html-site -p "test_e1*.py" -v`
on Ubuntu and Windows, using an entirely synthetic SRW-like HTTP fixture.
It never reads production data and is separate from mainline CI.

Passing synthetic tests is **not** a Windows EXE acceptance result.
