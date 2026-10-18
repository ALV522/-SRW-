# E1 Read-only API Matrix

The E1 experiment deliberately uses only GET endpoints.

| Product view | Endpoint | Purpose |
|---|---|---|
| Connection | `/health/ready` | verify local SRW service |
| Home | `/api/v1/dashboard` | operational/decision/review queues |
| Projects | `/api/v1/projects` | project cards |
| Project | `/api/v1/projects/{id}/pipeline` | funnel, next action, interviews/offers |
| Project candidates | `/api/v1/projects/{id}/candidates?archived=active` | active candidate list |
| Candidate header | `/api/v1/candidates/{id}/summary` | stage/contact/offer summary |
| Candidate evidence | `/api/v1/candidates/{id}/workspace` | sources, claims, criteria, decision readiness |
| Candidate operations | `/api/v1/candidates/{id}/brief` | contact/action-plan/business summary |

## Safety boundary

E1 has a hard-coded GET-only client. It refuses POST/PATCH/PUT/DELETE even if a UI bug attempts to call them.

It therefore cannot:
- change a pipeline stage;
- review a Claim;
- submit a decision;
- update a contact;
- create an Offer;
- start OCR/ASR/AI work;
- mutate Knowledge;
- change settings.

This makes E1 suitable for live-data UI exploration without changing production records.
