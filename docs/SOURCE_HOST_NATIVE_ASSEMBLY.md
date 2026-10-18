# Source-built Windows Host Native Candidate: end-to-end assembly

This path avoids dependence on the historical v0.8.8 exact Windows carrier. It does **not** claim the rebuilt host has passed a Windows WPF/WebView2 GUI acceptance.

## Inputs

1. A checked-out exact GitHub C11 `main` commit (source ZIP without its `.git` folder is insufficient for default exact-commit matching).
2. `SRW_C11_Legacy_External_Inputs_RECOVERED_UNVERIFIED.zip`, extracted to a separate folder containing `runtime/`, `knowledge/active/`, `PRODUCTION_RUNTIME.sha256`, `PRODUCTION_KNOWLEDGE.sha256`.
3. A Windows Host candidate artifact **built by the GitHub Windows Host workflow for that same Git commit** and extracted to another folder. It must contain `SmartRecruitmentWorkbench.exe`, `HOST_BUILD_CANDIDATE.json`, `DOTNET_BUILD_TRUTH.json` and its framework-dependent companion binaries.
4. A Windows Python 3.12 environment for invoking build tooling. The embedded Runtime is **not executed** during archive assembly.

The historical alpha10 Runtime does **not** currently meet the 13 C11 pinned dependency requirements. Eight packages are older or absent. Restore it first but upgrade/reconstruct a separate candidate Python Runtime to match `requirements-ci.txt`; regenerate the external file manifest after controlled installation and rerun `check_embedded_runtime_compatibility.py`. Do not modify the pinned historical originals.

## Build (Windows x64)

```powershell
# Exact source checkout, from its own root
py -3.12 scripts/check_source_integrity.py
py -3.12 scripts/check_embedded_runtime_compatibility.py --runtime "D:\SRW\external\runtime"
py -3.12 scripts/build_native_from_source_host.py --root . --inputs "D:\SRW\external" --host "D:\SRW\host-from-actions" --out "D:\SRW\SRW_C11_Windows_Native_UNVERIFIED_GUI.zip"
```

The assembler verifies every source SHA, staged Runtime SHA, strict version pins, five Knowledge SQLite hashes/tables, Host git revision/digest/build truth, then the finished ZIP exact member set and SHA values. It blocks mismatched source/Host identity, incompatible legacy Python or unknown private files in the Host folder. It cannot silently publish or mark WPF GUI accepted.

The resulting `UNVERIFIED_GUI` archive still needs Windows 10/11 x64, Microsoft .NET 10 Desktop Runtime (current Host is framework-dependent), Microsoft Edge WebView2 Runtime, full launcher/API/desktop integration testing, backup/restore acceptance, and synthetic recruiting workflows before promotion.

## Historical-host alternative

If the exact `SRW_v0.8.8_Windows_Portable.zip` can be recovered with SHA-256 `f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab`, the existing `BUILD_WINDOWS_NATIVE.bat` / `scripts/build_windows_native_from_v088.ps1` inheritance route remains available and unchanged. The source-built-host route **does not** pretend to inherit that carrier's identity. See [legacy resource recovery](LEGACY_RESOURCE_RECOVERY.md).
