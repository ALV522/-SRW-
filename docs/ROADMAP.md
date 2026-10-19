# SRW 产品路线图（2026-10-19）

这是一份**待执行计划**，不是把未完成事项声明为 PASS。当前唯一产品开发源码主线为 `main` / C11；历史 `v0.8.12-R2` 是成熟业务完整性对照；HTML E1–E5 和 Native SOURCE Lab 属于独立探索。

## 判定标准

- 源码存在、源回归通过、Chromium 通过、WPF GUI 实机通过、完整 Native/Portable 构建、RC/GA **是六类不同结论**，每一步均须精确 Git SHA 与工件证据。
- 保留 Source/Claim、Criterion/Decision、人工核实、面试、Offer、AI/OCR/ASR、五库 Knowledge、备份/恢复。未经行为等价测试，不得为了换框架缩减功能。
- 近期 Web/EXE 目标是**一个权威 Core + SQLite/Blob/Job Engine，两套 UI**，不是两个数据库间的简单双向同步。

## P0 · 业务完整性与质量基线

1. 制作 `v0.8.12-R2` → C11 能力对照矩阵：源码已实现、浏览器可操作、Windows 可操作、缺失、替代设计及测试覆盖分别列明。
2. 建立纵向业务验收：**岗位/标准 Draft 与发布 → 候选人导入与当前材料 → Claim 核实 → 面试/独立 Scorecard → 人工 Decision → Offer → 联系计划/项目交接**。
3. 对每个阻断项附用户操作步骤、业务影响、根本原因、修复 PR、回归测试与确切运行证据；优先处理损坏证据/决策可信性的缺陷。
4. `DEVELOPMENT_STATE.md` 的历史 138/121/109 项测试统计保留其时间含义；当前通过的主线 `c9d70cd` 是 Ubuntu/Windows 各 **146 项**、Chromium **5 项**、SHA 清单 **280 项**。

**退出条件**：完整能力对照矩阵存在；所有 P0 业务环节有可执行验收脚本和明确 PASS/FAIL/BLOCKED，未用按钮或抽象模块数量代替业务覆盖。

## P1 · Windows Native 的可重复产品验收

1. 利用 `d8d032d` 的真实 WPF/WebView2 基础 GUI 证据，但不要把它视为当前 `main` 的完整验收。新 Native 候选必须重新绑定准确源码、Host、Runtime、五套**生产** Knowledge DB 哈希。
2. 在目标 Windows 上重复验证：冷启动/重启、窗口与 WebView2、后端就绪、锁释放、Python 缓存不污染、长时运行、崩溃/恢复、备份/恢复与数据升级/回滚。
3. 用合成或经授权脱敏的招聘样本验证 PDF/OCR、ASR、Provider 超时降级、材料版本、AI 建议/人工判定边界、项目/候选人完整流程。
4. 维护唯一可复现工件清单：版本、源码 SHA、构建依赖、Host 与 Runtime 身份、Knowledge 来源、实际测试设备、剩余缺陷。

**退出条件**：一个具体 Native/Portable 候选在目标 Windows 的基础运行与完整招聘纵向业务都能重复通过，正式人工复核后才能讨论 RC。

## P2 · Web + EXE 共用 Core

1. 以 E1/E2 的读写 API 原型、E3 的 SQLite **事务级** If-Match CAS、E4 的独立 Core 进程所有权、E5 的单次附着凭据/身份固定，以及 Native SOURCE Lab 真正 WPF + 浏览器读同一合成 Core 为可行性证据。
2. 将 E3 的 revision 与审计纳入**正式 Schema 和全部 Action Plan 写入口**；条件校验、更新、审计在一次数据库事务内完成，过期写入返回 412，错误和重试不生成假成功审计。
3. 从 EXE 拆分 Core Supervisor 的工作区锁、停机/重启和多载体附着生命周期。EXE 关闭不应无意让独立 Web 失效；OCR/ASR/AI Job Engine 只能有一个权威调度器。
4. E5 的 localhost 能力仅是探索。正式服务须身份验证、授权、会话吊销、CSRF/Origin、防伪附着及数据域隔离；远程访问需要另行 TLS 和安全评审。
5. 在**同一真实 Windows Core**上实测 WPF/WebView2 + 浏览器同时读写相同 Candidate/Source/Claim/Decision Context，校验冲突拒绝与业务审计。

**退出条件**：实际 Windows EXE 与 Browser 使用同一受信任 Core 运行完整合成招聘流程、不会双重启动后台任务或数据库，并通过重启/关闭任一界面的真实联调测试。

## P3 · 发行、维护与规模化

1. 严格区分 Source ZIP、Host-only、实验包、Prepared Native、Portable Candidate、RC、GA，工件与哈希可独立验证；GitHub 旧 `v0.8` Release 不代替新产品。
2. 以测试保障为前提拆分 `fullworkbench.py` 和大型前端模块，增加安全、可访问性、性能/资源、兼容性与故障注入。
3. 抽检真实匿名招聘样本，建立人工反馈的证据/评价一致性、Provider 故障处理、迁移与备份回滚手册。

**退出条件**：官方 Release 指向**唯一通过验收的具体工件**，其功能、隐私、安装、升级及已知限制均可复核。

## 核查依据

[开发状态](../DEVELOPMENT_STATE.md) · [业务验收计划](ACCEPTANCE_PLAN.md) · [Windows GUI 首次证据](WINDOWS_GUI_FIRST_ACCEPTANCE.md) · [仓库治理](REPOSITORY_GOVERNANCE.md) · [发布规程](RELEASE_PROCESS.md) · [E1–E5 实验](https://github.com/ALV522/-SRW-/tree/explore/html-site-prototype/explorations/html-site) · [Native SOURCE Lab](https://github.com/ALV522/-SRW-/blob/explore/html-site-prototype/explorations/html-site/NATIVE_SOURCE_LAB.md)。

## 2026-10-19 业务增量

`main` 的 [PR #32](https://github.com/ALV522/-SRW-/pull/32) 已让真实 Chromium 从 3 增至 **5 个**场景：独立 Scorecard 两个评价者分歧不可覆盖、Offer 的人工合法状态更新（不自动录用）。下一轮 P0 应聚焦 **Claim→核实→判断→HumanDecision→材料或标准改变后的上下文失效**，不应重复开发已经通过的 Scorecard/Offer 案例。[验收证据](BUSINESS_E2E_SCORECARD_OFFER.md)。
