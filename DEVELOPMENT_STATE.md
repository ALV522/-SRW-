# SRW Development State — Convergence 11

> **最新项目状态（2026-10-19；main `c9d70cd48d03`）**：Ubuntu/Windows 各 146 项源码测试、5 项真实 Chromium 业务场景、280 项仓库完整性校验 PASS。旧 `d8d032d` Windows Native 候选包已在真实电脑上通过 WPF/WebView2 基础启动、项目创建、标准草案更新和正常退出验证，仍非正式 RC/GA。本文其余“138/121/109 项”和“GUI 待验收”等内容属于不同开发阶段**历史追加记录**，不得取代最新身份与证据。请优先查看 [README](README.md)、[Windows GUI 实机报告](docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md)、[路线图](docs/ROADMAP.md)。


> **最新业务增量**：`c9d70cd` 还新增两条真实 Chromium E2E：独立面试 Scorecard 分歧保留与 Offer Draft→Approved→Sent→Accepted 人工状态流；主线 Chromium 总量现为 **5** 项。该增量保留旧决定必须由人类确认的约束。参见 [验收记录](docs/BUSINESS_E2E_SCORECARD_OFFER.md)。

Version: `1.0.0-alpha10-convergence11`; schema `v1_0014`; capability reference `v0.8.12-R2`.

## Integrated capabilities

C08 business capabilities are retained. C09 supplies local-only Host and browser same-origin checks, known interrupted-backup cleanup, structured diagnostics, independent synthetic Knowledge fixtures, SQLite shutdown disposal and Ubuntu/Windows Python 3.12 regression gates. C10 adds a privacy-safe deterministic diagnostic support bundle with explicit exclusion of candidate content, Source blobs, database bytes, provider secrets and local filesystem paths. C11 changes the center of gravity from infrastructure to product workflow: the home dashboard now surfaces the decision workbench as an actionable queue, deduplicated to the highest-priority open action per candidate, and routes the operator directly into candidate evidence/decision or interview work. The same dashboard now surfaces overdue and same-day candidate contacts plus completed interviews missing submitted feedback, with direct navigation back into the operational action. A unified review center makes pending identity reviews, judgment-correction reviews and unreviewed evidence claims actionable from the home screen. Judgment-correction review is now end-to-end: candidate context is visible and an operator can explicitly resolve the item with a required review note. Project home also derives one explicit next action from current business state, reducing the need to interpret internal modules or hunt across tabs. Candidate brief and project handoff views now present readable business summaries with a full JSON handoff download retained for transfer/audit; dashboard contact actions open the specific candidate action plan rather than a generic queue. The candidate workspace has been promoted from a modal into a full project surface with separate Evidence & Decision, Process & Follow-up, and Offer modes, while preserving the existing evidence, verification, decision, intake, OCR/ASR and Offer actions. Candidate-specific phone screens, interview scheduling/completion, independent Scorecards and reevaluation drafts are now directly available in Process & Follow-up. Job setup is now a true four-step guided Draft flow; state is preserved across steps, suggestions are rendered as readable cards, and no suggestion or setup action can silently publish the recruiting protocol. Criteria editing now preserves recruitment context, decision policy, criterion metadata, criterion weights and assessment-stage membership when saving the Draft.

Integration separates immutable C08 source history from the current complete source hash inventory. Windows file-handle checks now enumerate real process handles through psutil instead of returning an empty Linux-only /proc result. A real SQLite open/close test runs on each OS. Probe errors fail the run rather than manufacturing PASS.

The current suite contains 138 tests. Runtime counts and results are emitted by CI for the exact commit. This document does not substitute for that evidence. Release identity is C11 throughout; historical C08 metadata is preserved under verification/history/convergence08.

## Delivery

CI uploads source ZIP, SHA-256 sidecar, regression log and installed dependency versions. The source ZIP records its exact commit and manifest hash. Portable/native artifacts remain unbuilt in this source line. Windows source verification is not WPF GUI acceptance.

## Remaining work, in order

1. Continue business workflow closure against v0.8.12-R2: project setup, intake, screening, evidence review, interview, decision, offer, operations and handoff must each be usable without API knowledge.
2. Run the end-to-end UI acceptance plan and convert every concrete workflow break into a product defect with a regression test.
3. Recover/audit the embedded runtime and five production Knowledge DB assets for a fresh Portable assembly.
4. Assemble with the exact Windows carrier and run target-machine GUI acceptance.
5. Validate external providers and an anonymized resume corpus with human review.
6. Restore additional high-value gates from the historical 725-test inventory while avoiding infrastructure work that does not close a user-facing workflow.
7. Decompose large workbench/frontend modules only behind preserved behavioral coverage.
8. Complete historical Git/Release privacy audit (private visibility alone is not that audit).

## Git and release workflow

main contains reviewed, merged source. Integration/fix branches use PRs and both OS gates. Require current source integrity, release binding, compile, JavaScript syntax and resource regression before promotion. Publish/tag only the exact verified commit; document source versus Portable versus Native artifact type. See docs/RELEASE_PROCESS.md.

## P1 active queue and calendar correction

Current decision-work items exclude archived projects and rank globally by explicit business priority, not task-type spelling. Project-level workbench lookup is scoped at query time. The operational queue applies host-local calendar midnight for today's contacts and limits each preview category separately before sorting. Windows user-flow/GUI acceptance remains pending.

## Exact review item navigation

Identity and judgment review dashboard links now carry review_id, and Claim review links carry claim_id. The destination focus routine locates the exact active record, scrolls to it and highlights it; it reports stale/missing targets instead of silently showing an unrelated list. This is frontend source coverage until real browser E2E acceptance.

## Windows Portable input readiness

Added a non-destructive, source-level Portable input preflight for the exact inherited Windows carrier SHA, embedded runtime entrypoint and five externally audited Knowledge hashes with SQLite integrity/table checks. It fails closed with a machine-readable report when files are absent or mismatched. No runtime/Knowledge bytes are stored in Git and no Portable/Native artifact is declared built. The external manifest's provenance and exact Windows GUI acceptance remain separate manual gates.

## Native assembly hardening

Fixed the legacy assembler's source-root wildcard copy that could accidentally include workspace data, backups and local secrets. It now stages only SOURCE_MANIFEST-listed reviewed source, the exact carrier's inherited Host and separately preflighted runtime and five production Knowledge DBs; output filenames reflect C11 and mark unverified GUI status. The PowerShell script uses hostExe instead of PowerShell's reserved Host variable. No actual native binary has been produced or GUI accepted in CI.

