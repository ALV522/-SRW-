# Dual-Carrier Architecture: Web + EXE With Shared Information

## Product goal

The long-run target can support **both a Web edition and a Windows EXE edition without creating two separate SRW products**.

The central design principle is:

> Web and EXE are carriers. The authoritative recruiting data and business rules live behind one SRW service contract.

The first implementation target is same-machine interoperability. A later optional target can add private-server / multi-device interoperability.

---

## 1. Same-machine dual carrier

This should be the default architecture for the local-first product.

```
                         SRW Local Service
                      http://127.0.0.1:<port>
                                |
                +---------------+---------------+
                |                               |
                v                               v
        System Browser                    Windows EXE
        SRW Web UI                   WebView2 / native shell
                |                               |
                +---------------+---------------+
                                |
                                v
                  one authoritative data plane
                                |
             +------------------+------------------+
             |                  |                  |
           SQLite            Blob Store        Job Engine
                                                   |
                                      OCR / ASR / AI / Knowledge
```

There is **no data synchronization problem** in this mode because browser and EXE do not maintain separate databases. They see the same data through the same APIs.

If the user edits a candidate from the EXE, refreshing or subscribing to updates in the browser reveals the same state. The reverse is identical.

This is substantially safer than having a "Web database" and an "EXE database" and attempting bidirectional synchronization.

---

## 2. Product identities

### Web edition

The Web edition is the canonical HTML/CSS/JavaScript product surface.

Possible carriers:

- browser opened by SRW launcher;
- browser manually opened at the local URL;
- future private-server deployment.

### EXE edition

The EXE should not become an independent implementation of recruiting logic.

It should provide:

- process/service lifecycle;
- Windows startup and shutdown;
- WebView2 carrier;
- native file dialogs / drag-drop integration when useful;
- local runtime discovery;
- diagnostics and recovery hooks;
- Windows packaging and update entry point.

The main application view should use the same Web product assets and API contract as the browser edition.

---

## 3. Authoritative state rule

For every business object there must be exactly one authoritative store.

| Object | Authority |
|---|---|
| Project / protocol | SRW backend + SQLite |
| Candidate | SRW backend + SQLite |
| Source metadata | SRW backend + SQLite |
| Raw file / media | SRW blob store |
| Claim | SRW backend + SQLite |
| Criterion judgment | SRW backend + SQLite |
| Human decision | SRW backend + SQLite |
| Interview / scorecard | SRW backend + SQLite |
| Offer / action plan | SRW backend + SQLite |
| OCR / ASR task | SRW Job Engine |
| Provider secret | local secret store |
| Knowledge databases | SRW Knowledge subsystem |
| UI ephemeral state | current carrier only |

Browser LocalStorage must never become an authoritative recruiting datastore.

---

## 4. Same-origin contract

For production, the preferred topology is:

```
http://127.0.0.1:<dynamic-port>/
  /
  /assets/*
  /api/v1/*
  /health/*
```

The HTML UI and API are served from the same origin.

Benefits:

- no permissive CORS;
- no provider keys in frontend code;
- no direct browser filesystem access;
- cookies/tokens can be added later without redesign;
- a WebView2 and a normal browser can load the exact same site;
- local service can remain loopback-only.

---

## 5. Cross-carrier consistency

### Initial implementation

Use ordinary HTTP reads/writes and refresh after mutation.

This is sufficient for a single operator.

### Later improvement

Add a lightweight change feed:

```
GET /api/v1/changes?after=<cursor>
```

or Server-Sent Events:

```
GET /api/v1/events/stream
```

Events should contain only identifiers and revision metadata, not provider secrets or unnecessary PII.

Example:

```json
{
  "cursor": 18422,
  "entity_type": "candidate",
  "entity_id": "...",
  "project_id": "...",
  "revision": 17,
  "event_type": "CANDIDATE_UPDATED"
}
```

Both browser and EXE can invalidate affected views after receiving an event.

---

## 6. Concurrency control

Once Web and EXE can be open at the same time, lost updates become a real product risk.

Write endpoints should eventually support an expected revision/version.

Example:

```
PATCH /api/v1/candidates/<id>/action-plan
If-Match: "revision-17"
```

If another carrier has already changed the object:

```
409 Conflict
```

The UI then reloads the current state and asks the operator to reconcile the change.

Do not silently use last-write-wins for human decisions, evidence confirmation, scorecards or protocol revisions.

---

## 7. Future multi-device / hosted mode

The same-carrier architecture does **not** require cloud deployment.

But if a future Web edition is reachable from another device, there are two valid models.

### Model A — one private authoritative server

Both desktop EXE and browsers connect to one SRW server.

This is still not "sync"; it is one database with multiple clients.

This is preferred for a team deployment.

### Model B — offline local instances with replication

This is much harder and should be deferred.

If ever required, it needs:

- globally stable UUIDs;
- entity revision numbers;
- append-only audit/event log;
- transactional outbox;
- idempotent inbox;
- content-addressed blob transfer;
- explicit conflict policy;
- identity merge semantics;
- tombstones for deletes/archives;
- schema/version compatibility negotiation.

This should not be introduced merely because both Web and EXE exist.

---

## 8. File interoperability

Raw resumes, PDFs, images and recordings should not be copied into browser storage.

Use backend source IDs and content-addressed blob hashes.

The UI accesses files through controlled routes such as:

```
/api/v1/sources/<source_id>/file
/api/v1/sources/<source_id>/content
/api/v1/sources/<source_id>/page/<n>
```

The same source ID therefore opens the same material in browser and EXE.

---

## 9. AI / OCR / ASR interoperability

Both carriers submit jobs to the same SRW backend.

```
Web / EXE
   |
   v
POST task
   |
   v
Job Engine
   |
   +-- OCR
   +-- ASR
   +-- AI
   |
   v
persist result
   |
   v
both carriers observe same task/result
```

No carrier should execute a hidden second copy of the AI/OCR/ASR pipeline.

---

## 10. Release model

Long-run packaging can become:

```
SRW Core
  backend/
  migrations/
  knowledge contract/
  API contract/

SRW Web
  web-dist/

SRW Windows
  SRW.exe
  WebView2 host
  bundled SRW Core
  same web-dist/
```

The Web and Windows releases should report:

- Core version;
- API contract version;
- frontend build version;
- schema version.

Compatibility must be machine-checkable.

---

## 11. Near-term experiment

The current exploration branch will prove the architecture in this order:

1. E0 mock standalone HTML — completed.
2. E1 read-only same-origin API adapter — implement now.
3. E1.5 read-only live Project and Candidate Workspace — implement now.
4. E2 controlled mutations — only after read-only behavior is stable.
5. E3 parity audit against C11 and the mature 0.8.x capability baseline.
6. Only then evaluate selective mainline adoption.

No exploration code is merged into production merely because it looks better.
