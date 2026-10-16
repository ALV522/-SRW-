# SRW — Business Convergence 08

## Product direction

Convergence 08 treats **v0.8.12-R2 as the capability-completeness reference**. The objective is not a lighter replacement. The objective is to retain 0.8.x evidence, lineage, privacy, calibration, decision operations, knowledge governance, intelligence, portability and release discipline while improving workflow organization and desktop usability.

## C08 additions

- Claim → PDF graphical grounding: verified page/bbox is rendered as an image with the evidence rectangle highlighted.
- Controlled competency-alias curation with semantic diff, exact digest activation and byte-exact rollback.
- Backup restore rejects duplicate ZIP entries, unsafe paths and excessive expanded payloads before SQLite access.
- Candidate/contact CSV exports guard formula-leading text fields for spreadsheet safety.
- Full project package portability: project-scoped business state plus content-addressed Source blobs, strict ZIP/blob/schema validation, Preview → exact SHA-256 → Commit, ID remapping and historical Decision Context preservation.
- Project package import is explicitly PII-bearing and requires current-context reevaluation; old decisions never silently become current.
- Cumulative capability-recovery tests: **46/46 PASS**.

## Windows Native Host

The current artifact remains Host-ready and includes the restored WPF/WebView2 Host source and ABI. `BUILD_WINDOWS_NATIVE.bat` still requires the exact audited v0.8.8 Windows carrier SHA-256 and refuses mismatches. A Windows Native ZIP is not claimed until the exact carrier is available and the assembled artifact is smoke-tested on Windows.

## Verification

Use `VERIFY_CAPABILITY_RECOVERY.bat` for the cumulative recovery suite. `VERIFICATION_INVENTORY.json` distinguishes current executed gates from the 725-test v0.8.12 reference inventory.
