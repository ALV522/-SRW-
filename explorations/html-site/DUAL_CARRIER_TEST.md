# Dual-Carrier Interoperability Test

This test is designed to prove the first long-run product hypothesis:

> The Windows EXE and the Web edition can coexist while observing the same recruiting information.

E1 proves only the **EXE → shared backend → Web** read path. Web writes remain deliberately disabled until E2.

## Preconditions

- a normal SRW local instance / Windows EXE is running;
- its loopback service URL is known;
- the exploration branch is checked out separately from the mainline working copy.

## Start the exploration bridge

The Windows EXE chooses a **dynamic port** and owns a workspace lock. Never
start a second service pointed at the same data directory. First locate the
running EXE's `data/app.lock/instance.json` (or the custom data-root if set).

Recommended command:

```powershell
py -3 explorations/html-site/serve_e1.py --data-root "C:\\Path\\To\\SRW\\data" --port 0 --open-browser
```

The bridge reads the Windows Host lease, verifies the backend's exact identity
and chooses a free browser port. Its HTTP routes are GET-only and allowlisted.
The `LIVE · windows · GET-only` badge is required before continuing.

For a standalone SRW Web service without an EXE lease, `--upstream` can be
used with its known `http://127.0.0.1:PORT`; this is not Windows EXE acceptance.

## Test A — shared project state

1. Open a project in the existing EXE.
2. Open the same project in E1 Web.
3. Compare:
   - project title/status;
   - candidate count;
   - funnel stage counts;
   - current next action.
4. Perform an ordinary mainline business action in the EXE.
5. Refresh the Web page.
6. Confirm the changed state is visible.

Expected result: Web observes the change because both carriers read the same authoritative backend.

## Test B — shared candidate state

Choose one candidate with material and evaluation state.

Compare EXE vs Web:

- display name;
- pipeline stage;
- contact confirmation;
- current decision readiness;
- source list;
- current-material markers;
- Claims and confirmation states;
- Criterion status/evidence level;
- blocking count;
- current human decision.

Expected result: identifiers and business state match.

## Test C — raw material identity

Pick a Source shown in Candidate Workspace.

Verify that both carriers resolve the same `source_id` and therefore the same backend blob/content route.

Expected result: no browser-side copy of the resume is required.

## Test D — safety boundary

From the browser devtools or another HTTP client, attempt through the exploration bridge:

```
POST http://127.0.0.1:8877/api/v1/projects
PATCH http://127.0.0.1:8877/api/v1/candidates/<id>/action-plan
DELETE http://127.0.0.1:8877/...
```

Expected result: HTTP 405 from the bridge. No mutation reaches the SRW service.

## Test E — simultaneous use

Keep both EXE and Web open for at least 30 minutes while doing normal read navigation.

Observe:

- no database locking errors;
- no extra SRW database is created;
- no duplicate OCR/ASR/AI job is launched by Web;
- no change to EXE lifecycle;
- browser refresh remains safe.

## E2 future test

After E1 is accepted, E2 can enable a very small number of controlled mutations in the exploration frontend.

First candidates:

1. update Candidate Action Plan;
2. confirm/reject a Claim;
3. submit a verification note.

At that point the reverse path can be proven:

```
Web mutation → shared SRW service → EXE sees the same persisted change
```

Human Decision, protocol publication, identity merge and Offer state transitions should remain disabled until concurrency/version protection is designed.
