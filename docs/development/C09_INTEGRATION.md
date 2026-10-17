# C09 integration plan and execution record

Scope: integrate C09 with the repaired C08 main baseline, preserve capability semantics, establish a current source integrity gate, bind release metadata, and verify on Ubuntu/Windows before merging.

Upstream parents: main 487e060423977db00c785d0879018d432ace61cb; C09 bc1d3ca04f2186f1eda41e72b4eff688ceefc62e.

1. Preserve C08 historical manifest; verify current reviewed source with a separate manifest. Detect missing, changed, unsafe, duplicate and omitted tracked paths.
2. Repair the Windows resource-probe blind spot; verify a real open SQLite file is detected and disappears after close.
3. Promote source metadata to C09, including launcher identity, while preserving old verification evidence as historical. Do not claim a Portable or Native artifact exists.
4. Run source tests, compile, frontend syntax, release binding and source integrity checks; independently review the complete integration diff.
5. Push an integration branch with both upstream parents, require both OS jobs, merge via PR, and inspect main CI.

Ruling: ordinary git clone cannot authenticate in this environment. Use an exact GitHub connector snapshot in an isolated local branch; verify downloaded bytes against upstream Git blob IDs. Publish using Git trees and a two-parent commit, preserving real upstream ancestry rather than pushing the local snapshot history.

Ruling: the 212-file C08 SHA manifest is immutable historical evidence, not a permanent prohibition on modifying source. Preserve it byte-for-byte and create a separate complete current manifest.

Baseline: C09 local 55-test suite passed. The main integrity checker fails on seven legitimate C09 modified files (no files missing).

Regression reproduction: SQLite probe returns no files without /proc despite an open SQLite connection. New source-manifest validation interface is absent in the C08 checker.

Local verification: 65/65 regression tests passed; compile, frontend syntax, strict resource gate and release binding passed. Current source inventory has 239 entries. Independent read-only reviewer reproduced these results and found no critical, important or minor issues. Historical C08 snapshots were checked byte-for-byte.

Publishing status: automated approval review rejected GitHub create_tree twice, including after confirming the existing private repository ALV522/-SRW- (id 1358834882), admin/push permissions and scanning the 31 changed text files for credential patterns. The stated requirement is explicit end-user authorization naming this payload and destination. No new remote tree/commit/branch/PR was created. Dual-OS CI and main merge remain pending that authorization.

Local Git commits are review checkpoints only, not upstream history. Do not push this reconstructed local history. The planned remote commit must retain the actual upstream main/C09 parents recorded above.
