# C11 product acceptance work remaining

This is an execution plan, not a completed acceptance report. C11 prioritizes complete operator workflows over new infrastructure. Use synthetic/anonymized inputs, never production candidate files in Git or CI artifacts.

| Flow | Actions | Required result |
|---|---|---|
| Queue priority and scope | Seed archived projects, active evidence conflicts, ordinary verification and a greater-than-12 candidate queue | Archived projects never appear; conflicts precede verification; preview and total counts remain distinct |
| Local contact day | Create contacts spanning local midnight, including tomorrow morning less than 24 hours away | Tomorrow never appears in today's queue; overdue and today share host-local calendar semantics |
| Daily work queue | Open dashboard, select highest-priority candidate action, enter the target workflow | One actionable next step per candidate; direct navigation preserves project/candidate context |
| Operations queue | Create overdue and same-day contacts and complete an interview without submitted feedback; open each from dashboard | Operator lands in contact workbench or scorecard workflow without searching for the candidate manually |
| Exact review navigation | Seed multiple identity, judgment and Claim items; click a middle dashboard item, then resolve/reject it | Exactly the clicked item is scrolled into view and highlighted; stale/deleted items report a clear message |
| Review center | Seed a pending identity review, open judgment correction and unreviewed Claim; open each from dashboard; resolve the judgment item with a note | Identity/judgment items enter Quality Governance; Claim opens the correct candidate evidence workspace; judgment review leaves the open queue after explicit resolution; archived recruiting work is excluded |
| Project guidance | Open a draft project, an active project with decision work, and an interview/Offer-stage project | Project home shows the correct next action and routes to the correct business tab without requiring internal-system knowledge |
| Candidate workspace | Open a candidate from Candidate Intake, Decision Cockpit and dashboard review queue; switch Evidence & Decision / Process & Follow-up / Offer | Full-size workspace preserves project/candidate context; no large parent modal; evidence, intake, verification, decision, pipeline, contact plan and Offer actions remain reachable |
| Candidate interview flow | In Process & Follow-up create phone screen/interview, complete a scheduled event, open independent Scorecard, create/apply reevaluation draft | Candidate-specific interview and reevaluation work can be completed without leaving the candidate workspace; project-wide flow remains available for coordination |
| Brief and handoff | Open a candidate brief and project handoff; download the full handoff JSON | Human-readable business summary is primary; version/audit context remains available; complete handoff data is downloadable without forcing raw JSON as the main UI |
| Contact action routing | Open an overdue or same-day contact from the dashboard | The exact candidate action plan opens directly, without manually locating the candidate in the generic contact queue |
| Job setup wizard | Walk forward/backward through all four setup steps, save Draft, request suggestions, add a suggestion to the criteria editor | Step data persists; setup remains Draft; suggestions are readable and never auto-publish; human save and explicit publish are still required |
| Criteria semantics | Save Job Setup context, define weighted criteria across one or more stages, retain custom criterion/stage/policy metadata, edit and save again | Job context, weights, stage assignments, decision policy and unedited metadata survive the round trip; deleted criteria are removed from stage references |
| Project and criteria | Create project, publish requirements, edit and republish | Clear active revision; prior evaluation context retained |
| Intake and identity | Import PDF/text, add new revision, review duplicate identity | Current material correct; canonical merge keeps provenance |
| Evidence | Open claim source, inspect PDF highlight, confirm or reject | Visible original evidence; mismatch rejected; missing stays unknown |
| Assessment and decision | Complete verification, compare, record human decision | Only eligible evidence-closed candidates ranked; human boundary retained |
| Context change | Change criteria/material after decision | Old decision historical; explicit reevaluation/reaffirmation required |
| Operations and feedback | Accept/start/complete action; classify feedback | Context-bound actions; no automatic ontology mutation |
| Knowledge | Preview alias change, apply exact digest, rollback | Target validation; correct diff; exact rollback |
| Runtime manifest stage | Plant local candidate data next to embedded Python; stage using external SHA-256 list | Only listed runtime files shipped; altered, missing and symlinked files rejected |
| Native ZIP final audit | Test synthetic archive with modified binaries, additional private files and fake accepted provenance | All ZIP names and SHA-256 digests checked against source, Runtime, Knowledge, Host inventories; false GUI claims rejected |
| Native stage allowlist | Place synthetic user-data directories and untracked secrets next to verified source, then assemble with audited external assets | Untracked candidate data, backups and secrets never enter the staging directory/ZIP; resulting candidate labelled UNVERIFIED |
| Portable input preflight | Run preflight with missing carrier/Knowledge and with separately audited complete inputs | Missing or hash-mismatched inputs are BLOCKED, never represented as a ready Windows build; provenance and GUI remain separate gates |
| Portability | Export project; preview/import into another instance | Source blobs preserved; IDs remapped; old decisions historical |
| Backup manifest integrity | Back up SQLite plus Source blobs, alter a ZIP member and attempt restore | Manifested backups reject tampering; existing data and pending restore marker survive failure |
| Legacy backup compatibility | Restore a historical DB-only backup and reject extra ZIP members | Historical layout remains readable without accepting unsafe paths or undetected additions |
| Restart and recovery | Restart, back up, restore, interrupt and retry | Business state durable; known staging cleaned; live data preserved |
| Windows GUI | Launch/close/relaunch, open files, view evidence, export | No leaked process/SQLite lock; usable WPF/WebView2 flow |
| External AI | Configure real provider, timeout/limit/error cases | Actual privacy projection; clear retry and failure status |

