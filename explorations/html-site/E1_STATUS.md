# SRW HTML E1–E4 — Verification Truth

This page tracks *exploration evidence*, not a Windows Native product release.

## Last fully verified source snapshot

- Branch: `explore/html-site-prototype`
- Passed code commit: `c3b3be139a595ac6497bed70c6c35997f0a534a8`
- [Independent GitHub CI, all jobs passed](https://github.com/ALV522/-SRW-/actions/runs/39189540086)
- Artifact for that tested commit: [complete E1–E4 source ZIP](https://github.com/ALV522/-SRW-/actions/runs/39189540086/artifacts/12159124090) (older artifact naming retains E1)
- Test data: **fully synthetic**, real C11 Starlette API and one disposable SQLite database per scenario

### Automated outcomes

| Gate | Verified result |
|---|---|
| Ubuntu E1/packaging tests | 15 PASS |
| Windows E1/packaging tests | 15 PASS |
| Ubuntu E2 proxy/guard tests | 4 PASS |
| Windows E2 proxy/guard tests | 4 PASS |
| Ubuntu E3 temporary cleanup tests | 4 PASS |
| Windows E3 temporary cleanup tests | 4 PASS |
| Chromium actual C11 browser integration | 16 PASS |
| Windows `START_HERE/E2/E3/E4.cmd --smoke` | all PASS |
| E3 direct independent-SQLite-engine race | exactly one writer commits, stale writer rejects |
| E4 dual origins/one Core identity/independent detach/reattach | PASS |
| SHA-256-verified packaged source demo | PASS |

CI browser artifact includes synthetic-data screenshots.

### What each stage proves

- **E1:** real C11 API read-only HTML UI; candidate and project navigation; Source/Claim display; cross-project filtering; responsive 390px layout and deep-link restore.
- **E2:** synthetic Action Plan `PATCH` through proxy with an `ETag` and `If-Match` precondition; stale writes get 412, but the Core itself does not enforce the proxy precondition.
- **E3:** a *synthetic-only* Core Action Plan route enforces revision, business update and audit in a single SQLite transaction. Tests include two independent database connections, rollback and stale audit protection.
- **E4:** one independently-owned synthetic Core supplies two separate browser carrier origins (second is desktop surrogate); one can detach or reattach without terminating the Core or losing authoritative state.

### Missing real-product acceptance

- No accepted, launchable C11 Windows WPF/WebView2 Native package / embedded Python runtime / five production Knowledge DBs.
- E3's transaction schema/API is not promoted to official `v1_0014` or applied to all Action Plan writers.
- E4's desktop surrogate is not an EXE, tray app, Windows Service or OS-level supervisor.
- Authenticated attach, role/tenant permissions, native workspace lock/process lifecycle and remote TLS have not been delivered.
- No real OCR/ASR provider quality, production Knowledge, human decision end-to-end parity or real-corpus validation; mature v0.8.x functionality must still be conserved.
- No production Web/EXE joint-read/joint-write real-device acceptance.

### User action

No action is required to keep the exploration moving. Optional review: download the full Actions artifact, extract it and start top-level `START_HERE.cmd` (read-only), `START_E2.cmd` (proxy-level), `START_E3.cmd` (transaction-level), or `START_E4.cmd` (independent Core/dual browser). Python 3.12 and first-run dependency internet are needed. Do not attach real SRW data or share sensitive candidate materials.
