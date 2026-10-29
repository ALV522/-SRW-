# SRW Agent 开发治理协议 · G1

## 1. 管理目标

停止“继续开发=自动加功能”的惯性，建立 **需求→契约→实现→回归→候选验收→事实报告→继续任务** 的可追溯闭环。治理是为了加快稳定交付，不是为每行代码增加审批。

## 2. 首次进入仓库的强制顺序

所有 Agent，包括 VS Code 插件、Copilot、第三方大模型、子代理，**开始任何代码修改之前先读根目录 AGENTS.md 中指定的全部文件**。执行一次性核查：当前 main SHA、VERSION/Schema、所选工件、最近真实 CI、未解决的关键缺陷、Windows/Web 影响范围。

不要仅凭 README 顶部的历史数字宣称最新源码已通过测试。没有权限打开相关文件、缺少测试条件或不能取得证据，则明确 UNKNOWN/BLOCKED，继续可独立验证的工作。

在每次业务开发前，先核查 [C11 能力与验收矩阵](CAPABILITY_MATRIX.md) 的相关模块；不可把旧版存在、源码存在、Chromium 测试存在和 Windows 已验收混为一谈。

从 ADR-0002 生效后，所有实现还必须核查 [API-first 模块化 Core 路线图](API_FIRST_MODULAR_CORE_ROADMAP.md)：默认开发顺序是 **operator outcome → Domain/Application → API contract → Browser/Windows client → carrier acceptance**。若工作直接扩大 `fullworkbench.py`、`frontend/dist/app.js` 或 WPF Host 中的业务规则，Issue/PR 必须解释为什么不能落在现有 Core/Application 边界。

## 3. Issue 任务契约（必备字段）

每个非纯笔误的 Issue/开发请求应具备：
- **业务动作**：哪个操作者在什么条件下完成什么结果。
- **现状与证据**：现有症状、版本 SHA、日志/测试或可靠复现步骤。
- **目标行为**：正向场景和最少一个异常或回退场景。
- **不变量**：相关产品宪章条款；哪些旧功能不可退化。
- **影响范围**：Core / Application / API contract / Windows / Web / Schema / Runtime / Knowledge / Packaging。
- **验收证据**：单元/API、真实 Chromium、真实 Windows、故障注入、Provider、工件中需要的部分；不能简单选择全部 PASS。
- **完成定义**：有代码 PR、准确测试、阻断问题关闭、文档/版本/来源与产物绑定。

## 4. 工作流 / WIP 限制

任务状态：BACKLOG → READY → IN PROGRESS → REVIEW → ACCEPTED 或 BLOCKED。建议**最多三个主要并行任务**：一个共同业务/数据能力，一个 Windows 交付，一个 Web/HTML 双载体。其他想法先入 Backlog。每个周期优先关闭已有 P0/P1 阻断项。

P0：数据、证据、人工决策错误/泄露、无法启动或丢失主线关键业务。P1：主流程阻断、备份恢复、跨载体一致性。P2：效率/易用性缺陷。P3：非关键优化。风险优先级可因安全影响上调。

## 5. PR 与合并制度

所有常规变更以分支+PR 进行；禁止 Agent force-push main。PR 描述使用 .github/pull_request_template.md，包含阅读确认、目标 SHA、业务前后行为、修改范围、两载体影响、具体测试/证据、版本/Schema/数据风险、回滚方案、剩余 BLOCKED。

- PR 更新 SOURCE_MANIFEST.sha256，先核查未解释的哈希/文件删减，禁止通过重算清单掩盖篡改；SOURCE_RECOVERY_MANIFEST.sha256 不可修改。
- CI 的 Source Integrity / Release Truth / 跨平台源回归 / Chromium / Windows Host / Governance 分别报告，不用一项代替另一项。
- 中大型变更要求关联 Issue，业务规则/接口或权威数据变化同时更新契约与测试。
- API-first 重构 PR 必须说明 operator use case、route/contract before→after、并发/审计/人工边界以及回滚；文件拆分本身不是完成标准。URL/Schema 默认保持，除非另有批准的迁移。
- 模块拆分采用 Strangler Refactoring：一次一个业务域，先建立 contract/regression safety net，再迁 route/application/frontend；禁止并行建设第二套 Core 或双写数据库。
- 合并后复验准确 main SHA，不沿用 PR 分支或其他来源的旧工件证据。
- 正式发布遵守 docs/RELEASE_PROCESS.md；需要产品负责人最终确认。

## 6. 决策授权

**Agent 自主**：具备回归覆盖的普通缺陷、局部重构、文档勘误、性能优化、低风险实现选择。
**Agent 提出方案并跨端评审**：Schema 增量、跨端 API、生命周期、权限/身份、任务调度、文件布局、兼容性破坏。
**负责人决定**：产品宪章 A 类变更、整体内核/UI 重写、取消历史关键能力、引入 SaaS/企业路线、发布 RC/GA。