Record for each run: exact commit/artifact hash, OS/runtime, dataset identity, actions, observed result, evidence location and unresolved defects. API regression is a prerequisite; it does not mark UI rows complete.

## Automated browser evidence

See [Chromium acceptance](BROWSER_ACCEPTANCE.md). This separate CI gate executes click paths against a loopback SRW instance with real persistence and synthetic Knowledge inputs. It is not equivalent to Native Windows GUI smoke, production Knowledge validation or live AI verification. Record the exact browser workflow URL and SHA alongside release acceptance evidence.

## 2026-10-18 acceptance evidence update

Completed on main commit `69f60b9` (Chromium only): four-step Job Setup draft, candidate Source text intake and operator follow-up, candidate interview scheduling, human pipeline transitions into eligible Offer Draft stage, and confirmation that Offer Draft does not auto-hire. The new browser CI is separate from the 109-test source baseline; 4 extra archive-management regression tests are being added in the present PR. Uncovered workflows in the table above remain requirements, **not** completed browser or Windows Native acceptance. Exact new-commit evidence must be linked before claiming this PR verified.

## 2026-10-19 real Windows GUI smoke evidence

A user-supplied screenshot and a 45-record Host JSONL log prove actual Windows WPF/WebView2 startup, dashboard loaded, backend ready/runtime identity, real project creation and protocol revision update HTTP 200, and clean backend/workspace shutdown; no fatal backend or GUI startup error was logged. Basic Native GUI lifecycle and these two business writes are accepted **on the d8d032d candidate only**, but candidate intake, OCR/ASR, AI Provider, backups, recruiting Decision/Offer remain acceptance gaps. The read-only log auditor and detailed evidence boundaries are documented in [WINDOWS_GUI_FIRST_ACCEPTANCE.md](WINDOWS_GUI_FIRST_ACCEPTANCE.md). No actual user log/session identifiers are checked into Git.

## Added independent evaluator and Offer state business acceptance

Real browser tests `test_04_independent_interview_scorecards_cannot_be_overwritten` and `test_05_offer_lifecycle_requires_human_transitions_and_never_auto_hires` now exercise independent interviewer judgments and legitimate Offer state transitions end to end. A submitted scorecard cannot be overwritten, disagreement is not automatically averaged, an Offer may not skip approval, and accepted Offer must not autonomously mark the candidate hired or create a HumanDecision. Five Chromium scenarios should be reflected in CI evidence only after the exact head and merged main checks pass. The Windows WPF frontend and full evidence->HumanDecision workflow remain distinct acceptance requirements.

