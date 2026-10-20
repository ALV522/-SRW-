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