## C11 backup manifest and restore integrity

Integrated the previously isolated backup-integrity implementation into the real backup and startup restore paths. New backup archives contain a SHA-256 manifest for the SQLite snapshot and Source blobs. Restore validates structure, member hashes, SQLite integrity, schema, limits, and disallowed paths before extracting into a temporary staging directory; tampering leaves the current database and pending marker untouched. Legacy archives remain readable under a restricted DB/blob-only layout and explicitly report weaker integrity. Automated synthetic roundtrip/tamper/restore coverage is added, but interrupt/crash injection and Windows exact-artifact validation remain pending.

## Final Native ZIP payload closure

Native packaging now requires an external audited manifest for every embedded Runtime file, stages only those files, and audits the entire resulting candidate ZIP against source, Runtime, Knowledge, and Host digests. Unexpected members, file tampering, and falsely claimed GUI acceptance block candidate assembly. Synthetic regressions are cross-platform. Real production assets and WPF/WebView2 acceptance remain unavailable in this source checkout.

The assembler now uses PowerShell hash checks to stage an isolated Runtime and reviewed source before launching any embedded Python. The launcher self-check uses temporary data outside the release tree rather than creating staged user data. Tests protect this ordering and launcher import side effects.

## Chromium browser acceptance gate (verified on 69f60b9)

Added a separate Ubuntu real-Chromium/Playwright integration workflow, backed by a disposable local SQLite database and generated synthetic Knowledge fixtures. It exercises UI clicks through project creation, four-step Draft Job Setup, candidate text intake, action plan, interview scheduling and draft Offer, then checks persisted API results. This gate passed 3 Chromium workflows on exact main commit 69f60b9. WPF/WebView2 and real Windows Portable acceptance remain pending. See docs/BROWSER_ACCEPTANCE.md.

## Chromium-discovered candidate intake defect

The initial Chromium run exposed an HTTP 409 in candidate workspace when a newly collected and published material revision existed before job standards were published. This was incorrectly hidden as missing material by the UI. The read-only workspace now returns Source/Claim content and a blocked (empty) decision context until published protocol and material exist. Decision controls are disabled in that state; published-context calculation remains unchanged. Three additional source tests cover draft-only, post-publication and nonexistent candidate cases.

The second browser run also revealed that the Offer create button was shown for an ineligible new candidate. It is now disabled unless the candidate is in interview or offer stage; Chromium acceptance verifies genuine human new -> shortlisted -> interview transitions before saving an Offer Draft. The backend stage guard is preserved.

## 2026-10-18 GitHub repository governance and historical ZIP audit

The root README has been consolidated as the current user/developer entry point; docs/REPOSITORY_GOVERNANCE.md now records the single `main` source trunk, historical branches, module map, CI/evidence, artifact kinds and delivery blockers. docs/history/ARCHIVE_CATALOG.md and LEGACY_ARCHIVES.json record the four uploaded historical ZIPs' exact SHA-256/size and explicitly state that original archive bytes were NOT uploaded to GitHub. Three packages contain large Knowledge databases and an alpha Web Portable additionally contains executable Runtime components. No production database content was treated as cleared for publishing. A read-only ZIP safety/hash tool and four isolated tests were added. The historical 725 test inventory remains reference only; current regression count is now 113 (pending exact-commit verification on this change).

## 2026-10-18 Legacy external dependency recovery and alternative Host build

Actual user-uploaded alpha10 Web Portable contains 1,611 embedded Windows Python 3.12 Runtime files (99,144,143 uncompressed bytes), including the public certifi CA trust store. v0.8.12-R2 contains five intact Knowledge SQLite DBs: integrity_check=ok; their SHA-256 hashes match same-name DBs in v0.8.10 source and alpha10 Web Portable. Recovered contents/manifest have been delivered as a separate UNVERIFIED external inputs ZIP (not stored in Git). Embedded Python packages match only 5/13 pinned current C11 requirements; eight are missing/outdated, so Native preflight now explicitly rejects an incompatible Runtime before assembly. The four current user archives do not include a compiled Windows Host; v0.8.10 Assembler contains an Application Overlay, not the exact Windows Portable carrier. A new GitHub Windows Host source-build CI gate attempts an unsigned framework-dependent WPF/WebView2 Host compilation from locked .NET inputs. Compilation and WPF GUI acceptance remain separate; see docs/LEGACY_RESOURCE_RECOVERY.md.

## Alternative source-built Windows Native assembly

A second, separate Windows Native assembly path has been implemented using the digest-bound WPF/WebView2 Host candidate from GitHub's Windows Host build workflow rather than the exact historical v0.8.8 carrier. The new assembler requires an exact matching Git source commit, source SHA manifest, restored/runtime-upgraded Python pinned to current C11 requirements, five Knowledge SQLite databases, and matching Host build provenance. The finished ZIP is re-opened for an exact allowlist/hash audit and remains explicitly UNVERIFIED_GUI. Four synthetic packaging and privacy regression tests were added. The existing historic carrier inheritance path is preserved. This is an unverified candidate builder: the historical alpha10 Python dependencies still need compatibility updates before actual candidate packaging, and WPF/WebView2 GUI acceptance is separate.

## Offline Windows Python wheel overlay (pending exact-commit acceptance)

Created an independently checksum-bound Windows/Python 3.12 wheelhouse CI and a fail-closed offline Runtime upgrade utility. Original alpha10 Runtime and five historical Knowledge databases remain untouched. Upgraded packages reside under `Lib/c11-overlay`, which is inserted before legacy `Lib/site-packages` in `python312._pth`. The utility requires all C11 pinned metadata versions and executes actual isolated `python.exe` imports before emitting a new runtime SHA inventory and `RUNTIME_UPGRADE_AUDIT.json`. The alternate Native assembler now refuses an overlay with no matching C11 runtime smoke audit. Added 7 source regressions (125 -> 132). Wheelhouse CI smoke cannot validate a private recovered old Runtime until the same user recovery inputs are present on an authorized Windows execution environment; WPF/WebView2 GUI and provider-live acceptance remain pending.

## 2026-10-19: Actual assembled C11 Native candidate, static-verified and GUI-unverified

