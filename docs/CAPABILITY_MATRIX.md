# SRW C11 能力与验收对照矩阵 · P0 (#41)

> 2026-10-20 静态能力地图，不是最新 SHA 的动态 PASS 报告。本表以 main 中可见的源码、业务测试、README、DEVELOPMENT_STATE.md 和 docs/ACCEPTANCE_PLAN.md 为初步依据；未逐字对比历史 v0.8.12-R2 的全部源码，不能声称完整 parity。所有 PASS 必须依附某个**准确 SHA + 环境 + 工件**。Agent 每轮先核查真实 CI，再更新证据，不能手填 PASS 代替测试。

## 状态词典

- **IMPLEMENTED**：仓库有操作/测试入口，但未声称在当前准确目标工件通过。
- **TEST_CASE_EXISTS**：已找到真实 UI 或源测试用例；CI 是否通过另看精确 SHA。
- **HISTORICAL_WPF_SMOKE**：仅 d8d032d 用户 Windows 的两次业务写入和启动/退出，无其他业务授权。
- **NOT VERIFIED**：本表没有对应环境的真实操作证据；不等于没有实现。
- **BLOCKED**：存在明确先决条件，当前不适合宣称完成。
- **PASS@SHA**：只应在行内附具体 CI run 或人工工件 SHA/测试报告时使用。不可用“测试数量”替代。

## 核心业务能力对照（静态事实和验收需求）

| 域 | C11 目前可定位的实现/测试 | 真实 Chromium 业务验证 | Windows WPF/GUI | 主要未闭环点 |
|---|---|---|---|---|
| 岗位、项目、标准草案 | `create_project_with_draft`、四步 Job Setup、Protocol/Criteria、标准发布 | `test_01` Draft 不自动发布；`test_06/07` 明确发布及重发布 | **HISTORICAL_WPF_SMOKE**：旧 d8d032d 的项目创建、标准草案修改 | 真实 Native 的完整 Criteria/重复发布/上下文保真 |
| 候选人身份/导入 | Candidate Intake、项目收件、Source/MaterialRevision、历史记录 | `test_02/06/07` 文本材料入库 | **NOT VERIFIED** | PDF/扫描件、批量导入、重复身份、材料异常恢复 |
| Evidence/Claim/Judgment | Source、Claim、人工核实、criterion 判断、上下文哈希和历史 | `test_06` 完整人工核实、证据增补、旧决定失效/重申；`test_07` 标准更新时旧决定失效 | **NOT VERIFIED** | 真实 PDF OCR/页面来源定位、跨版本冲突/人工回退 |
| 电话筛选、面试、Scorecard | Interview/Event 与独立评分、人工分歧保留 | `test_03` 预约；`test_04` 两位面试官独立 Scorecard | **NOT VERIFIED** | 完整面试状态、异常取消/改期、Native 点击流 |
| 人工 Decision / 评价 | HumanDecision、Decision Context、stale、reaffirm gate | `test_06/07` 人工决定与两类变更失效路径 | **NOT VERIFIED** | 人工决策流程在真实 Native、失败重试和历史审计 |
| Offer 状态 | Draft/Approved/Sent/Accepted、人工状态转移 | `test_02/05` Offer Draft 和合法状态链；Accepted 不自动 Hired | **NOT VERIFIED** | 完整跨阶段、拒绝/撤回/取消异常状态，Native |
| 联系、行动、交接 | Action Plan、看板、联系队列、Handoff/Brief | `test_02` 跟进计划持久化 | **NOT VERIFIED** | 跨场景端到端操作与交接可恢复验证 |
| Knowledge 治理 | 五库加载、受控 apply/rollback、语义检索 | 合成 Knowledge 的运行作为集成测试条件，**不是**生产库质量 PASS | **NOT VERIFIED** | 生产库来源、质量、合并、回滚实际测试 |
| AI Provider | 本地 Provider/隐私投影/任务与降级代码 | CI 无真实密钥/真实 Provider 调用 | **NOT VERIFIED** | 接口异常、超时、限流、实际质量/费用 |
| OCR/ASR | 文档处理/音频转写保留目标 | 现有 7 条 Chromium 不是 OCR/ASR 实测 | **NOT VERIFIED** | 有授权真实样本的接口、正确率、失败降级 |
| 备份/恢复/迁移 | backup_truth、恢复完整性/验证、project package | 现有 Chromium 业务测试不是升级/崩溃恢复验收 | **NOT VERIFIED** | Windows 当前准确工件的跨根恢复、故障注入 |
| Windows Native/Portable | WPF/WebView2、Native 源码+Host 升级工具链 | Browser E2E 与 Native 验收不能互推 | **HISTORICAL_WPF_SMOKE** 仅旧工件基础生命周期 | 当前 C11 ZIP 的 Runtime/Knowledge/Host/业务/恢复验收 |
| Local HTML/Web | C11 Core HTTP/API 与现有 HTML 前端；探索分支 E1–E5 | 受控 Chromium + 临时 SQLite 业务 E2E；正式 Local Web 入口见 #43 | 非 Windows WPF | 独立本地启动包、正式会话安全和生命周期 |
| EXE/Browser 同源同时运行 | 探索 E3/E4/E5 CAS、Core owner、attach 协议及 Native SOURCE Lab | **NOT VERIFIED** 为正式并发写入产品 | **NOT VERIFIED** | 一个权威 Core/Job Engine、事务写入、会话撤销、跨端冲突 |

