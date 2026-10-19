# SRW · 智能招聘工作台

**本地优先的招聘业务执行与证据化决策工作台**。SRW 连接建岗、招聘标准、候选人收件、材料证据、核实/复核、面试、人工决策、Offer、联系运营及 Knowledge 治理。AI 仅提供可追溯的辅助建议，不自动作出录用决定。

> **仓库状态（2026-10-18）**：Git 主线是 `main`，版本 `1.0.0-alpha10-convergence11`，数据库结构 `v1_0014`。它是**持续开发中的源码与回归验证基线**，不是已通过 WPF 实机验收的 Windows Native 正式版。历史 `v0.8.12-R2` 是功能完整性参考，而非当前可直接运行的主线发行包。

## 快速导航

- [仓库组织、主线与分支治理](docs/REPOSITORY_GOVERNANCE.md)
- [26 条现存 Git 分支盘点](docs/BRANCH_INVENTORY.md)
- [现有能力、未决问题及开发状态](DEVELOPMENT_STATE.md)
- [总体架构与业务不变量](ARCHITECTURE.md)
- [真实浏览器业务验收](docs/BROWSER_ACCEPTANCE.md)
- [Windows/Portable 装配与发布规程](docs/RELEASE_PROCESS.md)
- [完整业务验收计划](docs/ACCEPTANCE_PLAN.md)
- [Pre-Git 历史发展](docs/history/PRE_GIT_HISTORY.md)
- [四份过去的开发包：SHA 清单及上传状态](docs/history/ARCHIVE_CATALOG.md)

## 产品能力

| 业务环节 | 当前已有的源码能力 | 仍需证明或完善 |
|---|---|---|
| 项目/岗位 | 招聘项目、职位生命周期、四步建岗、JD 草案、招聘标准版本和人工发布 | 更多 UI 全流程、复杂业务边界 |
| 候选人 | 单人及批量收件、文件/文本材料、候选人 Pipeline、联系方式、跟进计划 | 真实简历语料、批量错误恢复 |
| 证据与评价 | Source、Claim、原文定位/PDF 高亮、证据核实、Criterion Judgment、Decision Context | 更宽的真实浏览器验收、判断一致性 |
| 面试/决策 | 电话筛选、面试事件、独立 Scorecard、重新评价、人工决定和历史决定 Lineage | 完整跨环节端到端验证 |
| Offer 与运营 | Offer 草案及状态、工作台业务优先级、复核队列、今日联系、项目交接 | 复杂状态流和 WPF 实机复核 |
| AI/OCR/ASR | 保留 Provider/OCR/ASR 接入及隐私安全边界的源码能力 | 真实外部 Provider、模型质量与降级验收 |
| Knowledge | 五套历史知识库模型、治理提议、审核、差异/摘要、激活及回滚 | 当前生产库来源与版本审计 |
| 系统/交付 | 本地 HTTP 安全边界、备份/恢复、诊断包、源码/Native 清单与哈希安全门 | 可运行 Native 工件与目标 Windows 验收 |

**核心业务约束**：缺失证据 ≠ 评价得分 0；AI 提议 ≠ 人工决定；旧材料/招聘标准产生的决定不能在新决策上下文中自动继续有效；联系运营优先级不是候选人优劣排名。详情见 [架构](ARCHITECTURE.md)。

## 当前测试与交付真相

当前源代码测试总数为 **138 项**（GitHub CI 才能证明实际 PASS），外加独立的 **3 条 Chromium 真实浏览器业务验收场景**。原 `v0.8.12-R2` 的 **725 项测试**是历史版本库存参考，不能推导出当前版本达到相同的业务覆盖率。

