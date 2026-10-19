# Windows Native SOURCE Lab — C11 WPF GUI + Browser Dual Carrier

This lab is *only* for the isolated `explore/html-site-prototype` branch. It does
not modify the production WPF C# project, source manifests, existing data,
Windows Portable installer, or official release identity.

## Two separate binaries, two different claims

**Canonical source host build.** Uses unchanged
`desktop/SRW.Desktop/SRW.Desktop.csproj`, pinned SDK 10.0.302, locked WebView2
NuGet graph. The WPF host-only artifact passes source compilation (0 warnings,
0 errors), but cannot by itself run C11 without Python/Knowledge resources.

**Native SOURCE Lab test host.** A separate copy of `AppPaths.cs` is
explicitly patched at two reviewed path lookups so the GUI launches an
externally provisioned Python 3.12 venv from
`runtime/Scripts/python.exe`, rather than an embedded
`runtime/python.exe`. This source-modified lab-only executable has its own
SHA-256 `NATIVE_LAB_CSHARP_PATCH.json` provenance. It is NOT the canonical
binary, a production WPF release, or a Portable installer.

## Synthetic Native Lab layout

```text
START_NATIVE_LAB.cmd
run_native_lab.py
NATIVE_LAB_README.md
NATIVE_LAB_MANIFEST.sha256.json
app/
  VERSION
  BUILD_INFO.json
  requirements-ci.txt
  windows-host/
    SmartRecruitmentWorkbench.exe
    WPF_HOST_SOURCE_BUILD_TRUTH.json
    NATIVE_LAB_CSHARP_PATCH.json
  scripts/run_local.py
  scripts/launch_alpha10.py
  backend/srw/
  frontend/dist/
  convergence_tests/knowledge_fixture.py
  explorations/html-site/serve_e1.py
```

On Windows, `START_NATIVE_LAB.cmd` uses **installed Python 3.12** and creates a
local virtual environment in `app/runtime`. It then generates five
**synthetic/minimal** Knowledge databases, and starts the **real WPF
`SmartRecruitmentWorkbench.exe`** with a **fresh temporary** workspace and
unique application identity. The WPF Host owns its backend process and
`app.lock`; it is still the *desktop-owned Core* model, not the detached E4
supervisor model.

A GET-only E1 browser adapter attaches to the **same host-owned C11 Core**,
verifying the dynamic-port lease and shared synthetic project. This is the
first concrete step toward EXE and browser data interoperability.

## Native acceptance requirements

CI must individually prove:
1. original canonical WPF source compiles with exact SDK/locked deps;
2. modified lab-source copy compiles with exactly two reviewed path edits;
3. the assembled Native SOURCE Lab package's SHA-256 file manifest passes;
4. the local Python venv installs the pinned C11 test packages and interpreter
   reports its **own** venv prefix;
5. the **real WPF EXE process** starts, publishes the host lease and brings C11
   backend to desktop-ready state;
6. the E1 browser sees the same synthetic Core project via live HTTP;
7. `frontend_loaded` is written by WebView2 navigation, not just the backend;
8. exit releases processes and temporary SQLite/Knowledge resources.

A failed GUI or runtime smoke must **not** publish the Native Lab as accepted.
The separate canonical host-only compile result can remain green.

## What has not been achieved

Even after all synthetic smoke checks pass, this is not a standalone release:
- Python 3.12 and .NET 10 Desktop Runtime must be installed on the host;
- WebView2 Runtime must be available;
- five Knowledge DBs are *synthetic*, not production;
- the test backend uses the pinned **source CI** package set rather than an
  audited complete standalone Python distribution;
- no real-corpus, OCR/ASR/AI provider, full 0.8.x parity or upgrade/migration
  test is claimed;
- stopping the WPF EXE still stops the owned backend and the attached E1 Web;
- the detached E4/E5 Core model remains a separate future Windows Host change.

Never point the lab at an existing SRW v0.8.x/C11 data directory or copy real
candidate records into the test workspace.

## Evidence

- [Source-only canonical WPF compile](https://github.com/ALV522/-SRW-/actions/runs/39194211548)
- [Native Host Sandbox workflow](https://github.com/ALV522/-SRW-/actions/workflows/native-host-sandbox.yml)
- [E1–E5 isolated browser/Core experiments](https://github.com/ALV522/-SRW-/actions/workflows/html-site-sandbox.yml)

A test package link should be published only after the full WPF backend +
WebView2 + E1 shared-Core acceptance job succeeds.