## 已知的真实测试入口（代码中存在 ≠ 当前 HEAD 已 PASS）

- `browser_acceptance/test_flows.py::test_01_job_setup_draft_requires_explicit_human_publish`
- `...::test_02_candidate_material_contact_and_offer_persist`
- `...::test_03_interview_is_a_real_persisted_workflow`
- `...::test_04_independent_interview_scorecards_cannot_be_overwritten`
- `...::test_05_offer_lifecycle_requires_human_transitions_and_never_auto_hires`
- `...::test_06_human_verification_decision_stale_and_explicit_reaffirmation`
- `...::test_07_published_protocol_change_invalidates_previous_human_decision`

精确成功记录以 `.github/workflows/browser-e2e.yml` 对应当前 SHA 为准。Windows 旧验收见 `docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md`（d8d032d）；当前 Native 升级资料见 `docs/C11_NATIVE_CANDIDATE_UPGRADE.md`。没有真实用户/Provider 数据时保持 NOT VERIFIED，而不是填 PASS。

## 三个与交付直接相关的纵向验收契约

**V1 人工可控主线**：创建项目→设置/发布 criteria→收件→Source→Claim 人工核实→Interview/Scorecard→HumanDecision→Offer→联系跟进。要求全流程不仅 API 返回成功，也能通过 GUI 操作和 SQLite 历史复核；文档中任意模块存在都不代表 V1 整链通过。

**V2 决策失效与恢复**：新 MaterialRevision 和新 ProtocolRevision 两类改变各自使旧 Decision stale；未经复核的 reaffirm 一律服务器拒绝、无假审计；历史决定不被覆盖。重申必须再次经过人工核实。

**V3 双端同权威状态**：Windows WPF 和本地 Browser 对同一 Core 交叉读写、冲突拒绝、Core 生命周期、单一任务队列、退出/备份互锁、Origin/会话保护。E1–E5 的实验不构成 V3 PASS。

## 优先级与完成规则

P0：V1/V2 的完整业务和异常路径；精确当前 Windows Native 候选完整 GUI 和数据恢复（#41/#42）。
P1：Local Web/EXE 共同核心与 V3（#43），不为并行开发引入第二套业务状态。
P1：历史版本/正式 SemVer 迁移（#44），不能让 VERSION 与各元数据不一致。
P2：真实招聘人员使用反馈，待第一个独立可用产品完成内部验收后开展。

能力对照中任何一项要从 IMPLEMENTED 变为 PASS，必须记录对应源 SHA、测试名称、环境、输入数据性质、工件 SHA（若适用）、实际运行结果及不可覆盖的证据链接。历史 v0.8.12-R2 是否具备细分能力必须由源文件/档案核查，不能靠推测填写“已保留”。