## Issue #72: reject damaged backups before scheduling restore

`POST /api/v1/system/backups/{filename}/restore` must use the same Core archive
validator as startup recovery before reporting `scheduled=true`. A modified or
missing manifested blob, invalid manifest, unexpected ZIP member or incompatible
Schema must fail before replacing `pending_restore.json`; an existing plan and
live recruiting data remain unchanged. The URL and successful response/marker
fields remain unchanged. Historical DB-only backup compatibility is retained;
legacy archives do not acquire a false manifest-integrity guarantee.

`convergence_tests/test_restore_schedule_integrity.py` covers rejection, previous
plan preservation, valid scheduling/cancel, legacy compatibility, missing files
and the existing Schema allowlist using disposable SQLite and synthetic blobs.
`browser_acceptance/test_flows.py::test_11_restore_schedule_rejects_bad_backup_before_restart`
creates a backup through Settings, injects damaged bytes into its temporary ZIP,
then clicks restore and checks the error and absence of a pending marker. After
restoring the original ZIP bytes, an explicit second click schedules it normally.
Only fault injection uses filesystem writes; business HTTP responses are real.
Cancellation at test cleanup uses the API, not a claimed UI cancellation flow.

Exact-SHA Source and Chromium results belong in the associated PR/Actions
evidence. This scenario does **not** execute restart recovery, prove crash-safe
restore, run WPF/WebView2, validate production Knowledge/Provider inputs, or
complete Windows/dual-carrier acceptance. Startup must still revalidate the
scheduled archive hash and members before replacing live data.

## Process-restart backup restore acceptance (P0 #41 / Native prerequisite #42)

`convergence_tests/test_real_restore_restart.py` launches the **real** C11
`run_local.py` Core on a disposable loopback port with synthetic SQLite,
Knowledge and Source blob content; it uses real HTTP backup and schedule
routes. The test takes a backup containing project A and its Source bytes,
creates project B afterward, schedules restore, then gracefully shuts down
Core. It modifies the scheduled ZIP after approval and verifies a subsequent
startup fails closed **before mutating SQLite** and preserves both the
pending marker and an absent/released workspace lease. Restoring the original
archive bytes and restarting executes the real pending restore and verifies:
only A survives, original Source bytes are reinstated, later blobs disappear,
the pending marker is removed, and one independently valid pre-restore
snapshot is created. The second process closes cleanly and releases the lock.

This is a **source/API real-process** acceptance test, not a mocked handler
or merely a call to `apply_pending_restore`. The GitHub Ubuntu/Windows Source
Gate must prove it at the exact PR HEAD. It does **not** establish actual WPF
GUI, embedded Windows Runtime, production Knowledge, physical disk crash/power
loss safety, user-data migration, or finished Native ZIP acceptance. All
inputs are generated under a temporary synthetic workspace and cleaned up.

## Browser real-PDF candidate intake: source-level document fidelity (#41)

`browser_acceptance/test_flows.py::test_12_operator_uploads_real_pdf_resume_with_source_provenance`
uses a generated, single-page **actual PDF** (not a renamed text file) in a fully synthetic
workspace. It clicks the existing candidate file selector and “上传并处理”, then verifies
that the extracted text becomes a **current** Source/MaterialRevision, Source metadata
retains the PDF filename and `rich_document` importer identity, and the original
binary is retrievable byte-for-byte from the authorized Source endpoint. Uploading
this resume alone **must not** create an authoritative HumanDecision; text-bearing PDF
must not spuriously require an OCR Provider task.

The CI result is a **Chromium + real Core/SQLite/PyMuPDF** acceptance for text-bearing
PDF only. It does not prove image-only PDF OCR, OCR accuracy, actual user data quality,
Provider, ASR, Windows WPF GUI or full v0.8.12-R2 parity. These remain separately
blocked/not verified until exact-artifact acceptance evidence exists.