需要重大裁决时生成 ADR，列出现状、3个以内的可行选项、证据、破坏范围、推荐方案及回退。非必要不打断负责人。

## 7. 验收真实性

每个声明必须带：Git SHA、工件 SHA（如适用）、测试环境、样本性质、运行日期、动作、预期/实际、日志或 CI 链接、结果 PASS/FAIL/BLOCKED/NOT RUN。

- Source tests ≠ Browser E2E ≠ WPF GUI ≠ 正式 Portable/RC/GA。
- 探索分支 E1–E5/Native SOURCE Lab 的合成 PASS 不会自动转为主线双载体 PASS。
- “有按钮”“有 API”“写了测试”都不是业务流程完成。
- 软件版号、Schema 和发行状态由 VERSION_POLICY.json 与已有多处 release truth 共同核对。
- 真正发生问题而无法复现，应标记 UNKNOWN 并保存无隐私泄露的最小证据。

## 8. 暂无分支保护的 G1 强化纪律（当前生效）

产品负责人决定暂不启用 GitHub main 保护，因此全体 Agent 必须先阅读 [临时无保护协议](NO_BRANCH_PROTECTION_PROTOCOL.md)，在新建的干净任务分支执行 `python scripts/agent_preflight.py --issue <对应Issue> --acknowledge-reading`，只能经 PR 合并，须先读取同 PR Head SHA 的治理/源码/浏览器及受影响构建检查结果，**全绿才合并**。合并前二次比较 Head/Main SHA，合并后再次查 main 的 CI 与产物。禁止任何 Agent 直接修改或 push main。不能把这称为平台级强制保护：当前无权限屏障，违规直接 push 只能事后发现与调查。

## 9. 可执行约束与局限

新增 scripts/check_governance_contract.py 与 .github/workflows/governance.yml：检查必读文档、产品/版本机器契约，并要求 PR 描述出现完整阅读与验收声明。**技术上无法证明 AI 真正阅读了文档**；可强制自我声明，并通过审查其结果发现违反条款。要让合并时真正无法绕过，仓库管理员须在 GitHub Settings → Rules → Rulesets 或 Branch protection 为 main 打开 PR 合并要求和 required status checks（至少 governance-contract、源完整性、跨平台源回归以及适用的浏览器检查）。没有仓库规则保护时，任何具有直接写入权限的人仍可能绕过 PR/CI。

## 10. 负责人每轮收到什么报告

固定格式：
- 目标和本轮实际闭环（用业务动作描述）；
- 变更 PR/commit、代码影响范围；
- Source/Browser/Windows/Provider/双端各自验收状态；
- 版本/Schema/工件身份及备份或回滚策略；
- 新增或剩余 P0/P1；
- 下轮建议最多三个有验收标准的任务；
- 需要负责人决定的事情（如果无则注明无）。

如没有真实新增进展，不得用“功能更加完善”作结论。

## 11. G1.1 独立审查、冲突域与复核（#132）

- Core/API、备份恢复、数据模型、会话安全、Native 发布类 PR 必须由**非作者轨道**对准确 HEAD 做正式 Review，写明代码边界、至少一条负例、跨端差异与 `SOURCE_MANIFEST` 变化，并给出 `ACCEPT/NEEDS_CHANGES/BLOCK`。HEAD 一变，旧 Review 过期；缺 Review 就是 `REVIEW BLOCKED`，CI 全绿也不能替代。
- A/B/C 共用一个 GitHub 账号时，`COMMENTED` review 只是**过程层分工**，平台无法证明是另一个人审的；不得声称 Ruleset 或 Branch Protection 已强制审查。
- P0/P1 修复的顺序固定为：合成且确定的 **RED** → 修复 → **RED 变 GREEN** → 正反例回归 → 双平台 Source 与 Chromium（必要时 Native）→ 独立 Review。无法自动复现的故障必须写清人工/杀进程 oracle。
- `os.fsync`、`os.link`、`os.replace`、Windows 文件共享、SQLite WAL、路径大小写与权限、崩溃窗口属于系统级风险，**设计前**写双 OS 兼容表，不等 Windows 红灯再分析。
- 合并遵循[事件驱动、风险优先的队列](INTEGRATION_QUEUE.md)：同一冲突域一次只有一名集成人，main/PR HEAD 实时复核；巡检不是强制等待窗口，紧急 P0 不得延迟。
- 清单继续执行"**提交的字节与提交的 SHA 清单一致**"，CI 不得自动写回清单并盖章；评审可用只读 `scripts/report_source_manifest_delta.py`，分域清单仍属[未生效的迁移研究](SOURCE_MANIFEST_MIGRATION.md)。
- 交接六字段（main/head｜变更｜实证｜下一件｜决策｜阻断）尽量少于 300 字，细节留在 PR/Issue；使用系统真实 ISO-8601 时间，不手填占位。
- 任何一轨缺席都不授权另一轨代签自己的高风险 Review；可做非重叠的治理、只读工具与确定性测试合同。

