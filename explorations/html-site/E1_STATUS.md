# E1 Verification Status — browser HTML + real SRW C11 backend

Last confirmed source snapshot: `481162b65ffb612fd4509a76647c0b0e50302c6a`

Independent CI: https://github.com/ALV522/-SRW-/actions/runs/39152520579

## Verified

- **Ubuntu**: 15 E1 / packaging regression tests PASS.
- **Windows**: 15 E1 / packaging regression tests PASS.
- **Chromium real browser**: 9 combined E1/E2 tests PASS against genuine C11 Starlette API and disposable SQLite.
- **Python 3.12 source + Windows batch**: `START_HERE.cmd --smoke` and `START_E2.cmd --smoke` PASSED on Windows, including isolated venv creation, pinned dependency installation and genuine backend startup.
- **Source packaging**: complete verified SHA256 manifest; all expected backend/srw/runtime files, original frontend, synthetic fixture and launchers included.
- **Windows file-path incident**: incomplete-root false negative and duplicate launch-script path were reproduced and fixed by CI.
- **E1 identity and guards**: product/session/data-scope checks, loopback / allowed GET/HEAD / Host / Origin / redirect defenses tested.
- **E1 business views**: Dashboard, Project, cross-project Candidate Directory, Candidate Workspace with synthetic Source and Claims, profile/stage display from persistent records.
- **E1 navigation**: direct candidate deep link, refresh, back navigation, cross-project search and stage filter.
- **Responsive**: 390px-width mobile browser pages do not have page-wide horizontal overflow.
- **Cross-client reads**: an independent direct-backend synthetic stage mutation is visible after E1 browser refresh.
- **E2a**: four proxy guard regressions per OS, conditional synthetic Action Plan mutation, 412 stale rejection, 428 missing precondition, 405 all other mutation paths; backend audit events visible.

The artifact can be retrieved from:
https://github.com/ALV522/-SRW-/actions/runs/39152520579/artifacts/12145448946

The artifact is the **E1/E2 source demonstration** and must not be referred to as a Windows Portable / accepted Native EXE package.

## Unverified or unfinished

1. A real API-compatible C11 Windows WPF/WebView2 Native EXE + embedded Python runtime.
2. Five production Knowledge DBs and full v0.8.x capability parity.
3. Real EXE/Browser simultaneous attach identity + shared writes.
4. Official transactional Core CAS for Action Plan and other human decisions (E2 guard is proxy-only).
5. External real OCR/ASR/provider calls and real candidate corpus calibration.
6. Secure remote/private-server browser access, authentication and authorization.
7. Native process lifecycle when browser remains open after EXE closes.
8. Full native packaging and integration acceptance.

## User action

If you want to try the now-verified **source demo**, download the whole Actions
artifact and run top-level `START_HERE.cmd`. Optional E2 experience:
`START_E2.cmd`. See `USER_ACTIONS_NO_EXE.md`. Both use only temporary
synthetic records. No real candidate data or database needs to be provided.

Actual C11 EXE dual-carrier verification can wait until a compatible native
package exists; do not substitute an old Windows host and migrate historical
production data merely to complete an experiment.
