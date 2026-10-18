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

## Current experiment status

- E0 static standalone prototype: implemented in `index.html`.
- E1 read-only live adapter: implemented in `e1-live.html`.
- E1 is intentionally GET-only and contains no mutation API calls.
- Web + EXE interoperability architecture is documented in `DUAL_CARRIER_ARCHITECTURE.md`.
- E1 API ownership/safety boundary is documented in `E1_API_MATRIX.md`.

The E1 JavaScript has been syntax-validated. It has **not yet been accepted against a running Windows SRW instance**, because this exploration branch does not alter the mainline backend/static mount. Live runtime acceptance is therefore still pending.
