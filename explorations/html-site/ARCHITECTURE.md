# Architecture Exploration: HTML-first SRW

## 1. What "HTML website form" can mean

There are four materially different interpretations.

### A. One standalone HTML file

All CSS and JavaScript are embedded in one `index.html`. Data is stored in browser storage.

This is attractive for demos and zero-install prototypes, but it is **not a credible production replacement for SRW**. Browser storage is a poor fit for resume files, SQLite-compatible transactional state, long-running OCR/ASR jobs, provider credentials, backup/restore and evidence lineage.

Use case: product concept, demo, interaction testing.

### B. HTML frontend + local SRW service

The user sees a normal website. The page is served by SRW at a loopback address such as `http://127.0.0.1:<port>/`. The browser communicates with the existing backend through same-origin HTTP APIs.

This is the preferred production direction.

It gives:
- normal browser navigation and layout,
- no CORS problem when served same-origin,
- local data ownership,
- existing Python business logic,
- existing SQLite and blob storage,
- existing AI/OCR/ASR integrations,
- compatibility with Windows WebView2,
- a path to optional remote deployment later.

### C. Installable PWA

The B architecture can later add a manifest and service worker.

This may improve launch behavior and offline static-asset caching, but it does not eliminate the backend. It should be considered only after the web product surface stabilizes.

### D. Fully hosted SaaS

The same HTML frontend could eventually point at a remote API, but this changes the privacy, authentication, tenancy, compliance and deployment model. It is a different product decision and should not be smuggled into the current local-first work.

## 2. Important discovery from the current codebase

SRW is already closer to architecture B than it may appear.

The current production frontend consists of an HTML entry page plus static CSS and JavaScript files served by the application. The Windows host is therefore already acting partly as a carrier around a web UI.

The architectural question is not "can SRW use HTML?" It already does.

The useful question is:

> Can we make the HTML/browser surface the canonical product, with the Windows shell becoming only one carrier?

That is technically plausible and strategically useful.

## 3. Recommended target structure

```
srw-web/
  index.html
  assets/
  app/
    router.js
    state.js
    api.js
    views/
      dashboard.js
      projects.js
      candidate-workspace.js
      interviews.js
      offers.js
      review-center.js
      settings.js
    components/
      action-queue.js
      evidence-viewer.js
      status-chip.js
      modal.js
```

The current monolithic `frontend/dist/app.js` should not be copied into this structure wholesale. The exploration should first prove page structure and navigation. Decomposition should happen only after behavioral coverage exists.

## 4. Product navigation hypothesis

The website should be organized around recruiter work, not technical subsystems.

Top level:

- Home
- Recruiting Projects
- Candidates
- Review Center
- Knowledge
- Settings

Project flow:

- Project Home
- Role & Criteria
- Intake
- Screening & Decision
- Interviews
- Follow-up & Offer
- Quality / Audit

Candidate Workspace:

- Overview
- Sources & Evidence
- Criteria & Verification
- Interview
- Decision
- Offer & Follow-up
- History

The Candidate Workspace should be a first-class routed page, not a modal.

## 5. What remains local/backend-only

These capabilities should remain outside browser JavaScript:

- SQLite transaction management
- migrations and schema verification
- filesystem/blob storage
- PDF/document extraction
- OCR runtime
- ASR runtime
- provider secrets
- local model/runtime discovery
- Knowledge DB validation and switching
- backup and restore
- long-running background jobs
- diagnostic bundle construction
- Windows process and lock cleanup
- WPF/WebView2 native host lifecycle

Trying to move these into browser code would reduce rather than improve product quality.

## 6. Carrier model

A major advantage of HTML-first design is that the same product surface can have multiple carriers.

### Local browser

SRW starts the local service and opens the user's default browser.

Advantages: simplest UI debugging, browser devtools, least native code.

### Windows WebView2

The existing native launcher opens the same local site in a dedicated window.

Advantages: desktop feel, controlled lifecycle, future file integration, no visible browser chrome.

### Optional private server

A future server deployment could serve the same frontend against a remote backend.

This should remain an optional future path, not a C11/C12 requirement.

## 7. Security model

Production HTML should always be served from the SRW origin. Avoid opening the production product through `file://`.

Same-origin serving gives a much cleaner security boundary:
- no broad CORS configuration,
- provider keys never enter the page,
- no direct filesystem access from JavaScript,
- authenticated/authorized routes can be added later,
- CSP can be tightened,
- local host binding can remain loopback-only.

## 8. Migration strategy

Do not perform a big-bang rewrite.

Phase 0 — isolated prototype:
- standalone HTML,
- mock data,
- no production writes.

Phase 1 — read-only live shell:
- dashboard,
- project list,
- candidate list,
- candidate workspace,
- same-origin GET APIs.

Phase 2 — controlled mutation:
- candidate intake,
- contact plan,
- Claim review,
- interview feedback,
- decision,
- Offer.

Phase 3 — parity:
- OCR/ASR task feedback,
- evidence viewer,
- Knowledge,
- import/export,
- diagnostics,
- backup/restore surfaces.

Phase 4 — carrier convergence:
- local browser and WebView2 use the same static web application.

Only after Phase 3 should we consider retiring old frontend paths.

## 9. Decision criteria

The experiment should be considered successful only if it improves all of the following without losing 0.8.x capabilities:

- fewer navigation steps per recruiting task,
- clearer current/next action,
- stable candidate context,
- evidence provenance remains visible,
- no regression in OCR/ASR/AI integration,
- no weakening of audit/decision boundaries,
- no new requirement for public cloud,
- acceptable memory and startup cost,
- easy Windows packaging.

## 10. Main risk

The largest risk is mistaking "HTML-first" for "frontend rewrite."

The project already has extensive business logic and hard-won operational capabilities. The web exploration is valuable only if it simplifies the product surface while reusing those capabilities. A visually cleaner rewrite that drops evidence, Knowledge, OCR/ASR, AI, audit, portability or operational workflows would repeat the failure mode that made the stripped alpha line less useful than the mature 0.8.x line.
