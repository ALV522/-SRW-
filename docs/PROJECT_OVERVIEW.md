# SRW 项目总述与事实基线

> 本文为治理基线（2026-10-20）。它不是最新 CI 的动态 PASS 报告；所有测试结论以准确 Git SHA、执行记录及工件哈希为准。最新可验证状态参见根目录 README、DEVELOPMENT_STATE.md、验收计划以及 GitHub Actions。

## 1. 目的和用户

SRW（智能招聘工作台，Smart Recruitment Workbench）是一个 **local-first、evidence-centered、AI-assisted** 招聘执行工具。目标是在本机支持岗位/标准、候选人资料、证据核实、面试、人工决定、Offer、联系跟进、知识库与辅助 AI/OCR/ASR，减少招聘人员在多处资料之间查找与重复操作的成本。它不是纯 AI 打分器、全自动录用系统或云端企业 SaaS。

核心使用者：独立 Recruiter、小型招聘执行团队或专职招聘人员。真实用户研究安排在**可用产品内部验收完成之后**，但并不豁免合成数据和人工操作的业务验收。

## 2. 演进与保留

历史 v0.8.x，特别是 v0.8.12-R2，是功能保真对照，不是当前 C11 源码或正式发行物。历史曾出现新 alpha 版在 UI/架构重构后失去成熟业务能力的问题。因此现行 C11 要以业务能力对照和回归验证为原则，严禁因美化或全面重写而丢失 Source/Claim、Knowledge、AI/OCR/ASR、面试/Offer、人工决策、备份等能力。

C11 的目标不是重写为新 UI、全新业务内核、微服务或者 SaaS，而是在现有框架上完成业务闭环和 Windows/Web 本地双入口。

## 3. 已知事实（不外推）

- 当前开发主线以 VERSION=1.0.0-alpha.11（工程里程碑 C11）/ Schema=v1_0014 标识；2026-10-21 已按版本政策完成 SemVer 迁移（本地执行，远端 CI NOT RUN）；更精确的源码身份是 Git SHA。实施新版本政策见 VERSION_POLICY.md。
- 2026-10-19 文档曾在 c9d70cd 提交上记录 Ubuntu/Windows 各146项源码回归、5条 Chromium 业务场景；后又增加关于 Evidence Decision 和标准重新发布的 E2E-06/07，是否通过以各自精确提交 CI 为准。不可累计不同提交的数字。
- d8d032d 的 Windows WPF/WebView2 Native 候选在用户机器上实际通过启动、项目创建、标准草案修改和干净退出；**不**意味着最新 main 的所有业务或新版完整 Native 已在实机通过。
- main 包含新版 Native upgrade kit 的脚本和来源核验流程；相关构建是否在当前 HEAD 成功且实机通过，需要独立验收。
- explore/html-site-prototype 的 E1–E5 和 Native SOURCE Lab 使用合成数据，已验证一系列共享 Core/Browser/WPF 技术可行性，但没有完成正式双端安全写入和双载体发行。
- OCR/ASR、真实 AI Provider、生产 Knowledge、备份/迁移、完整 WPF 招聘闭环依然需要相应工件的实测。

## 4. 正在努力实现的产品

第一阶段产品目标是本地、可独立运行、可备份恢复的招聘工作台，Windows EXE 与 HTML/Browser 本地入口**并行开发、争取同期交付**。统一 SRW Core、SQLite/Source Blobs/Knowledge、业务不变量、审计及后台任务唯一所有权。界面可复用现有前端，不另建独立业务系统。

业务主链：建立岗位与发布 Criteria → 候选人收件/材料版本 → Source/Claim 与人工核实 → Interview/Scorecard → HumanDecision → Offer/联系跟进 → 材料或标准变更时决策失效、人工重申 → 项目交接/备份恢复。

业务底线：Claim 不等于已核实事实；缺失证据不等于零能力；模型建议不等于人类决策；上下文变化不得自动继承旧决定；历史决策不得覆盖丢失。

## 5. 当前主要阻断点

1. 同一当前源码 SHA 的 Windows Native 完整装配、安装依赖、业务操作与恢复验收。
2. 将 v0.8.12-R2 能力逐项与当前 C11 的源码/浏览器/Windows/质量测试做对照；完成纵向 E2E 与异常路径。
3. Web 探索成果进入受审计正式 Core：事务写入/状态修订、Core Supervisor、会话保护、WPF 与浏览器实际双端读写。
4. 统一动态状态报告与版本规范；历史文档数字不得自动等同于最新 HEAD。
5. 完成首个可用双入口候选后，再启动真实招聘人员反馈。

## 6. 仓库与权威信息

- README.md：项目概览、历史精确证据导航。
- AGENTS.md：AI/协作者必读入口。
- docs/PRODUCT_CHARTER.md：产品边界与变更授权。
- docs/CAPABILITY_MATRIX.md：业务模块、现有测试与 Windows/Web 的明确证据边界。
- docs/DEVELOPMENT_GOVERNANCE.md：开发流程和强制检查。
- docs/VERSION_POLICY.md + VERSION_POLICY.json：版本、Schema、SHA、渠道、工件身份。
- docs/DUAL_CARRIER_PLAN.md：Windows/HTML 并行计划和集成门禁。
- docs/ACCEPTANCE_PLAN.md：详细现存业务与 Windows 验收场景。
- docs/ROADMAP.md：既有路线图，遇到顺序冲突以新宪章及双轨计划为准。
- docs/RELEASE_PROCESS.md：源码/Windows 工件发布和回滚。
- docs/OWNER_GUIDE.md：产品负责人操作指南。
- docs/NO_BRANCH_PROTECTION_PROTOCOL.md：暂不启用 main 服务端保护时必须遵守的替代流程。

**事实 ≠ 假设 ≠ 规划 ≠ 验收结果。** 在任何 Agent 或宣传文件中均需明确区分。
