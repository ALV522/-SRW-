# Release and rollback procedure

## Source promotion

1. Work from a reviewed integration commit. Update VERSION, BUILD_INFO, release_state, PORTABLE_MANIFEST, verification inventory/truth, Host status and README together. Keep historical evidence unchanged.
2. Update SOURCE_MANIFEST.sha256 from the complete reviewed tracked inventory, excluding only the manifest itself. Never regenerate a manifest merely to hide an unexplained mismatch. Review file deletions and changed hashes in the PR. SOURCE_RECOVERY_MANIFEST.sha256 is immutable C08 evidence.
3. Pass source integrity and release binding. Run the full current suite with strict resource checks, Python compile and Node syntax on Ubuntu and Windows.
4. CI builds a manifest-only deterministic source ZIP, embeds BUILD_PROVENANCE.json with exact commit and manifest digest, and emits a SHA-256 sidecar. Download from the successful run matching the intended commit, not a previous branch run.
5. Merge with an expected-head SHA guard, then verify main CI. Only then create a version tag/Release referring to that exact source commit and attach its corresponding assets. A source-only tag must say source-only; do not label it a Portable or native release.

The source hash manifest and Git history jointly protect against accidental omissions and corruption; they are not a signing system or a substitute for review. LF checkout normalization is specified in .gitattributes for cross-platform hashing.

## Portable and Native promotion

Before attempting assembly, run `python scripts/portable_input_preflight.py` with the exact Windows carrier, embedded Python, an independently audited PRODUCTION_RUNTIME.sha256 listing every intended Runtime file, and a trusted external PRODUCTION_KNOWLEDGE.sha256 inventory. Exit code 2 blocks promotion. Passing this inventory only establishes presence, expected SHA hashes and read-only SQLite validity; it does not prove the external manifest's provenance, runtime launch or GUI acceptance.


A Portable build must include the separately audited embedded runtime and five production Knowledge DBs, their hashes and an exact-artifact check. Never ship synthetic test Knowledge fixtures as production data. Verify launcher dependencies, backup/restore and data migration on the assembled artifact.

Native assembly must stage only reviewed files listed by SOURCE_MANIFEST.sha256, runtime files enumerated by the independent Runtime SHA-256 manifest, five audited Knowledge DBs and the exact inherited Host. Reopen the finished ZIP and verify its complete member allowlist, hashes and UNVERIFIED_GUI provenance before reporting a candidate build. The candidate ZIP name includes UNVERIFIED and must not be published as production without GUI and data-exclusion acceptance. Native additionally requires SRW_v0.8.8_Windows_Portable.zip with SHA-256 f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab and target-machine WPF/WebView2 GUI acceptance. The historical Web Portable asset is not interchangeable with this carrier.

## Rollback

Retain the prior verified source commit, release assets, checksums and pre-upgrade user-data backup. Roll back code using a reviewed revert or a separate checkout of that commit, preserving Git history. Do not force-reset shared main. C09 retains schema v1_0014, but code rollback never substitutes for validating data compatibility. If data was migrated or restored, use the corresponding tested backup procedure; do not overwrite live data blindly.

## Evidence boundaries

GitHub CI logs belong to their recorded commit. Old reports under verification/ and the C08 metadata snapshots remain historical. Source test success does not assert GUI, provider-live, full 0.8.x parity or real-corpus quality acceptance.