## P0 进行中招聘指标与历史记录隔离（Issue #41 增量）

浏览器验收入口 `browser_acceptance/test_flows.py::test_08_archive_restore_preserves_material_and_live_funnel` 通过现有 UI 新建项目、候选人、发布合成文本材料，执行候选人归档、筛选和恢复，再分别取消/确认项目归档。验收检查在库人数和新候选人漏斗、恢复后材料可见且 Source 记录不变，以及项目归档后实际首页漏斗减少。所有业务写入均由 Chromium 点击触发；API 只用于结果复核。它不覆盖 Offer/面试归档、项目恢复、备份恢复、WPF GUI 或正式双端并发。是否 PASS 以该测试所在精确提交的 Chromium CI 为准；不能将本条视为 #41 整体完成。

运营工作台 `GET /api/v1/dashboard` 中的在招候选人数、招聘漏斗各阶段、Offer 状态、近期面试及过期复评待办应当只统计**未归档项目中未归档候选人**。归档项目及单独归档候选人的历史 Offer、面试、复评数据仍保留在 SQLite 与历史业务页面中，不得通过删除记录达到指标一致性。`convergence_tests/test_convergence11.py::test_dashboard_active_funnel_offer_and_upcoming_exclude_archived_work` 使用合成活动/归档项目及候选人，验证这五类聚合与真实 API 返回一致。它属于 API/源回归证据，不代替浏览器交互或当前 Native 工件验收；PASS 状态以相同提交 SHA 的 Source Gate 为准。

## P0 #41 增量：无有效当前上下文时的历史人工决定（2026-10-20）

原先 `get_decision_history` 仅在成功计算当前 `decision_context_hash` 时才把不一致的旧决定标记为 `stale`。当当前发布 Protocol 或当前 MaterialRevision 暂时缺失，旧决定返回 `is_current_context=false, stale=false`，产生具有权威含义的含糊状态。本次在既有 A2 产品不变量下修复为“没有当前有效上下文的历史决定显式 `stale=true`”，不删除决定、不生成新的决定、不修改重申门槛。

`convergence_tests/test_decision_history_context.py` 使用临时 SQLite 与真实 API 验证：正常上下文仍有效、当前 Protocol 缺失时失效、当前 Material 缺失时失效、实际决策历史 HTTP 响应一致。仅为 Source/API 增量；Windows GUI、Browser/双端完整业务不由此自动宣称通过。验收以此 PR 精确 SHA 的 CI 为准。

### Issue #41: recruitment event source ownership

Event creation rejects nonexistent source references (404) and sources owned by another candidate, including within the same project (409), before any event or success audit is written. Valid owned references, source-free scheduling and automatic structured-interview source publication retain their behavior. Five synthetic SQLite/API regression tests cover this shared Core contract in `convergence_tests/test_event_source_ownership.py`. This adds no Schema migration and does not repair historical invalid references. Exact-head source CI is required; these tests are not Windows GUI or full dual-carrier acceptance.

## Issue #41 增量：已完成面试的结构化证据修订

在 `PATCH /api/v1/events/{event_id}` 编辑由该事件自动生成的结构化面试 Source（问题、反馈、备注或结论）时，Event 不得静默覆盖与当前引用 Source 不一致的业务事实。如果文本发生实质变化，必须保留旧 Source 的不可变文本，并发布新 Source 和新的 MaterialRevision；新 Source 元数据标记 `supersedes_source_id`，历史 Source/Claim 不删除。相同文本的幂等更新不发布新材料版本；人工附着的外部 Source 不应被系统改写为面试 Source。

`convergence_tests/test_event_source_revision.py` 使用真实临时 SQLite/C11 API 验证编辑前后 Source、材料版本、来源归属、无变化更新及失败回滚。**该增量仅覆盖 Source/API 行为；具体 SHA 的 CI、真实 Chromium 点击、Windows WPF、双端并发以及既有 HumanDecision 的全部上下文复核仍须分别验收，不因增加测试而自动 PASS。**
