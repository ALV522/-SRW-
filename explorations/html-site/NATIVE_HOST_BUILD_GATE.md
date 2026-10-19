# SRW Windows Native Host — Isolated Source-Compilation Gate

## Scope and why it matters

SRW has a checked-in WPF/WebView2 C# source project at
`desktop/SRW.Desktop/SRW.Desktop.csproj`, targeted at
`net10.0-windows` / `win-x64` with SDK pinned to `10.0.302` in
`global.json` and NuGet packages locked in `packages.lock.json`.

The existing `BUILD_WINDOWS_NATIVE.bat` calls
`scripts/build_windows_native_from_v088.ps1`; that packaging path is
currently gated on an audited historical `SRW_v0.8.8_Windows_Portable.zip`
carrier (SHA-256 is pinned), embedded Python runtime, production Knowledge DBs
and manifests. **This E5 source-compilation experiment does not bypass that
release provenance or promote unverified binaries.**

## Added Windows experiment

A distinct branch-only workflow:

[SRW Windows Native Host Source Sandbox](https://github.com/ALV522/-SRW-/actions/workflows/native-host-sandbox.yml)

- checks out the existing C# project **without modifying it**;
- installs the exact pinned .NET 10.0.302 SDK;
- restores the already-locked WebView2 NuGet dependency graph;
- attempts WPF source build in Release for `win-x64`;
- verifies the resulting SmartRecruitmentWorkbench.exe exists;
- records SHA256 and provenance with explicit `portable=false`,
  `native_gui_accepted=false`, and `runtime_included=false`;
- uploads a separate host-only artifact with **NOT-PORTABLE** in its name.

## Interpretation

A green source compile demonstrates only C# build reproducibility and
source availability. It does **not** prove:

- the compiled executable can start a complete SRW product;
- a verified Python C11 backend/runtime is present;
- five production Knowledge databases have been included;
- WPF/WebView2 UI and host lifecycle actually work on a user's PC;
- feature parity against mature v0.8.x;
- real EXE/Web Browser simultaneous state sharing.

A failure in locked restore/SDK/build will be logged as such instead of
replacing provenance inputs or modifying normal `main` releases.

## Next real product gate

Compile the host, prepare a separately reviewed and hash-attested Python
runtime + production Knowledge payload, stage the full C11 source/assets,
and run Windows **native GUI smoke** plus EXE/browser coexistence.

This must occur through an explicit product-development/review process after
the experimental evidence is solid; the source-only WPF build is not a product.


## Next step: Native SOURCE Lab integration attempt

A **separate** experimental assembly path has been added:

- `assemble_native_lab.py` copies explicitly allowlisted C11 source,
  previously compiled hash-attested WPF host files, and a Python launcher;
- `run_native_lab.py` creates a local Python 3.12 venv, generates **only
  synthetic** Knowledge fixtures and gives WPF a new temporary data root;
- `START_NATIVE_LAB.cmd` (when the build succeeds) starts the real WPF host
  rather than a browser-only desktop surrogate;
- the script checks `app.lock/instance.json`, desktop runtime identity,
  backend readiness, same-Core E1 browser read-only project access, and
  the `frontend_loaded` Host log event when `--strict-gui` is specified.

GitHub Actions Windows runs the source lab as a **separate job** after the
source compile. Its status must be independently inspected. If the synthetic
GUI readiness test fails, the WPF host-only build remains a valid compile
result; no Native source preview is promoted or published.

The Native SOURCE Lab is **not** a standalone Windows Portable even if its
GUI starts: it needs system Python 3.12 and .NET 10 Desktop/WebView2 Runtime,
uses test Knowledge and test database, and excludes real AI/OCR/ASR acceptance.

No approved historical 0.8.x carrier, official resource manifests or
production releases are modified to make this experiment run.
