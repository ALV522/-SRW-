# SRW Q1R10 dual-carrier early pilot: actual Windows launcher overlay

**Status: EARLY PILOT / independent Q1R10 artifact validation pending; NOT RC/GA.** Issue #258. This release pilot is for local test data. It does not deploy a shared-Core supervisor and does not override product or source provenance.

## Target prerequisite (not included in GitHub)

Use the B/C-built, privately retained Q1R10 Native ZIP for **source SHA** `1d273b67bd0f571bd3c2e691e80a541c50e16f09`, **ZIP SHA-256** `708b6deddaab5bda7a1d13c93a740e6aed3d4e6dfa3eebe1637f99fdb661cb1e`, **size** 102,272,222 bytes. See [#42 Q1R10 evidence](https://github.com/ALV522/-SRW-/issues/42#issuecomment-6845892479): Source 456/456, Runtime 2332/2332, Knowledge 5/5, 1920×1200 135% WPF startup/window/sidebar/shutdown & exclusive-DB PASS. These are **not** assertions of Web startup or EXE↔Web switching. Do not upload this private Runtime/Knowledge ZIP into the public repository.

## Install/operate

1. Verify the **original Q1R10 ZIP** SHA using Windows PowerShell `Get-FileHash 'D:\\path\\Q1R10.zip' -Algorithm SHA256`. Stop if it differs. Extract it to a new application directory. Keep the original ZIP intact.
2. Copy `START-SRW-EXE.cmd` and `START-SRW-WEB.cmd` from this pilot overlay into that extracted root, beside `VERSION`. The root must contain `runtime/python.exe`, `frontend/dist/index.html`, `scripts/start_local_web.py`, `knowledge/active` and `windows-host/SmartRecruitmentWorkbench.exe`. Do not modify the private Runtime or Knowledge contents.
3. For **Windows EXE**, double-click `START-SRW-EXE.cmd`. The launcher supplies an explicit private data directory `%LOCALAPPDATA%\\SRW\\DualCarrierV0\\data` and the real WPF Host receives `--application-root` and `--data-root` arguments.
4. Close the EXE normally. For **Local Web**, double-click `START-SRW-WEB.cmd` in an interactive console. Embedded Python runs the existing real `start_local_web.py` (not synthetic and not a static demo), always bound to `127.0.0.1:8765/v1`. Session enforcement is ON; enter the single-use, 60-second pairing code shown **only** in the terminal. Press Ctrl+C to shut the Web Core down gracefully; closing a browser tab does not stop the backend.
5. Only after graceful stop, reopen EXE. Both carriers use the same `%LOCALAPPDATA%\\SRW\\DualCarrierV0\\data`, subject to the current cross-carrier atomic `data/app.lock`. Simultaneous Web + EXE Core ownership of the same SQLite is **unsupported and intentionally refused**; no manual removal of lease/restore files.
6. Do not point either entry at an existing real-data workbench as part of this initial pilot. Built-in native ZIP audit may see the two additional overlay files as extra members if run on a modified extracted folder; verify the pristine original ZIP separately, never falsely label the overlay as the original 2812-member artifact.

## Evidence needed to claim a usable pilot

- B/C must repeat **actual** Windows Q1R10+launcher test in a clean private data-root: EXE project+protocol+candidate → normal close → Web one-time pair → same candidate + new scheduled interview → Ctrl+C → EXE sees same event.
- Confirm active EXE refuses Web startup (and vice versa) without a second SQLite writer or unsafe lock deletion. Record instance/window/port/exit, lease ownership, script SHA, ZIP SHA, and no raw private data.
- Include the **reverse first-run order** Web→EXE on another new empty workspace, and demonstrate original existing workspaces were not touched.
- This only qualifies a **local single-user sequential-switching pilot**. #230 cross-instance replay, #43 simultaneous shared Supervisor/CAS, #124 Runtime & Knowledge custody/licence, #130 physical recovery, #159 rare Windows shutdown remain blockers to **RC/GA**.

Windows 10/11 x64 requires .NET 10 Desktop Runtime and Edge WebView2 Runtime for the native Host. No separate Python installation is required for this pilot (uses pinned embedded runtime).

Pre-edit mode: GitHub-API-native (not local Git). Local git preflight: NOT RUN. Source/Chromium/Windows/real pilot results must be reported separately at the precise SHA/artifact identity.

## Verified Windows pilot — 2026-11-13 (scope-bound)
B/C found a P1 in the original `START-SRW-EXE.cmd` (SHA256 `196dfe1d21df024fd21c580cf7f84238707c86e74fafd20abdd6517fa0d54038`): `%~dp0` carries a terminal backslash, so the outgoing quoted `--application-root "%APPROOT%"` accidentally escaped its closing quote and swallowed `--data-root`. Original launcher: **FAIL**, preserved at [PR #259](https://github.com/ALV522/-SRW-/pull/259#issuecomment-6846901789).
The replacement retains slash-terminated `APPROOT` only for joins, derives a terminal-slash-free `APPROOT_ARG` for external Windows argv, and adds a regression. B/C's *locally corrected* CMD with the original fixed-SHA Q1R10 ZIP passed EXE project+published protocol+candidate → Web same candidate, pairing and two scheduled interviews → EXE readback, plus reverse initial order and exclusive workspace denial. [Windows actual evidence](https://github.com/ALV522/-SRW-/issues/258#issuecomment-6847066190) is specific to B/C's locally corrected bytes. The corrected new PR exact HEAD and the separately packaged installer still need their own check, and no simultaneous two-Core access is supported.
