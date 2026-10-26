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

- 对所有 Core/API、备份恢复、数据模型、会话安全、Native 发布类 PR，必须由**非作者轨道**作准确 HEAD 的正式 Review，指出代码边界、至少一条负例、跨端差异和 SOURCE_MANIFEST 变化，并标明 `ACCEPT/NEEDS_CHANGES/BLOCK`。新 HEAD 使旧审查过期；缺审查则 `REVIEW BLOCKED`，哪怕 CI 全绿。
- 当前 A/B/C 使用同一 GitHub 账号时，COMMENTED review 是**过程层**分工，不是平台能证明的另一个人审核；不得伪称 Ruleset/Branch protection 已经强制审查。
- P0/P1 修复优先“合成确定性 RED → Core 修复 → RED 变 GREEN → 正反例回归 → Ubuntu/Windows Source 与 Chromium、必要 Native → 独立 Review”；无法自动复现的故障必须说明人工/进程杀死 oracle。
- `os.fsync`、`os.link`、`os.replace`、Windows 文件共享、SQLite WAL、路径/权限/大小写和崩溃窗口都属于系统级风险，**设计前**写双 OS 兼容表，不能等 Windows 绿灯失败才分析。
- 使用[事件驱动、风险优先的合并队列](INTEGRATION_QUEUE.md)：重叠文件一次只允许一名集成人，main/PR HEAD 实时复核；午晚可作巡检但不是强制等待窗口，紧急 P0 不得延迟。
- 源码清单继续执行“**提交的字节与提交的 SHA 清单一致**”，CI 禁止自动写回清单并盖章。分域清单属于[独立迁移研究](SOURCE_MANIFEST_MIGRATION.md)，未生效。
- 六字段交接优先少于 300 字：`main/head | 变更 | 实证 | 下一件 | 决策 | 阻断`，细节归 PR/Issue；先读最新评论，系统真实 ISO-8601 带时区时间，不手填 `xx`。
- B/C 暂时无法回应不授权 A 自审合并其所需签字的高风险 PR；A 可继续非重叠治理、风险回归和 README 文档工作。PR pre-edit preflight 未真实运行时仍 BLOCKED，不能事后倒填。

权威风险条目见 [风险地图](ENGINEERING_RISK_REGISTER.md)，四道 alpha.11 准备度见 #132。新版本必须独立原子迁移 PR，本文不变更产品 A1–A8。
