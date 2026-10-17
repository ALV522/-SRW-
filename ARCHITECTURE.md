# SRW Architecture Truth

## Product boundary

SRW is a local-first recruitment operations and decision-support workbench. The current architecture treats **v0.8.12-R2 as the capability-completeness reference** and does not use UI simplification as permission to remove mature evidence, lineage, privacy, calibration, governance or release semantics.

## Core layers

- `backend/srw/kernel`: IDs, hashing, clock and invariant primitives.
- `backend/srw/runtime`: database/schema, settings, capability loading, local-boundary and lifecycle infrastructure.
- `backend/srw/modules`: durable domain capabilities. Candidate material/evidence, protocol, decision, identity, calibration, feedback, operations, planning, intelligence, knowledge governance and project portability live here.
- `backend/srw/api`: HTTP adapters. New capability work should prefer small dedicated route modules instead of adding more surface area to `fullworkbench.py`.
- `backend/srw/surfaces`: read-oriented product projections/workspaces.
- `frontend/dist`: current retained browser/WebView2 surface. It is a product asset in the present source baseline; a future frontend-source rebuild must preserve capability parity before replacing it.
- `desktop/SRW.Desktop`: inherited WPF/WebView2 Host source. Host ABI is restored; the exact native binary remains carrier-gated.
- `convergence_tests`: current capability-recovery regression suite. Tests must be self-contained and must not require production candidate data or production Knowledge DB bytes.
- `verification`: historical/current evidence records. Reference evidence must never be presented as newly executed evidence.

## Decision truth

The central semantic chain is:

`Source → Claim → Evidence/Verification → Criterion Judgment → Assessment → Human Decision`

Important invariants:

1. Missing evidence is unknown, not zero.
2. AI proposals are not human decisions.
3. Material/protocol context changes make old judgments and decisions historical unless explicitly carried/reaffirmed under current gates.
4. Operational priority is not candidate ranking.
5. Market/channel intelligence is planning evidence, not candidate scoring input.
6. Privacy-safe AI projection is used on the actual remote-provider path.
7. Source grounding must remain traceable to the original material.

## Local security boundary

The HTTP surface is local-only. Requests with non-local Host headers are rejected. Browser mutations carrying `Origin`/`Referer` must be same-origin. Native Host/API calls may omit `Origin` but still remain restricted by the local Host boundary and, for lifecycle shutdown, the Host session token.

## Knowledge boundary

The five active Knowledge databases are governed artifacts, not mutable runtime scratch data. Operational learning follows:

`human-confirmed action → feedback draft → curation proposal → governance review → prepared package → semantic diff/digest → explicit activation → rollback history`

High-risk ontology creation remains export-only until its full validation contract is restored.

## Release truth

`VERSION`, `BUILD_INFO.json`, `backend/srw/release_state.json`, `PORTABLE_MANIFEST.json`, `VERIFICATION_TRUTH.json` and the code-level schema revision must agree for a tagged release. `scripts/check_release_truth.py` is the source gate for that binding.

Git history is the development truth from the Convergence 08 baseline onward. Portable/native ZIP files belong in GitHub Releases, not normal Git history.
