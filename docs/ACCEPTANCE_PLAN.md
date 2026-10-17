# C11 product acceptance work remaining

This is an execution plan, not a completed acceptance report. C11 prioritizes complete operator workflows over new infrastructure. Use synthetic/anonymized inputs, never production candidate files in Git or CI artifacts.

| Flow | Actions | Required result |
|---|---|---|
| Daily work queue | Open dashboard, select highest-priority candidate action, enter the target workflow | One actionable next step per candidate; direct navigation preserves project/candidate context |
| Operations queue | Create overdue and same-day contacts and complete an interview without submitted feedback; open each from dashboard | Operator lands in contact workbench or scorecard workflow without searching for the candidate manually |
| Review center | Seed a pending identity review, open judgment correction and unreviewed Claim; open each from dashboard; resolve the judgment item with a note | Identity/judgment items enter Quality Governance; Claim opens the correct candidate evidence workspace; judgment review leaves the open queue after explicit resolution; archived recruiting work is excluded |
| Project guidance | Open a draft project, an active project with decision work, and an interview/Offer-stage project | Project home shows the correct next action and routes to the correct business tab without requiring internal-system knowledge |
| Project and criteria | Create project, publish requirements, edit and republish | Clear active revision; prior evaluation context retained |
| Intake and identity | Import PDF/text, add new revision, review duplicate identity | Current material correct; canonical merge keeps provenance |
| Evidence | Open claim source, inspect PDF highlight, confirm or reject | Visible original evidence; mismatch rejected; missing stays unknown |
| Assessment and decision | Complete verification, compare, record human decision | Only eligible evidence-closed candidates ranked; human boundary retained |
| Context change | Change criteria/material after decision | Old decision historical; explicit reevaluation/reaffirmation required |
| Operations and feedback | Accept/start/complete action; classify feedback | Context-bound actions; no automatic ontology mutation |
| Knowledge | Preview alias change, apply exact digest, rollback | Target validation; correct diff; exact rollback |
| Portability | Export project; preview/import into another instance | Source blobs preserved; IDs remapped; old decisions historical |
| Restart and recovery | Restart, back up, restore, interrupt and retry | Business state durable; known staging cleaned; live data preserved |
| Windows GUI | Launch/close/relaunch, open files, view evidence, export | No leaked process/SQLite lock; usable WPF/WebView2 flow |
| External AI | Configure real provider, timeout/limit/error cases | Actual privacy projection; clear retry and failure status |

Record for each run: exact commit/artifact hash, OS/runtime, dataset identity, actions, observed result, evidence location and unresolved defects. API regression is a prerequisite; it does not mark UI rows complete.
