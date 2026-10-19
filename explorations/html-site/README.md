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

## E1–E4 experiment: executable source-backed HTML site

All work is on the **isolated** `explore/html-site-prototype` branch.

| Experiment | Implementation | Verification boundary |
|---|---|---|
| E0 | Static single-file HTML Mock | Visual exploration, no real API |
| E1 | Real C11 + SQLite, GET-only Web UI | Identity, projects, candidates, Claim/Source read flows, mobile, browser history |
| E2 | Browser-only Action Plan PATCH via proxy lock | Synthetic two-client ETag conflict, **not transactional Core CAS** |
| E3 | Experimental C11 Core Action Plan route with SQLite `BEGIN IMMEDIATE` | Revision + business mutation + audit in one transaction, synthetic only |
| E4 | Independently-owned single Core with two detachable browser carrier origins | Same Core identity and SQLite across both UIs; detaching one doesn't stop the other |

The optional **Desktop surrogate** used by E4 is a second browser endpoint,
**not** Windows WPF/WebView2 Native. There is no accepted C11 EXE and
no production data migration.

### Download and run the complete Windows source demo ZIP

Open the [isolated E1–E4 GitHub Actions workflow](https://github.com/ALV522/-SRW-/actions/workflows/html-site-sandbox.yml).
Choose the **latest successful** run and download its artifact named
`SRW-HTML-E1-E4-WINDOWS-SOURCE-DEMO-<commit>`.

Extract the whole ZIP and run one of:

- `START_HERE.cmd`: E1 real-core read-only HTML site.
- `START_E2.cmd`: E2 synthetic proxy-level concurrent Action Plan editing.
- `START_E3.cmd`: E3 synthetic **atomic SQLite transaction** CAS.
- `START_E4.cmd`: E4 one independent Core + two browser carrier surfaces.

All four use disposable synthetic projects/candidates, Python 3.12,
an isolated virtual environment and pinned dependencies. First start
requires internet access; stopping the controller removes the temporary
workspace (with bounded retry for transient Windows file locks).

**The package is source code, not a Windows EXE or production Portable.**
The user does not need to upload a real database or launch any old EXE.

- [Windows instructions](USER_ACTIONS_NO_EXE.md)
- [E1 browser acceptance](E1_STATUS.md)
- [E2 proxy CAS limitations](E2_STATUS.md)
- [E3 SQL transaction proof](E3_ATOMIC_CAS.md)
- [E4 independent shared Core](E4_SHARED_CORE.md)
- [Target Web + EXE product contract](DUAL_CARRIER_PRODUCT_CONTRACT.md)

### Current acceptance evidence

At accepted code snapshot `2257195887bde102fd3ae77042c0e088cf039ffd`,
[GitHub Actions run 39189966339](https://github.com/ALV522/-SRW-/actions/runs/39189966339)
passed all jobs on Ubuntu/Windows and genuine Chromium.
It exercised 16 real Chromium tests, the Windows batch launchers,
independent SQLite connections, synthetic cross-carrier writes and
E4 Core detach/reattach lifecycle.

The [verified E1–E4 source ZIP](https://github.com/ALV522/-SRW-/actions/runs/39189966339/artifacts/12160145418) has now been published and its SHA-256 file inventory validated (184 files). Passing exploration tests does **not** certify
a Windows Native Host, full v0.8.x parity or real-corpus/provider quality.

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