Using actual same-source d8d032d Actions source, Windows WPF Host, 13 locked Windows wheels and the user's uploaded historical Runtime/five Knowledge DBs, assembled `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip` (101617623 bytes; SHA-256 27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb). Legacy Runtime bytes remain preserved; offline target win_amd64 wheel overlay was installed separately, 13/13 pinned metadata matches, 2332 Runtime hashes and five SQLite DBs pass; audited final ZIP has exactly 2629 expected SHA-bound members. No Windows embedded interpreter or WPF GUI was executed in the Linux staging environment. New `scripts/verify_prepared_native.py` provides immutable on-target source+runtime+Host+Knowledge verification, actual Windows Python import smoke and synthetic backend Host ABI/loopback readiness, with evidence outside candidate root; GUI manual acceptance remains mandatory. Added 6 synthetic regressions (132 -> 138). See `docs/PREPARED_NATIVE_WINDOWS_ACCEPTANCE.md`.

## 2026-10-19 Windows x64 user-provided real backend smoke PASS

On an actual user Windows x64 machine, the pinned d8d032d prepared package passed 273 source, 2332 Runtime, 5 Knowledge, 13 dependency and 15 Host member integrity checks, then ran embedded CPython 3.12.10 importing 13 C11 libraries, launched the real SRW loopback backend in an isolated synthetic workspace and validated the Host ABI/runtime identity. The saved `C11-Windows-smoke.json` states `WINDOWS_BACKEND_SMOKE_PASS_GUI_PENDING` / `gui_accepted=false`. A subsequent invocation on the same extracted root returned unreviewed file delta; the initial import smoke did not use `-B`, so generated bytecode is the leading hypothesis, not independently proven until inspecting the delta. This patch suppresses interpreter bytecode writes for smoke and new WPF Host, reports exact unexpected/missing paths without relaxing fail-closed SHA allowlists, and rejects evidence overwrite before executing. Regression count 138 -> 141; Windows GUI, provider/OCR/ASR and business operations remain unaccepted. See docs/WINDOWS_FIRST_SMOKE_RESULTS.md.

## 2026-10-19: verified Windows GUI startup, business writes and graceful shutdown

