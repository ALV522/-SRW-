# P0 #42 · Pinned Windows Native predecessor input audit (2026-10-22)

This is **input verification**, not a Native build or GUI acceptance report.
The local operator supplied the exact original prepared Windows Native ZIP;
the complete original ZIP, embedded Python, production Knowledge databases,
private candidate data and application secrets are **not** checked into Git.

## Evidence acquired (offline Linux; verified on actual pinned ZIP)

- Input: `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip`
  (uploaded copy has an additional `(1)` filename suffix).
- Original ZIP byte count: **101,617,623**.
- Full ZIP SHA-256: `27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb`.
- Original Prepared source identity: `d8d032de255c87839adbeedc5737124d7fbfc3cd`.
- Checked via unchanged `scripts.rebuild_native_from_prepared.stage_attested_inputs`:
  **2,332 Runtime files** and **five** Knowledge SQLite DB files (2,337
  selected members, **385,461,244** uncompressed bytes), all matched their
  independently verified archived SHA-256 manifests. The five SQLite DBs
  passed the repository `knowledge_checks` table and integrity checks.
- Current C11 `requirements-ci.txt` dependency metadata: **13/13 MATCH**
  against the recovered Runtime with C11 overlay on its import path.
- Exact current source bytes independently checked against their full
  `SOURCE_MANIFEST.sha256` before changing packaging scripts; source is newer
  than original Prepared ZIP and must **never** be replaced by older source.

## Still required before a Native candidate can exist

- A **same-commit** GitHub Windows WPF Host rebuild with matching `git_sha`,
  `HOST_BUILD_CANDIDATE.json`, `DOTNET_BUILD_TRUTH.json` and Host EXE SHA-256.
- A **real Windows x64** run of the extracted pinned embedded `python.exe -I -B`
  verifying Python 3.12, all **13 imports** and their exact Runtime paths,
  and no write-back to Runtime (the assembler creates separate
  `RUNTIME_UPGRADE_AUDIT.json` only after a successful executable smoke).
- Then `rebuild_native_from_prepared.py` must produce the new
  `UNVERIFIED_GUI.zip`, with fresh full source/Host/Runtime/Knowledge manifests
  and the package's independent `audit_zip` PASS. The output is **not RC/GA**.
- Static candidate verification, disposable Windows embedded backend and
  two actual WPF/WebView2 GUI cycles and full recruitment business/backup
  acceptance are **separate gates**. All are **NOT RUN** by this input audit.

## G1 safeguards

Use only a new isolated synthetic data root and never overwrite the original
prepared ZIP, real production database, Knowledge, older EXE or existing
acceptance evidence. The original ZIP hash is immutable and must not be
"updated" merely to make a new file pass. The original production Knowledge
must remain outside this public GitHub repository and its Actions artifacts.

On a Windows x64 workstation with Python 3.12, download the **same-SHA
Source+Host kit** from the successful GitHub Windows Host workflow and run
its `BUILD_C11_CANDIDATE.cmd` with the pinned original ZIP and a new output
path outside the kit. Read `docs/C11_NATIVE_CANDIDATE_UPGRADE.md` and
`docs/SOURCE_REBUILT_NATIVE_ACCEPTANCE.md` before any GUI claim.