2026-10-18 最近已确认的整合基线 `69f60b9`：
- [Source Gate：Ubuntu + Windows](https://github.com/ALV522/-SRW-/actions/runs/39134969100) — PASS（当时 109 项源回归）。
- [Chromium Business Acceptance](https://github.com/ALV522/-SRW-/actions/runs/39134969124) — PASS（3 条真实操作 + HTTP/SQLite）。
- [Repository Integrity](https://github.com/ALV522/-SRW-/actions/runs/39134969098) — PASS。

此后新增历史 ZIP 核验工具及其 4 项测试，**是否通过以对应新提交的 Actions 为准**；不能将旧运行结果冒充新提交的证明。

## 源码开发与验收

环境：Python 3.12、Node.js 22。对完整 Git checkout 安装当前 source test 依赖：

```bash
python -m pip install -r requirements-ci.txt
python scripts/check_source_integrity.py
python scripts/check_release_truth.py
python scripts/run_convergence_verification.py
```

浏览器业务验收采用独立工作流 `.github/workflows/browser-e2e.yml`，在隔离临时数据库与合成 Knowledge fixture 上运行 Playwright/Chromium。它不访问真实候选人数据，不等于 WPF/WebView2 Windows GUI 验收。

**不要将 GitHub Actions 提供的 Source ZIP 当作双击即用 Portable 包。** 当前 Git 代码库不包含独立审计的完整 Windows Python Runtime、五份生产 Knowledge DB 或已经实机验收的 Windows Native Host。合成测试 Knowledge 不可替代生产知识库。详见 [装配与发布规程](docs/RELEASE_PROCESS.md)。

## 主线、发行与历史包

- **`main` 唯一当前开发主线**。通过 PR 开发并跑完源回归/Chromium 验收，合并后再次核对 main 的同一提交；保留旧分支用于溯源，不再将其视为并行发行版。
- **能力保留以 v0.8.x 为参照**。过去的 alpha 轻量化尝试有流程价值，但不应覆盖已成熟的 Evidence、Knowledge、OCR/ASR、运营与可靠性能力。
- **GitHub Releases 不是自动等于当前版本**。仓库中现有 `v0.8` Release 附带的是 `SRW_v0.8.8_Web_Portable.zip`（历史 Web 包），**不是**当前 C11 的 Native Windows 发行版。
- **四份用户提交的历史开发包目前没有上传二进制到 GitHub**。已在 [历史 ZIP 档案目录](docs/history/ARCHIVE_CATALOG.md) 保存原始文件的 SHA-256、大小、类别、风险及上传状态；不要把大 ZIP 直接 commit 到 `main`。未来上传应使用独立的 Historical/Unverified Release assets，并先完成数据库敏感数据和供应链审查。

## 代码与文档在哪里

`backend/srw/` 是核心业务/运行时/HTTP，`frontend/dist/` 是当前保留的 WebView2/浏览器界面，`desktop/SRW.Desktop/` 是 Windows Host 源码；`convergence_tests/` 负责当前源回归，`browser_acceptance/` 验证真实浏览器操作；`verification/` 保存证据，`scripts/` 保存核验与装配工具；`docs/history/` 仅记录历史，不替换当前主线。详见 [仓库治理文档](docs/REPOSITORY_GOVERNANCE.md)。

## 下一阶段

按照“**完整招聘业务体验 → 真实浏览器验收 → 可信 Runtime/Knowledge → Windows Native 构建 → 目标机器验收**”推进。优先补充标准发布、人工核实/Claim、独立 Scorecard、最终决定、Offer 生命周期及项目交接的 Chromium 验收，再安排 Host/Portable 实物恢复和验收；不能只增加外观和抽象设施。

## 历史资源恢复（2026-10-18）

已从用户提供的 alpha10 Web Portable 中找到 **1,611 个 Windows Python Runtime 文件**，并从 v0.8.12-R2 中恢复五套经 SQLite `integrity_check` 的 Knowledge DB。同名数据库与 v0.8.10 及 alpha10 的哈希一致。请看 [旧资源恢复证据、两种 Windows Host 路线与用户所需操作](docs/LEGACY_RESOURCE_RECOVERY.md)。提供固定历史 ZIP 哈希的 `scripts/recover_archived_external_inputs.py`，以及不执行旧解释器的 `scripts/check_embedded_runtime_compatibility.py`。旧 Python 仅 5/13 项当前 C11 依赖完全匹配，**恢复成功不等于可启动**；Host 仍可选择上传精确旧载体或通过 GitHub Windows CI 从源码重新编译。两者均未实机验收。

### Alternative C11 source-built Windows Host assembly

A Windows/.NET 10 CI workflow now produces digest-bound, unsigned WPF Host candidate artifacts for exact source commits. `scripts/build_native_from_source_host.py` accepts that candidate and individually recovered Runtime/Knowledge inputs, validates their SHA/provenance/version requirements and audits the final UNVERIFIED GUI ZIP. It does not need the historical v0.8.8 Windows carrier, but the alpha10 Python Runtime must first be updated from its 8/13 version mismatches. See [source Host Native assembly procedure](docs/SOURCE_HOST_NATIVE_ASSEMBLY.md).

### C11 Windows Python 离线兼容升级

新增 [Windows Runtime 隔离升级流程](docs/RUNTIME_UPGRADE.md)：从 GitHub Windows CI 下载同一源码提交的带 SHA-256 清单的依赖 Wheelhouse；对已经恢复的 alpha10 Python 3.12 进行全新目录的 `Lib/c11-overlay` 安装，严格校验 `python312._pth` 的加载优先级，**实际运行嵌入式 Python 导入验证**，保留五个 Knowledge DB 不变。未通过嵌入式运行测试时禁止 Native 封包。旧输入文件绝不原地覆盖；Windows Host 与 WebView2 GUI 实机验收仍属于独立阶段。

### C11 完整 Windows Native 候选包（Prepared，未 GUI 验收）

已使用同一 Git SHA `d8d032d` 的 GitHub Source ZIP、Windows Host 和 Wheelhouse，结合历史 Runtime / 五套 Knowledge，实际装配出 **101,617,623 B** 的 `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip`。源码、2332 项 Runtime、五库 SQLite、Host provenance 及最终 ZIP **2629 个文件**的 SHA 白名单审计通过。嵌入式 Windows Python 与 WPF GUI **尚未在目标 Windows 执行**。验收命令、SHA 与边界见 [完整候选包与 Windows 实机验收](docs/PREPARED_NATIVE_WINDOWS_ACCEPTANCE.md)。
