# C11 招聘业务链：独立面试评价与 Offer 状态闭环

## 目的与证据类型

本轮将此前只有零散 API 断言的招聘业务，扩展为**真实 Chromium 点击操作 → 真正 C11 HTTP API → 合成 SQLite 持久化 → 业务约束断言**的端到端验收。运行脚本是 `browser_acceptance/test_flows.py`，继续使用独立临时数据/Knowledge fixture，禁止真实候选人数据与生产 Provider 密钥。

这是浏览器端真实 UI 验收，不等同于用户 Windows WPF/WebView2 中逐项完成这些新场景的实际验收。此前 Windows 原生窗口启动、项目创建及招聘标准草案修改已获得真实实机证据，见 [GUI 验收记录](WINDOWS_GUI_FIRST_ACCEPTANCE.md)。

## 新增真实业务场景

### E2E-04：独立 Interview Scorecard

1. UI 创建项目与候选人，通过候选人“流程与跟进”创建结构化面试。
2. UI 打开 **独立 Scorecard**，分别让两名虚构评价者对同一 Criterion `research_reasoning` 提交不同 Rating 与行为观察。
3. 从真实 API 读取 Scorecard，核对两份 `submitted` 评价均保留，`criteria[research_reasoning].disagreement=true`。
4. 向同一 API 尝试覆盖已提交评价者的 Scorecard；服务器必须拒绝，原评分与评价者不变。
5. 不应因独立面试评价完成就自动将候选人推进至录用阶段，不对意见作隐性平均。**保留分歧，交由人工讨论。**

### E2E-05：Offer 草案 → 已批准 → 已发送 → 已接受

1. 新候选人未进入面试前，Offer 创建按钮必须禁用。
2. 经 UI **人工**阶段推进 `new → shortlisted → interview` 后才可创建 Offer 草案。
3. 无论 UI 如何显示，直接从 `draft` 跳到 `accepted` 的非法 API 操作必须拒绝。
4. UI 只列出当前状态合法的下一步，不再把无效状态展示为候选操作；按 `draft → approved → sent → accepted` 顺序经 UI 执行，每步从持久化 API 核对。
5. `accepted` 是 Offer 终态，更新按钮禁用；**Offer 已接受 ≠ 自动标记 Candidate hired，也 ≠ 自动写入 HumanDecision**。最终录用仍属于独立的人工决定与 Pipeline 业务动作。

## 已实施的产品修复

`frontend/dist/app.js` 原先向操作者展示所有 Offer 状态，包括不可能合法跳转的状态。现在以与后端 `_OFFER_TRANSITIONS` 一致的 `offerNextStatuses` 限制选项、拒绝空选择，并对 `accepted/declined/withdrawn` 禁止继续更新。

后端 `change_offer_status` 的独立状态约束未削弱。因此即使跳过 UI，非法状态仍会被拒绝。

## 验收范围与未覆盖项目

本次完成后，如同一源码提交的 CI 为 PASS，可声称有 5 条真实 Chromium 招聘场景（原建岗草案、材料+人工阶段+Offer 草案、面试排期，加上本轮两项）；不能由此推断历史 0.8.12-R2 的 725 项能力已经完全回归，也不能自动宣称：

- 人工 Claim 核验、评价标准版本发布与 Judgment、完整 Decision Context 及 Decision Lineage；
- OCR/ASR 在目标 Windows 上的实际效果、真实外部 AI Provider 配置及脱敏隐私验收；
- 全流程 Windows 原生 WPF/WebView2 点击验收、备份恢复、规模化性能与长时稳定运行。

下一轮优先补齐 **证据 Claim → 人工核实 → 评价判断 → HumanDecision → 材料/标准变化后 Decision 失效及重申** 的可证实全链路。
