# SRW 项目负责人操作手册：以后怎样与 AI Agent 一起开发

> 本文写给 SRW 项目负责人。目标是让你不需要亲自逐行编码，也能够稳定推进开发、看懂进展、发现伪验收，并在必须做决定时给出明确答复。它不是给 Agent 绕过验收的授权。

## 当前特别规定：不启用 GitHub 主线保护

请先读 [暂时不启用主线保护时的开发制度](NO_BRANCH_PROTECTION_PROTOCOL.md)。新 Agent 必须在**非 main 的干净任务分支**运行 `python scripts/agent_preflight.py --issue 41 --acknowledge-reading`（41 改成真实 Issue 号）。必须走 PR，等所有相关检查完成且成功后才能合并；合并后确认 main SHA 和 CI。没有主线保护时，Github UI 仍可能允许不安全操作，本制度降低风险但不能彻底防止绕过。

以后发给 Agent 的开头可以是：“主线暂不设置保护。严格执行 AGENTS.md 与无保护协议：绝不直接 push main，先读文件和运行预编辑检查，按 Issue 做 PR，核实相同 SHA 的所有 CI 才合并，合并后核对 main 和测试状态。”

### 协作证据与负责人抽查（#132）

机器人只覆盖 Source、Chromium、Governance 三项报告；Repository Integrity、Windows Host、Wheelhouse 不在评论范围内，必须分别检查。合并后先验证首次真实 `workflow_run`，而不是默认认为机器人已在运行。

每个新 PR 的 CI 会由 GitHub Actions 的可信主线 Reporter 尝试写入同一条 **exact-HEAD 证据评论**，点击各 workflow 的 run 链接核对，不必从 #103 的长篇自报中寻找。机器人仅汇总 Source/Chromium/Governance，不等于 Native GUI/正式发布，也**不会替你批准或合并 PR**。如果没有 bot 评论，则按 NOT AVAILABLE 处理并人工查 Actions，不声称已部署或已有结果。

当前 A/B/C 工作可能使用同一个 GitHub 账号：独立工作轨复核是真实的流程控制，但不是另一个 GitHub 账户的 APPROVED。若你希望增强独立性，可以用**真正不同的授权账号**每周集中审核风险最高的 1–2 个 PR；平台批准门禁只有在账号与分支权限实际区分后才成立。无需因此将所有普通修复变成逐单请示。

## 一、每次启动一个新 Agent

先告诉它仓库和默认开发方式，不要第一句话只写“继续开发”。推荐直接发送：

> 请先打开 SRW GitHub 仓库根目录 AGENTS.md，并按其中给定顺序阅读所有必读文件，尤其是产品宪章、ADR-0001/ADR-0002、API-first 模块化 Core 路线图、版本政策、开发治理、双载体计划和验收计划。在任何代码修改前，报告当前 main SHA、VERSION、Schema、最近可验证的 CI 与 Windows/Browser 分别达到的状态，以及你准备推进的最多三个任务。此后以真实业务闭环、API-first 模块化 Core、Windows+本地 HTML/Web 并行产品化为目标，通过分支/PR/测试推进；新增业务能力优先进入 Core/Application/API contract，而不是继续把规则堆进大前端或 Host；不得未经证明声称 PASS，不得静默修改产品不变量。

若它直接给出新功能方案，却不愿阅读仓库文件或拿不出提交和验收证据，就要求先完成阅读与事实核查。

## 二、一次正常开发迭代应该发生什么

1. Agent 阅读契约、检查仓库 main、当前 Issue、CI 和未完成任务。
2. Agent 提出有限的本轮目标：共同 Core/业务1项、Windows 1项、Web 1项（可按阻断风险调整）。
3. Agent 在分支上实现并增加必要回归，建立 PR，运行真实检查。
4. Agent 提交结果：**实际改变的业务行为、文件/PR、精确 SHA、环境、PASS/FAIL/BLOCKED、未决风险、下轮建议**。
5. 你只对重大 A 级取舍、发布确认和真实 Windows/人工动作进行干预。
6. 当当前工作不能继续，比如缺少用户本地 Runtime 输入，Agent 应转入其他不受阻断的任务，同时保留明确的 BLOCKED，不要编造成功。

## 三、今后会遇到的常见情况，以及怎样回复

### 1. Agent 说“已经完成了”
回复：
> 请给出对应 PR/commit SHA、改动前后真实业务动作、在哪些环境运行了什么测试、哪项功能在 Windows 和 Browser 分别 PASS，以及哪些仍是 NOT RUN。没有对应验收的功能按待验收记录。

### 2. Agent 建议“全面重构 UI 或业务内核”
回复：
> 当前产品宪章和 ADR-0002 排除全面重写。请先按 API-first 模块化单体路线判断：能否在现有 C11 Core 中通过 Domain/Application/API contract 的小步拆分解决，并给出具体阻断、影响能力、现有回归覆盖、route/contract 兼容和回滚方案。没有证据证明渐进方案不可行，不得建立 new-core、微服务、第二套数据库或同时迁移前端框架。

### 3. Agent 想新增大量功能
回复：
> 先在 Capability Matrix 和任务队列中标明它解决哪个具体招聘动作、与当前 P0/P1 的优先级关系，以及验收脚本。优先关闭现有主流程阻断，不为扩大功能数量新增独立系统。

