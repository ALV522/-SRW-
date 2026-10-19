# SRW Agent 开发治理协议 · G1

## 1. 管理目标

停止“继续开发=自动加功能”的惯性，建立 **需求→契约→实现→回归→候选验收→事实报告→继续任务** 的可追溯闭环。治理是为了加快稳定交付，不是为每行代码增加审批。

## 2. 首次进入仓库的强制顺序

所有 Agent，包括 VS Code 插件、Copilot、第三方大模型、子代理，**开始任何代码修改之前先读根目录 AGENTS.md 中指定的全部文件**。执行一次性核查：当前 main SHA、VERSION/Schema、所选工件、最近真实 CI、未解决的关键缺陷、Windows/Web 影响范围。

不要仅凭 README 顶部的历史数字宣称最新源码已通过测试。没有权限打开相关文件、缺少测试条件或不能取得证据，则明确 UNKNOWN/BLOCKED，继续可独立验证的工作。

## 3. Issue 任务契约（必备字段）

每个非纯笔误的 Issue/开发请求应具备：
- **业务动作**：哪个操作者在什么条件下完成什么结果。
- **现状与证据**：现有症状、版本 SHA、日志/测试或可靠复现步骤。
- **目标行为**：正向场景和最少一个异常或回退场景。
- **不变量**：相关产品宪章条款；哪些旧功能不可退化。
- **影响范围**：Core / API / Windows / Web / Schema / Runtime / Knowledge / Packaging。
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

## 8. 可执行约束与局限

新增 scripts/check_governance_contract.py 与 .github/workflows/governance.yml：检查必读文档、产品/版本机器契约，并要求 PR 描述出现完整阅读与验收声明。**技术上无法证明 AI 真正阅读了文档**；可强制自我声明，并通过审查其结果发现违反条款。要让合并时真正无法绕过，仓库管理员须在 GitHub Settings → Rules → Rulesets 或 Branch protection 为 main 打开 PR 合并要求和 required status checks（至少 governance-contract、源完整性、跨平台源回归以及适用的浏览器检查）。没有仓库规则保护时，任何具有直接写入权限的人仍可能绕过 PR/CI。

## 9. 负责人每轮收到什么报告

固定格式：
- 目标和本轮实际闭环（用业务动作描述）；
- 变更 PR/commit、代码影响范围；
- Source/Browser/Windows/Provider/双端各自验收状态；
- 版本/Schema/工件身份及备份或回滚策略；
- 新增或剩余 P0/P1；
- 下轮建议最多三个有验收标准的任务；
- 需要负责人决定的事情（如果无则注明无）。

如没有真实新增进展，不得用“功能更加完善”作结论。
