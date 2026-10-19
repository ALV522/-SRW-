# C11 证据决策链：Source → Claim → Judgment → HumanDecision → 失效/重申

## 新增真实浏览器验收 E2E-06

该场景使用 Chromium 的实际界面操作、真实 C11 HTTP API 和临时 SQLite 数据库。无需配置远程 AI，不读取任何生产候选人记录或 API 密钥。Claim 由**人工核实记录**产生，不假装是 AI 自动抽取结果。

1. UI 创建招聘项目，在“建岗与标准”添加具有 `decision_critical=true`、`verification_required=true` 的评价标准；保存草案并由人显式发布。
2. UI 新增候选人，粘贴并发布第一版虚构文本材料。核对 `decision_context_hash` 已形成，但标准缺少核实，`decision_ready=false`。尝试绕开 UI 直接 `advance` 必须由服务器拒绝。
3. UI 执行“人工核实”。后端添加 `verification_note` Source、人工作为权威的 Claim、发布新的 MaterialRevision、记录具有强证据的 Criterion Judgment。核对来源、Claim 和 Judgment 与同一当前上下文绑定。
4. UI 记录 `advance` HumanDecision。真实决策历史须存在一条对应当前上下文的人工决定。
5. UI 追加第二份虚构文本材料。由于材料版本与 Decision Context 已变化，旧决定必须标记 `stale=true`；不能继续作为当前决定。
6. 未对新增证据重新核实的状态下，直接请求 `decisions/reaffirm` 必须被服务器拒绝，且不会产生额外决定行。
7. UI 再次执行人工核实，然后显式输入新的“重申理由”。核对新 Decision 属于当前上下文、`reaffirmed_from_decision_id` 指向此前的人工决定，原始决定保留但处于历史状态。

这个流程同时检验：`Source/Claim` 有明确人工来源、`Judgment` 按上下文有效、`HumanDecision` 不由 AI 或材料更新自动生成、证据变化不隐式继承旧决定，以及重申必须重新通过当前证据门槛。

### 状态语义

- **经过人工核实的 Claim** 不等于没有人参与的 AI Claim 生成。当前 CI 不模拟 Provider 返回，避免对 AI 能力作虚假验收。
- **历史决定 stale** 不等于被删除。历史记录应该可查，并指出旧版本与新版本的差异。
- **重申** 不是给过期决定改状态，而是由人再次确认新 Decision Context，产生新的、可追溯的决定，并要求通过最新验证标准。
- 本次 Chromium 验收不等于已经在实际 WPF/WebView2 Windows Host 中逐项点击验收。Windows 原生版基础 GUI 已实机通过，完整业务必须在下一轮候选 Native 装配后单独验收。

测试入口：`browser_acceptance/test_flows.py::RecruitmentBrowserAcceptance.test_06_human_verification_decision_stale_and_explicit_reaffirmation`，使用 `python -m unittest discover -s browser_acceptance -p 'test_*.py' -v`。验收工件见 GitHub workflow `SRW Chromium Business Acceptance`。