### 4. Agent 说“Windows 包已经好了”
回复：
> 请区分 SOURCE ZIP、Host-only、Prepared Native、UNVERIFIED GUI Candidate、Windows GUI ACCEPTED、RC 和正式版。给出本次 ZIP 哈希、源码 SHA、运行库/Knowledge/Host 身份、真实 Windows GUI 日志及完整业务验收结果。旧 d8d032d 的 PASS 不可替代新工件。

### 5. Agent 说“HTML 版本完成了”
回复：
> 这是不是静态 UI Demo？是否经真实 C11 API 使用同一个 Core 与 SQLite？是否可以从本地包启动并执行招聘流程？哪些动作经真实 Chromium E2E？是否验证了与 EXE 的同时读写、冲突拒绝和任务唯一所有权？未验证的保留探索状态。

### 6. 出现构建失败、异常日志或文件缺失
回复：
> 请首先定位准确失败环节、受影响工件、最小复现步骤和预期/实际。不要关闭完整性校验、临时替换 SHA 或改变生产工作区来绕过阻断。优先修复构建或测试本身，保留旧工作区/旧 ZIP。

### 7. Agent 要你执行 PowerShell 或本地测试
你需要确认：运行命令是否只访问指定合成 data-root、会否覆盖原始 ZIP、会否访问 Provider Key/真实简历、预计生成什么本地证据、是否要求管理员权限。建议它先提供安全前置校验和明确的日志路径。
执行以后回传命令输出（删除个人路径、密钥和私有候选人数据），必要时提供脱敏截屏和日志。切勿将完整工作区发往 GitHub。

### 8. Agent 提议更换版本号
回复：
> 先读取 docs/VERSION_POLICY.md。说明产品 SemVer、Schema、Git SHA、carrier、channel 五者的不同；若确需改 VERSION，列出八处现有 release truth 需要同步更新的文件、测试和回滚方案。不要为文档治理或单次修复就宣称升级到正式 1.0。

### 9. 某个 Agent 的工作和先前方向冲突
回复：
> 请先引用现有 PRODUCT_CHARTER 条款和相关 ADR。若确有新增事实，请以 ADR 列出旧决定、反证、新选项、风险与回退；我只审批产品/架构级变更，普通实现继续按已有契约执行。

### 10. 项目进入正式发布讨论
回复：
> 请提交一个冻结的 Release Candidate：源 SHA、完整工件哈希、Windows 与 Local Web 分别的验收、业务 E2E、Schema 升级与回滚、P0/P1、已知限制和用户启动说明。任何一项 BLOCKED 不要记为通过；满足发布准则后再征求我批准。

## 四、不要怎么管理 Agent

不要仅用“继续推进”“尽可能完善”“思考更久”作为唯一工作定义；这会让不同 Agent 随意选择局部目标。
不要用代码行数、新按钮数量或生成了多少 ZIP 评价进度。
不要看到测试总量增长就认为产品完整；问清楚覆盖了什么用户动作。
不要为了追求“漂亮的全新版本”容忍功能缩水。
不要允许 Agent 接触真实数据后，把原始日志、密钥或数据库上传到仓库。
不要对无法实机验证的事项给予口头 PASS。

## 五、正常你应该看的三个地方

1. 根目录 AGENTS.md 和 docs/PRODUCT_CHARTER.md：产品边界是否仍被遵守。
2. 目标 PR 的改动、测试与 GitHub Actions：是否真实关闭问题。
3. 当前工件的 Windows/Browser/双端验收与未关闭 P0/P1：距离交付有多远。

暂时不要把真实招聘人员的外部试用设为内部发布候选的前置条件；产品自检通过之后再安排用户研究。但合成数据端到端业务测试从第一天就不能少。

## 六、最重要的固定回复模板

**普通推进**
> 按 AGENTS.md 的制度推进当前优先级最高的业务闭环、Windows 与 Web 产品化任务。请自主完成无需我决策的低风险工程工作。交付具体 PR、测试与事实报告；有阻断则明确原因并推进其他无依赖任务。

**验收质疑**
> 这项能力请不要只说“已实现”。给出操作场景、准确 SHA/工件、Windows/Browser 各自可复现的测试，未通过请直接记 FAIL/BLOCKED，不得复用别的版本证据。

**架构争议**
> 按 ADR-0002 使用现有 C11 Core 做 API-first 模块化单体的渐进改造：业务真相留在 Domain/Application，API 是稳定 contract，Windows/Browser 是客户端。不得为了目录或框架美观丢失成熟功能，也不得默认继续膨胀 fullworkbench.py/app.js。涉及 A 类产品不变量时提交 ADR 和替代方案让我决定。

**产品范围变更**
> 当前非目标：新 UI/全面内核重写/SaaS/云端登录/企业平台。请按产品宪章调整计划，不要扩大范围。

**Windows 本地验收**
> 给我安全、不可破坏旧数据的精确 PowerShell 操作，注明候选 ZIP SHA、data-root、预期输出与失败处理。我执行并回传脱敏证据后再判定是否通过。

**发布决策**
> 先提交正式发行判定单，分别列出 Windows 与 Local Web 的工件、覆盖、通过/阻断、恢复与已知缺陷。在证据齐备前保持候选状态。

## 七、何时你应该说“可以继续”？

当 Agent 已说明准确版本状态、当前目标和验收标准；未提出违反产品宪章的变化；并且不要求你批准每个技术细节时，你可以直接回复“按已批准契约继续自主推进，完成后用事实报告交付”。

当需要实际 Windows 环境、重大路线选择、数据操作或发布授权时，你才介入。

最终目标是 **你规定产品边界，Agent 负责高频工程执行，测试和真实环境负责纠偏**。
