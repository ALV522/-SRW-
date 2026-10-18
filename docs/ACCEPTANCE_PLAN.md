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
| Native stage allowlist | Place synthetic user-data directories and untracked secrets next to verified source, then assemble with audited external assets | Untracked candidate data, backups and secrets never enter the staging directory/ZIP; resulting candidate labelled UNVERIFIED |
| Portable input preflight | Run preflight with missing carrier/Knowledge and with separately audited complete inputs | Missing or hash-mismatched inputs are BLOCKED, never represented as a ready Windows build; provenance and GUI remain separate gates |
| Portability | Export project; preview/import into another instance | Source blobs preserved; IDs remapped; old decisions historical |
| Backup manifest integrity | Back up SQLite plus Source blobs, alter a ZIP member and attempt restore | Manifested backups reject tampering; existing data and pending restore marker survive failure |
| Legacy backup compatibility | Restore a historical DB-only backup and reject extra ZIP members | Historical layout remains readable without accepting unsafe paths or undetected additions |
| Restart and recovery | Restart, back up, restore, interrupt and retry | Business state durable; known staging cleaned; live data preserved |
| Windows GUI | Launch/close/relaunch, open files, view evidence, export | No leaked process/SQLite lock; usable WPF/WebView2 flow |
| External AI | Configure real provider, timeout/limit/error cases | Actual privacy projection; clear retry and failure status |

Record for each run: exact commit/artifact hash, OS/runtime, dataset identity, actions, observed result, evidence location and unresolved defects. API regression is a prerequisite; it does not mark UI rows complete.