User-supplied Windows screenshot and complete 45-record Host JSONL establish actual WPF window display/WebView2 initialization/frontend_loaded, runtime health endpoints HTTP 200, successful POST /api/v1/projects (200), successful PATCH /api/v1/protocol-revisions/<id> (200), and clean shutdown_requested/backend_stopped/workspace_released/host_closed. Timing for that single machine/session: ~3.03 s Host->backend_ready; ~4.92 s Host->frontend_loaded. One harmless /favicon.ico HTTP 404. No recorded backend crash, retry or HTTP 5xx. User additionally showed runtime/Lib/c11-overlay/**/__pycache__/*.pyc files, confirming these generated cache files are present after first smoke and likely account for immutable-member check failures. Original artifact remains d8d032d, not silently mutated or re-labelled. New read-only scripts/audit_windows_host_gui_log.py produces scrubbed GUI lifecycle/business HTTP evidence, tests block cross-session aggregation and errors. **Windows GUI baseline PASS; full recruitment, OCR/ASR, Provider, Knowledge governance and restore acceptance remain OPEN**, so not RC/GA. Total current source regressions: 146. Full scope at docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md.

## 2026-10-19: Decision Context staleness and guarded manual reaffirmation

Added sixth real Chromium/HTTP/SQLite test of published verification-critical criteria, human verification-generated Source/Claim/Judgment, explicit HumanDecision, material revision staleness, blocked premature reaffirmation, renewed grounded verification and human-authored context-bound reaffirmation lineage. Product bug fixed: `CandidateWorkspace.decision_reaffirmable` now uses the exact action-specific `_action_gate` rather than merely detecting a stale decision, and the UI disables “按当前证据重申” until the current evidence permits the operation. No external AI result mocks. Native WPF GUI acceptance remains distinct. See docs/BUSINESS_E2E_DECISION_LINEAGE.md.

## 2026-10-19: protocol-republication stale HumanDecision acceptance

Added E2E-07 against genuine Chromium/C11 API/disposable SQLite: project ProtocolRevision is newly published with another verification-critical criterion while all candidate Source IDs remain unchanged. The old HumanDecision must become stale, the unverified revised criterion blocks decision readiness, and both API/UI reject premature reaffirmation. This complements the already accepted E2E-06 material-change scenario; it is not a Windows native manual acceptance. Exact-commit CI remains the authority for PASS. See docs/BUSINESS_E2E_PROTOCOL_REVISION.md.

## 2026-10-20: P0 #41 fail-closed decision history without active context

A real SQLite and HTTP regression found historical HumanDecision entries falsely represented as both `is_current_context=false` and `stale=false` when no active published Protocol or MaterialRevision could supply a current context hash. The read-only lineage projection now marks those old decisions stale; existing decisions, audit and action permissions stay unchanged. Four synthetic source/API regressions cover both absence cases, active context and real HTTP history. Schema v1_0014 and VERSION unchanged. Base main SHA `54548ee29a78072ff036c5ac19b062e08452ef1e` Source Gate actually executed 174 tests; previous 146 count in inventory was stale, new expected source test count 178 subject to exact-head CI. Browser actual base main CI exercised eight synthetic scenarios, not the old stored seven. No new Windows Native or dual carrier GUI acceptance asserted.

## 2026-10-21: HTTP 层分解切片 1 — Provider 探测/OCR/ASR 归位 providers 域（本地执行）

按 [ADR-0002](docs/decisions/ADR-0002-http-layer-decomposition.md)（负责人 2026-10-21 批准）启动 HTTP 层分解，首个切片把 `api/fullworkbench.py` 中内联的 Provider 配置投影、能力探测、OCR/ASR 字节处理提取为新域模块 `backend/srw/providers/probing.py`（185 行），HTTP 侧只留 thin adapters；`api/fullworkbench.py` 1714→1642 行，行为与请求/超时/错误映射逐字保持不变，`/api/v1` 路由契约零变更。新增 `convergence_tests/test_provider_probing.py` 16 项（fake secrets/settings + fake httpx 传输，无真实网络、无候选内容），含 GET `/api/v1/settings/providers` 的 HTTP 边界集成测试；此前无任何测试覆盖这三条 Provider 路由，属净增覆盖。Schema v1_0014、VERSION、发行状态不变。**执行方式：经负责人授权仅本地执行（任务分支 `dev/43-http-decomposition-slice1-providers`，不 push、不建 PR、不合入），GitHub CI = NOT RUN。** 本地实测：`python -m unittest discover -s convergence_tests` 252 项 = 247 PASS / 3 skipped（平台门禁）/ 2 FAIL；2 项 FAIL（`test_rejects_symlink_database`、`test_rejects_malicious_host_symlink`）在未改动 main 的干净 worktree 上原样复现，属本机 Windows 临时目录 symlink 权限环境问题，非本次引入。远端 CI 验证与合并待负责人指令，届时按无保护协议走完整 PR 门禁。

## 2026-10-21: ADR-0002 HTTP 层分解切片 1–4 + 契约显式化 + 前端守卫（本地执行）

经负责人授权（“全部按建议、仅本地执行、D 盘新文件夹开发”），在 `D:/SRW-dev` 的任务分支完成 ADR-0002 分解第一轮：`api/fullworkbench.py` 1714 → 1485 行。切片 1 Provider 探测/OCR/ASR → `providers/probing.py`；切片 2 Knowledge apply 编排 → `modules/knowledge_governance/service.py`；切片 3 项目 Pipeline 读模型（含 next_action 链）→ `surfaces/project_pipeline.py`；切片 4 候选人对比/CSV 导出（含公式注入防护 `csv_safe_cell`）→ `surfaces/candidate_exports.py`。四切片均行为逐字保持、`/api/v1` 契约零变更，新增 46 项测试（Provider 三路由、knowledge/apply、pipeline、compare/CSV 路由此前零覆盖）。Schema v1_0014、VERSION、发行身份未变。

契约显式化：`scripts/check_api_contract.py` 将 146 条路由与 `docs/contracts/api-v1-inventory.txt` 基线比对，Source Gate（`test_api_contract.py`）与 CI 双通道强制路由漂移即失败；`docs/contracts/API_V1.md` 记录分域不变量与错误映射。

前端守卫与缺陷修复：`scripts/check_frontend_contract.py`（`test_frontend_contract.py` 进门禁）静态校验内联处理器引用与静态 API 路径登记；借此发现真实潜在缺陷——app.js 的 `settingsPage/renderPage/tasksPage/projectWorkspace` 被内联 onclick/onchange 引用但未挂 window（ES module 作用域不可达，点击即 ReferenceError，含候选人下拉切换），已按文件既有模式显式挂载修复。修复使引用可解析（静态可证）；按钮实际行为待真实 Chromium 复验。

**前端六代基建合并与 app.js 按域拆分：BLOCKED**——本机无 Playwright/Chromium，无行为等价兜底手段，按既定规则不硬改；前置条件为可用的真实浏览器验收环境（CI 的 Chromium 门禁可在负责人授权同步后承担）。

本轮为本地执行（分支 `dev/43-http-decomposition-slice1-providers`，6 个提交），未 push、未建 PR、未合入；GitHub CI = NOT RUN。本地实测：全量 290 项 = 288 PASS / 3 skipped（平台门禁）/ 2 FAIL（`test_rejects_symlink_database`、`test_rejects_malicious_host_symlink`，本机 symlink 权限既有失败，未改动 main 的干净 worktree 复现）；治理三查（source integrity 340 项 / release truth / governance contract）PASS。

## 2026-10-21: #44 SemVer 原子迁移 1.0.0-alpha10-convergence11 → 1.0.0-alpha.11（本地执行）

按 VERSION_POLICY.md 第 4 节程序完成版本迁移（Issue #44 本地部分）：单一原子提交更新八处权威身份——VERSION、BUILD_INFO.json（version/release_id，source_revision 改为代码基线完整 SHA `4dc0c9f4491b892a1eaed8a8f5db8315ac156a56`，新增 engineering_milestone=C11 保留工程代号）、backend/srw/release_state.json（version，parent 记录 `1.0.0-alpha10-convergence11@45abc4c` 血缘）、PORTABLE_MANIFEST.json、VERIFICATION_TRUTH.json、VERIFICATION_INVENTORY.json、WINDOWS_NATIVE_HOST_STATUS.json、VERSION_POLICY.json（current_runtime_version/current_version_format=semver/next_product_version=1.0.0-alpha.12 proposed-not-effective/intended_channel/last_transition）。同步更新三处镜像当前身份的测试夹具与五处当前状态文档；历史证据（verification/、docs/history/、CONVERGENCE_DELIVERY.md 交付日志）与历史 alpha10 工件引用一律未改。Schema 保持 v1_0014 独立；发行通道仍为 development，未 tag、未发布。本地实测：check_release_truth PASS、check_governance_contract PASS、全量回归维持基线；GitHub CI = NOT RUN（负责人授权仅本地执行）。RC/GA 门槛与双载体工件验收不变，见 VERSION_POLICY.md 迁移执行记录表。

## 2026-10-21: #41 业务 E2E 补缺 4 场景 + 前端处理器缺陷深修（本地实跑通过）

本地搭建隔离 Playwright/Chromium 环境（D:/srw-tools venv，CI 固定 1.56.0），首次在本机真实跑通浏览器验收：既有 9 场景全 PASS。新增 4 场景并全部本地实跑通过：test_10 知识建议经 UI 应用到标准草案（含 knowledge_source 溯源与 decision_critical 传递，为此扩充合成知识夹具的 alias_fts/competency_fts 检索表）；test_11 项目交接完整 JSON 下载内容核验；test_12 候选人 CSV 导出的公式注入防护（`=HYPERLINK` 合成名前导撇号）；test_13 内联页面处理器浏览器解析回归。

test_13 实证并深修了一类真实缺陷：app.js 四个页面入口函数（settingsPage/renderPage/tasksPage/projectWorkspace）此前未挂 window（ES module 作用域对内联 onclick 不可达）；仅挂函数仍不够——候选人下拉 onchange 与漏斗筛选 onclick 还直接引用模块作用域 `state`，本次新增 `selectFlowCandidate`/`filterCandidatesByStage` 两个拥有状态变更的 window 包装并重写两处 handler。`scripts/check_frontend_contract.py` 同步升级为可检出“内联处理器引用模块作用域绑定”（剥离模板表达式与字符串字面量后比对顶层绑定），`test_frontend_contract.py` 增至 5 项。全套 13/13 浏览器场景本地 PASS；全量源回归 291 项维持基线（288 PASS / 3 skipped / 2 既有 symlink 环境 FAIL）。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；本地执行未同步 GitHub。

## 2026-10-21：业务↔代码映射 + #43 Supervisor 设计稿（本地执行）

产出 `docs/development/BUSINESS_CODE_MAP.md`：12 个业务域逐一映射 modules/surfaces/api 落点、测试与载体覆盖；登记 6 个臃肿靶点（fullworkbench 余量 1485 行、两个 fullworkbench.py 同名、capability_recovery* 名不副实、前端六代重复、app.js 126KB）与 5 个覆盖缺口（身份合并/备份恢复/招聘智能 UI E2E、OCR/ASR 真实链路、双端并发），并立 5 条防再臃肿维护规则（新能力落 modules/surfaces、路由基线 CI 强制、前端处理器守卫、新场景必须真实 Chromium、状态只用证据）。

产出 `docs/decisions/ADR-0003-core-supervisor.md`（Proposed，待负责人批准）：S1 按需分离 Supervisor + 引用计数生命周期（载体永不持租约）；S2 Schema v1_0015 + If-Match 事务级 CAS（412 不产假审计）；S3 一次性会话附着 + CSRF/Origin + 撤销；S4 Job Engine 唯一所有权（复用现有 worker 租约与 idempotency_key）；S5 生命周期四原语；T1–T10 逐条落法；三相位实施与回滚。实现未启动——按负责人指令待 #41 E2E 补缺完成（已完成）后先设计，批准再动代码。

## 2026-10-23: #42 Windows 实机验收（本地执行，d8d032d prepared ZIP）

输入核验：`SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip` SHA-256 与固定值 `27ae4765…b2cb` 精确匹配；全新目录解压（2629 成员，与文档一致，未碰 10-19 旧解压）。`verify_prepared_native.py` 全量实机验证通过：2332 Runtime / 5 知识库 / 15 Host / 13 依赖文件在册，嵌入式 Python 3.12.10 全量导入成功，loopback 后端就绪，身份核验 true，合成工作区 true，证据落在候选包外；历史上“重跑出现未登记文件”的疑点未复现（全新解压 + `-B` 修复生效）。

**环境发现（非二进制缺陷）**：本机代理客户端环境下，Host 的 readiness 探测 URL 被双重编码（`http%3A//127.0.0.1%3A<port>/…`）→ 404 → force-kill 重试循环（两个候选 ZIP 均复现）；剥离代理变量后零 404、启动序列完整。源码侧无此模式：desktop 全树无 `EscapeDataString`，`RuntimeApiClient` 自 C08 起即 BaseAddress + 相对路径；c8431ca7 ZIP 内 Host 与 upgrade-kit 的 CI 编译 Host 字节一致（`f95b9b56…`）且干净环境下正常启动。结论：旧二进制健康，故障为本地代理环境干扰；运维注记——启动 Host 前剥离代理环境变量。

脚本化 GUI 验收（`D:/SRW/acceptance-20261021/scripted_gui_acceptance.py`）**PASS**：干净环境启动 → `backend_ready`（5.9s，Uvicorn loopback）→ 经宿主后端完成真实业务写入（建项目 200 / 建候选人 200 / 列表 200 / 候选人持久化 true）→ 优雅关闭链完整（shutdown_requested → backend_stopped → workspace_released → host_closed），后端随宿主级联退出无泄漏。日志审计：`project_created_http_200=1`、`host_shutdown_clean=true`、fatal=0、malformed=0；`wpf_window_and_frontend_loaded=false`——无头会话中 WebView2 无法初始化，GUI 级（点击级）验收按预案交负责人执行，规程见 `D:/SRW/acceptance-20261021/GUI-ACCEPTANCE-RUNBOOK.md`（精确 PowerShell、预期输出、失败处理、脱敏要求）。工件身份注记：该工件报告 `release_id=1.0.0-alpha10-convergence11`（构建于 C11 代码基线，早于本地 alpha.11 迁移，属预期）。

Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

## 2026-10-23: 前端整合步骤 1 — 六代基建收敛为 shared.js + 3 处跨 shim 缺陷修复（本地实跑通过）

Chromium E2E 环境就绪后启动前端整合。步骤 1：新建 `frontend/dist/shared.js`（`$/esc/fmt/api/toast/modal/modalWide/closeModal` 单一实现挂 window，行为取并集——toast 带根节点守卫与 3600ms、modal 标题转义、modalWide 保留 shim 的宽型 `min(1120px,94vw)`），`index.html` 首个加载（module 按文档序执行）；app.js 删 6 处私有定义改解构；convergence03–08 删各自 `cNN` 私有副本（共 22 处定义）并改写全部调用点。**借此发现并修复 3 处真实潜在缺陷**：c06/c07 在模块作用域调用 c05 的 `c05toast`/`c05modal`、c07 调用 c06 的 `c06api`——ES module 顶层声明不挂全局，这些 handler 一旦点击即 ReferenceError（运营学习页签的渠道观测保存/激活/回滚、ATS CSV 导入预览/提交全线断裂，且无任何 E2E 覆盖）；修复后全部经 window 全局解析。新增 test_14（渠道观测端到端：填漏斗→保存→toast→面板刷新→API 断言含 human_confirmed）本地 PASS。静态校验：全部裸调用可解析（模块定义 + window 全局），`check_frontend_contract.py` 8 模块 / 159 符号 PASS；本地实测：E2E 14/14 OK、源回归 291 OK（6 skipped，零失败）。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。
## 2026-10-23: 前端整合步骤 2a — app.js 抽出 dashboard/pages/jobsetup 三域（本地实跑通过）

Chromium E2E 兜底下启动 app.js 按域拆分。2a 抽取三个低耦合叶子域：`dashboard.js`（工作台总览）、`pages.js`（岗位模板/知识库/后台任务/系统设置四页及全部处理器）、`jobsetup.js`（四步建岗向导）。app.js 126KB→93KB（280→228 行），保留 core（state/路由/shell/启动/核心助手）。跨模块引用统一 `window.X()` 形式（与加载顺序解耦）；核心助手与页面渲染器按“谁定义谁发布”原则挂 window。

**过程故障与修复（当日实录）**：首轮 E2E 14/14 全红——`renderPage` 路由表与第 9 行胶水层仍按裸名引用已迁走的页面函数（`dashboard:dashboardPage`、`window.settingsPage=settingsPage`），ES module 作用域不可达，整个应用启动即崩。修复后暴露出静态检查器盲区：对象字面量里的**值引用**与胶水赋值不在调用模式内。已将该规则固化——`check_frontend_contract.py` 新增跨模块裸引用检查（函数在 A 模块定义、B 模块裸引用且未挂 window 即失败），`test_frontend_contract.py` 增至 7 项（含正/反两例）。此后每个拆分子步都受此规则 + 契约 + E2E + 源回归四道守卫。

本地实测：跨模块引用检查 CLEAN；`check_frontend_contract.py` 11 模块 / 176 符号 PASS；E2E 14/14 OK；源回归维持基线。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。
## 2026-10-23: 前端整合步骤 2b — app.js 抽出 protocol/candidates/events 三域（本地实跑通过）

2b 抽取三个业务域：`protocol.js`（标准编辑：criteriaTab/criterionRow/collectCriteria/saveCriteria/publishCriteria/forkDraft，97 行）、`candidates.js`（候选人收件/抽屉/工作台 HTML/联系/阶段/Offer/材料/Claim/核实/决定 + 联系工作台/行动计划/电话脚本/Scorecard/交接，64 行）、`events.js`（流程页/面试事件/完成反馈/复评，10 行）。app.js 仅剩 60 行 / 29.7KB（core + 工作区外壳待 2c）。前端共 14 模块。

**过程故障与修复（当日实录）**：E2E test_05（Offer 生命周期）超时——`openOfferStatus` 引用 `offerNextStatuses`，该 const 定义在 app.js 但未挂 window，ES module 作用域不可达。已按域归属将该 const 迁入 candidates.js（其唯一使用方）。这是继函数类之后的第二类断链（const 类）；一次性启发式扫描（本模块任何作用域有声明即安全 + 调用/属性形态 + 长度≥3 + 浏览器全局表）对全树复扫，6 个候选经上下文甄别全部为误报（URL 串、同行多声明符、函数参数、注释），const 类确已干净。该规则噪音水平不足以进永久检查器（函数类规则已进且零误报），const 类由 E2E + 拆分期一次性扫描覆盖，此取舍已记录。

另修复 6 个源测试：`test_convergence11.py` 的 UI 结构断言原先只读 `app.js`，已改为读取 index.html 加载的全部模块合并源码（新增 `frontend_js()` helper）——断言描述的是前端产品面而非单文件。

本地实测：跨模块函数引用检查 CLEAN；`check_frontend_contract.py` 14 模块 / 180 符号 PASS；E2E 14/14 OK；源回归 293 OK（6 skipped，零失败）；治理三查 PASS。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。
## 2026-10-23: 前端整合步骤 2c — app.js 拆分完成（本地实跑通过）

2c 抽取项目工作区外壳（projectsPage/openProject/projectTabs/projectWorkspace/openProjectStatus/archiveProject/projectOverview/cockpitTab/qualityTab/auditTab/refreshProjects/ensureProjects/projectOptions，16 行）至 `workspace.js`。**app.js 拆分完成：126KB / 280 行 → 8KB / 44 行**，仅剩 core（state、路由 renderPage、shell、go/review 快捷入口、init、核心助手及其发布）。前端最终形态：15 个 ES 模块——shared（基建）+ app（core 8KB）+ dashboard/pages/jobsetup/protocol/candidates/events/workspace（七域）+ convergence03–08（六 shim）。

过程实录：抽取脚本的头部模板遗漏 `.format()` 导致双括号语法错（node --check 即时捕获）；契约检查器同时抓到真断裂——workspace.js 裸引用 core 的 `shell` 未发布，已补 `window.shell=shell`。这正是 2a 固化的函数类规则的第二次实战命中。

本地实测：`check_frontend_contract.py` 15 模块 / 185 符号 PASS；E2E 14/14 OK；源回归 293 OK（6 skipped，零失败）；治理三查 PASS。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

**前端整合任务（药方 C）至此完成**：六代基建收敛 + app.js 按域拆分 + 三处跨 shim 缺陷 + 三处拆分期断链（renderPage 路由表/胶水层/offerNextStatuses/shell）全部修复并有静态+运行时双重守卫。
## 2026-10-23: #43 ADR-0003 相位 1 实现 — Core Supervisor 按需分离 + 附着协议（本地实跑通过）

按 ADR-0003 相位 1 实现 Supervisor 模式（特性开关默认关，开关关时行为与今天逐字一致）：

- **`backend/srw/supervisor/service.py`**：附着协议纯逻辑——附着/重附/心跳/detach 四原语、引用计数生命周期（最后一个载体 detach 进入空闲宽限，默认 300s；宽限期内新附着即取消退出）、静默载体超时自动 detach（默认 90s 无心跳）、令牌每次附着独立（`secrets.token_hex`，仅存内存）、未知附着 `UnknownAttachment`/令牌不符 `InvalidToken` 显式拒绝。时钟可注入，全单测。
- **`backend/srw/supervisor/runtime.py`**：分离进程入口（`python -m srw.supervisor.runtime`）——以 `edition="supervisor"` 持工作区租约（租约模块新增该 edition），在 loopback 服务 v1 API + 4 条附着路由，端口写入租约元数据供载体发现；宽限线程到点自退并释放租约。
- **`backend/srw/supervisor/client.py`**：载体侧——探测租约：活跃 supervisor 租约→直接附着；缺失→派生**分离进程**（Windows DETACHED_PROCESS + NEW_PROCESS_GROUP，POSIX start_new_session）后附着；非 supervisor 载体持租约→按既有单写者语义拒绝。
- **接线**：`create_v1_app(supervisor_service=...)` 条件挂载路由（`app.state.supervisor_service`，`runtime/info` 增 supervisor 块）；`scripts/start_local_web.py --supervisor` 载体路径（默认关，走原逻辑逐字不变）。
- **测试 `convergence_tests/test_supervisor.py` 14 项**：单测 7（引用计数/宽限取消/保活/静默回收/拒绝/关闭拒附/视图不泄令牌）+ HTTP 边界 4（TestClient 全roundtrip、403/404、runtime/info 块有无）+ 租约 1（supervisor 持租约时 local-web 被拒 INSTANCE_ALREADY_RUNNING）+ 真实子进程 2（**T5/T7 实证**：双载体附着同一 Supervisor→A 关闭后 Supervisor 存续、B 心跳正常→B 关闭后宽限自退、租约释放；他载体持租约时拒绝派生）。
- **契约**：路由基线 146→150（4 条 supervisor 路由进清单，漂移检测机制按设计拦截后 deliberate 重建）；`docs/contracts/API_V1.md` 增 Supervisor 域行与双载体说明；ADR-0003 记录相位 1 状态与已知缺口（旧 Portable `.srw-instance.lock` 兼容锁、pending-restore、CAS/一次性会话留相位 2/3）。
- **启动器冒烟**：`--supervisor` 实跑通过（派生→附着→租约 edition=supervisor、版本 1.0.0-alpha.11、API 正常）。沙箱在命令结束强杀进程树，跨命令存活性无法在本环境演示；T5/T7 合同由单进程内的真实子进程测试实证。

本地实测：源回归 307 OK（6 skipped，零失败，+14 新测试）；E2E 14/14 OK；治理五查 PASS（完整性 357 / release truth / G1 契约 / API 清单 150 / 前端契约）。Schema v1_0014、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。
## 2026-10-23: #43 ADR-0003 相位 2 第一部分 — 事务级 If-Match CAS + Schema v1_0015（本地实跑通过）

按 ADR-0003 相位 2 落地 S2 前半与 Schema 迁移：

**事务级 If-Match CAS（S2）**：新增 `V1RevisionConflict` → HTTP 412 `revision_conflict`（`v1_session_scope` 异常即回滚，结构上保证 412 不产假审计、不写任何状态）。覆盖 4 个重要写入口：协议草稿更新与发布（令牌 = `draft.token`，即修订标识+内容哈希，由协议工作台视图新增 `token` 字段暴露）、人工决定与核实记录（令牌 = 候选人工作台已暴露的 `decision_context_hash`，随协议/材料/策略修订移动）。语义：**发送 If-Match 即事务内强制校验，不发送则行为与今天逐字一致**（前端全量带头属相位 2 收尾，E2E 更新随后）。`convergence_tests/test_revision_cas.py` 5 项：更新生命周期（成功→令牌移动→陈旧 412→内容不变→无 If-Match 放行→垃圾令牌 412）、发布陈旧拒绝、决定的上下文追踪（新材料发布后旧令牌 412）、核实记录 412、以及**412 不产审计**专项断言。

**Schema v1_0015**：新增 `carrier_session` 表（S3 会话记录：attach_id/supervisor_instance_id/edition/carrier/created/last_seen/revoked——令牌永不落盘，只存记录使撤销可审计）；`V1_SCHEMA_REVISION` v1_0014→v1_0015，v1_0014 进入迁移集合，`create_all` 在新旧库上建表；五处权威身份（VERSION_POLICY/PORTABLE_MANIFEST/VERIFICATION_TRUTH/VERIFICATION_INVENTORY/release_state）原子同步；`launch_alpha10.py` 硬编码 `EXPECTED_SCHEMA` 同步（该处曾导致备份恢复测试拒绝新备份，已修）；三处镜像夹具与两处当前状态文档同步。`convergence_tests/test_schema_migration_0015.py` 4 项：v1_0014 旧库迁移后 revision=v1_0015 且新表存在、未知修订仍拒绝、新库直接建表。

本地实测：源回归 316 OK（6 skipped，零失败，+9 新测试）；E2E 14/14 OK；治理五查 PASS（完整性 359 / release truth / G1 / API 清单 150 / 前端契约）。Schema v1_0015、VERSION 1.0.0-alpha.11（VERSION 本身未变，仅 Schema 修订号迁移）；GitHub CI = NOT RUN（仅本地执行）。

**相位 2 剩余**：S3 一次性会话/CSRF/Origin 白名单（carrier_session 表已就位）、offer/阶段等其余写入口的 If-Match、前端 api() 带头 + E2E 更新。
## 2026-10-23: #43 ADR-0003 相位 2 第二部分 — S3 一次性会话 + CSRF/Origin 强制（本地实跑通过）

S3 落地：`SessionRegistry`（内存一会话签发/校验/CSRF 校验/撤销，`persist` 钩子只收无密投影——令牌永不落盘）；`SupervisorService` 全链路接线（attach 签发会话、detach/静默超时/`begin_shutdown` 全部撤销）；`CarrierSessionMiddleware`（纯 ASGI：仅 loopback Origin/Referer 放行；所有 `/api/v1` 变更请求须带 `X-SRW-Session`+`X-SRW-Token`+匹配的 `X-SRW-CSRF`，缺会话 401、CSRF 不符 403、非 loopback 403；attach/heartbeat/detach 与健康探针以附着令牌自主认证而豁免——该豁免名单在测试中按真实语义修正：detach 若被会话规则拦截将导致撤销链路自锁）。运行时持久化：Supervisor 进程以独立 engine 写 `carrier_session` 表（issue 建行、revoke 记 revoked_at/reason，持久化失败只记日志不中断协议）；`--enforce-sessions` 开关默认关（前端带头后随相位 2 收尾翻转）；client 句柄暴露 `session_headers()` 供载体请求使用。`convergence_tests/test_carrier_sessions.py` 13 项：注册表（签发/校验/CSRF/撤销/attach 级与全量撤销/持久化投影无密）、服务生命周期（附着签发→detach 撤销、静默撤销、退出全撤）、中间件矩阵（无会话 401、错 CSRF 403、正确放行、坏 Origin 403、读与协议端点豁免、撤销后 401）。

本地实测：源回归 329 OK（6 skipped，零失败，+13 新测试）；E2E 14/14 OK；治理五查 PASS（完整性 360 / release truth / G1 / API 清单 150 / 前端契约）。Schema v1_0015、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

**相位 2 剩余（收尾项）**：前端 `api()` 带 If-Match 与会话头 + E2E 更新；offer/阶段等其余写入口 If-Match；`--enforce-sessions` 默认翻转前的双端联验。
## 2026-10-23: #43 相位 2 收尾 — 前端 If-Match/会话头接线 + test_15（本地实跑通过）

相位 2 前端接线（ADR-0003 S2/S3 客户端侧）：`shared.js` 的 `api()` 合并载体会话头（`X-SRW-Session`/`X-SRW-Token`/`X-SRW-CSRF`，有会话才发），新增 `ensureCarrierSession()`（启动时尽力附着；非 Supervisor 的 Core 返回 404 即正常无头路径）；`app.js` init 先附着再渲染，state 增 `criteriaDraftToken`/`decisionContextHash`；`protocol.js` 的 saveCriteria/publishCriteria 带 `If-Match: <draft.token>` 并从写响应刷新令牌（连续两次保存 + 发布全程有守卫）；`candidates.js` 从候选人工作台跟踪 `decision_context_hash`，saveDecision/saveVerify 带 If-Match。后端写响应（协议更新/发布）新增 `token` 字段供前端刷新。新增 test_15（标准编辑器 If-Match 全链路：两轮保存 + 发布 + API 断言，含 confirm 对话框处理）。

本地实测：E2E 15/15 OK；源回归 329 OK（6 skipped，零失败）；治理五查 PASS（完整性 362 / release truth / G1 / API 清单 150 / 前端契约 187 符号 / 13 静态 API 路径）。Schema v1_0015、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

**相位 2 至此后端+前端+E2E 齐备**；剩余收尾项：offer/阶段等其余写入口 If-Match、`--enforce-sessions` 默认翻转前的双端联验（属相位 3 双载体验收范围）。
## 2026-10-23: #43 相位 3 本地可跑部分 — 双载体 T1–T10 验收闭环（本地实跑通过）

按 ADR-0003 S6 落地双载体并发验收的本地可跑子集，并补齐两项产品能力：

- **T6 内容级任务去重**：`_find_or_queue_task`（fullworkbench）——同 (类型, 候选人, 源) 的开放任务直接复用，双端触发同一抽取只建一个任务/job（此前键为 `task:{id}`，跨载体不去重）。
- **T8 备份互锁**：新增 `runtime/backup_guard.py`（可重入持有/释放 + 原因）；备份端点全程持锁；`LocalBoundaryMiddleware` 对变更请求检查持锁状态 → 409 `backup_in_progress`；attach 端点同样拒绝新附着。中间件经 `scope["app"]` 取 Starlette 实例（首版误用 `self.app.state` 拿到内层 ExceptionMiddleware，500——已修）。
- **loopback 禁走代理**：载体客户端与验收测试统一无代理 opener——本机代理会把已停止的 Core 变成 502 而非连接拒绝（与 #42 Windows 验收轮的代理干扰同源，产品侧一并加固）。
- **`convergence_tests/test_dual_carrier_acceptance.py` 10 项全过**：T1/T2 跨端双向读写；T3 同令牌双线程并发写 → 一 200 一 412、被拒写入内容与审计无痕；T4 协议重发布后旧决定两端均 stale；T5 关 A 后 Supervisor 存续且 B 继续读写（A 重附）；T6 双端同源抽取单任务单 job；T7 杀 Supervisor → 重派生 → 两端重附、数据保留、旧 Core 不可达；T8 端点持锁证明 + 持锁期间写入/新附着 409、释放后恢复；T9 跨站 Origin/无会话/错令牌(403)/未知附着(404) 全拒；T10 交接导出两端一致（生成时间戳除外）。
- 测试工程修复：unittest 每方法新实例——跨方法保留的载体句柄必须挂类属性（曾致 T6/T9 用已撤销会话）；Windows 存活探测复用 `workspace_lease.process_alive`（`os.kill(pid,0)` 在 Windows 不可靠）。

本地实测：双载体 10/10 OK；源回归 339 OK（6 skipped，零失败，+10 新测试）；E2E 15/15 OK；治理五查 PASS（完整性 364 / release truth / G1 / API 清单 150 / 前端契约）。Schema v1_0015、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

**相位 3 剩余**：T1/T2 的真实 WPF Host 载体对（需负责人 Windows 机器）；Owner Guide 更新；`DUAL_CARRIER_ACCEPTED` 申报条件待双端齐备后评估。
## 2026-10-23: #43 收尾 — Owner 文档更新 + capability_recovery* 正名（本地实跑通过）

- **Owner 文档**：`docs/DUAL_CARRIER_PLAN.md` 新增 M3.1「Core Supervisor 落地状态」——运行方式（`python -m srw.supervisor.runtime` / 启动器 `--supervisor`）、已闭环的 T1–T10 本地验收索引（含各测试文件与项数）、仍需负责人 Windows 机器的两项（真实 WPF Host 第二载体、GUI 点击级）、显式缺口（旧 Portable 兼容锁、pending-restore、`--enforce-sessions` 默认翻转）。
- **`capability_recovery*` 正名**（臃肿登记第 3 项，P2）：`git mv` 三文件为域准确名——`decision_operations_http.py`（运营学习/规划/决策动作/反馈，10 路由）、`intelligence_http.py`（招聘智能/渠道观测/知识包/策展，7 路由）、`sourcing_import_http.py`（渠道观测导入，2 路由）；安装函数同名变更，**内容逐字保留**（不为拆而拆）；app.py 三处导入/调用同步；BUSINESS_CODE_MAP 登记行与两处域索引刷新。

本地实测：源回归 339 OK（6 skipped，零失败）；E2E 15/15 OK；治理五查 PASS（完整性 365 / release truth / G1 / API 清单 150 / 前端契约）。Schema v1_0015、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。

**至此 ADR-0003 三相位本地可跑部分全部闭环**：相位 1（Supervisor + 附着协议）、相位 2（CAS + Schema v1_0015 + 会话/CSRF + 前端带头）、相位 3（T1–T10 本地验收 + Owner 文档）。分支领先 main 21 提交；main/origin 未动、未 push。
## 2026-10-23: #43 更正记录 — capability_recovery* 正名撤回（BLOCKED，本地实跑通过）

对上一条目（正名）的**如实更正**：`82c9cd0` 的三个文件正名当日撤回。根因：`SOURCE_RECOVERY_MANIFEST.sha256` 是 C08 不可变基线，锁定了 `capability_recovery*.py` 三个路径；`check_source_integrity.py` 要求当前清单必须是历史清单的超集——正名后要么丢失历史项（门禁失败，实测 exit=1），要么改写冻结基线（治理违规）。按宪章第 5 条（清单纪律）选择撤回：文件与安装函数名、app.py 接线全部还原（内容本就没动），BUSINESS_CODE_MAP 第 3 项登记为 **BLOCKED 并附域准确名备查**（decision-operations / intelligence / sourcing-import），供未来基线解冻或负责人裁决时使用。`82c9cd0` 中的 DUAL_CARRIER_PLAN M3.1 Owner 文档部分**保留有效**（与正名无关）。

本地实测（撤回后）：源回归 339 OK（6 skipped，零失败）；E2E 15/15 OK；治理五查 PASS（完整性 364 / release truth / G1 / API 清单 150 / 前端契约）。Schema v1_0015、VERSION 1.0.0-alpha.11 未变；GitHub CI = NOT RUN（仅本地执行）。