权威风险条目见[风险地图](ENGINEERING_RISK_REGISTER.md)。新版本仍须独立原子迁移 PR，本文不改变产品 A1–A8。

## 12. 证据与冲突成本优化（#132，兼容性先行）

这一节不是新增审批层：减少重复状态转述和全局清单冲突，保留 G1 原有合并门禁。

- **#150 审查修正：** 机器人只展示三项 reporting workflows，不代表六项主线门禁全部通过；按 PR 号串行、在写入前核验 HEAD，幂等更新并清除重复的旧 bot 评论。GitHub `workflow_run` 必须在默认分支真正部署后另行实测；仅有 PR 的 Source CI 全绿不证明评论机器人已经部署。
- **CI 链接自动化：** 可信默认分支的 `SRW CI Evidence Link Reporter` 通过 `workflow_run` 读取 GitHub API，按准确 PR HEAD 更新一条 bot 评论，附 Source/Chromium/Governance 的 run URL 和完成状态；无对应 run 一律显示 PENDING，任意失败不得显示全绿。它不运行 PR 代码、不写 Source Manifest、不合并 PR，也不自动补签 Review。main push 的工件/CI 仍需分别查 SHA。手工转述不必在 #103 复制长篇 CI 数字，给 PR 证据链接即可。
- **真实审批身份：** A/B/C 即使有分轨实证，只要使用同一 GitHub 登录就不是第二个 GitHub 审批身份。此时如实写“不同工作轨道审查，平台审批者未独立”；不把 `COMMENTED` 算作第二账号 `APPROVED`。若产品负责人决定亲自审阅，可用独立身份在可用权限范围内提交 GitHub Review；未获正式审查不代签。每周 10 分钟是可选的审查节奏，不替代风险优先队列。
- **Manifest 分域试运行：** `python scripts/report_source_manifest_domains.py --markdown` 仅从权威根清单导出互斥且全覆盖的 7 个领域摘要，逐字节校验合并后仍等于根清单，检查真实文件哈希。它不保存第二份权威清单，也**不减少当前 PR 对根文件的编辑冲突**。正式切换须另立迁移 PR，证明 Source ZIP、旧历史清单、Native Host、Windows 路径与复原流程的兼容性；禁止 CI 自动重算后自我批准。

**度量分母必须明确。** “作废的 PR / 已结束 PR”、“因 Manifest 冲突而作废 / 所有合并候选”、“单个 PR 多个 HEAD”不是同一指标；历史 11/34 是指定样本的估算，不代表全库因果归因。记录真实的 rebase 次数和冲突工时之后再裁决分片升权。

## 12. P4 处置、重跑语义、交接字段与 REST 提交兜底（#103 裁决，2026-10-29）

**P4 必须三选一。** 每条在 Review 中提出的 P4，合并前必须在 PR 正文写明且仅写明一种处置：
`已修（PR/提交）`、`已登记（#155 或具体 Issue）`、`明确接受风险（理由）`。
`check_governance_contract.py --check-pr-body` 校验该行的**结构**（恰一条、恰一个标记、标记后有具体指向或理由）；
它不证明修复真实、也不证明风险已被他人接受，语义仍由人工审查。留空模板、只写标记、或把三个选项都留着，均判红。

**重跑不消除红灯。** 任何 UI/时序类首次失败必须保留原始 run/attempt 记录，并开一个诊断 Issue，写清：根因未知、
下一次出现时要采集的字段、以及关闭条件。再跑通过**不是** incident closure；把工作台"变绿"不算修复。
诊断交付（例如 #154 的结构化超时字段）只提升可判读性，不等于原故障已定位。

**交接必须带机读阻塞方。** 每份交接的最后一行固定为 `BLOCKED_BY: A|B|C|none`，表示**当前下一动作的责任轨**，
不是 CI 通过声明。字段单值；多个前置条件同时存在时写最先必须行动的一轨。只有所有门禁已满足且没有待执行动作时
才可写 `none`；CI/外部保管/发布状态仍须在前文如实写出。

**Git 传输不可用时的 REST 兜底。** 仅在新建任务分支上使用：先跑真实 pre-edit `agent_preflight`；每个新增 blob 与
本地 `git hash-object` 逐字一致；整棵 tree 与本地 `git write-tree` 一致；父提交与 `refs/heads/*` 的 lease 严格核对；
**不得创建或强推 main**；commit message 末尾加 `Transport: REST (git push 502)`；PR 正文注明本地与远端 SHA 的元数据
不同、同一 tree 及核对方法。已合并的历史（如 #156）不因补 trailer 而改写。
