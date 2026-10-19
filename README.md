# SRW · 智能招聘工作台

**本地优先、证据驱动的招聘业务工作台。** SRW 覆盖建岗、招聘标准、候选人收件、材料与 Claim 证据、人工核实、面试/Scorecard、Decision、Offer、联系运营、Knowledge、AI/OCR/ASR 辅助。AI 建议不等于人工录用决定；缺失证据不按零分处理；材料或招聘标准变化后，旧决策上下文不能自动复用。

> **项目状态（2026-10-19）**：当前唯一整合研发主线是 `main`，C11 版本 `1.0.0-alpha10-convergence11`、Schema `v1_0014`。此前 **`d8d032d` 的 Windows Native 候选包**在真实 Windows 上通过 WPF/WebView2 基础启动、后端就绪、项目创建、招聘标准草案修改和退出验证。这是**特定旧工件的基础 GUI 验收**，不是最新 `main` 已发布正式 Portable/RC/GA。

## 目前已经验证了什么

| 范围 | 已通过 | 尚未证明 |
|---|---|---|
| **当前 main 源码** | `c9d70cd48d03`：Ubuntu/Windows 各 **146** 项测试及资源门禁通过；280 项源码 SHA 清单通过 | 历史 725 项测试已经全部恢复、所有业务已可真实使用 |
| **真正 Chromium 浏览器** | 同一 SHA 的 **5 条** C11 API + 临时 SQLite 业务用例通过 | 全业务、真实简历、OCR/ASR/AI Provider 及 WPF GUI 的完整覆盖 |
| **Windows Native 候选包** | `d8d032d`：真实 WPF/WebView2 启动、2 项业务写入与退出通过 | 现行 main 的整包发行验收、Scorecard/Decision/Offer/备份全链路 |
| **隔离 Web 实验 E1–E5** | 合成数据：只读网页、条件更新、SQLite 原子 CAS、独立 Core、受保护附着 | 生产身份授权、真实数据多端安全写入 |
| **Native SOURCE Lab** | Windows CI 启动**真实 WPF EXE**，浏览器 E1 与其读取相同临时 C11 Core/SQLite，WebView2 已加载 | 正式嵌入式 Runtime、生产 Knowledge DB、独立 Core 的 Windows 正式产品 |

精确验收证据：[main Ubuntu/Windows](https://github.com/ALV522/-SRW-/actions/runs/39227251473) · [Chromium](https://github.com/ALV522/-SRW-/actions/runs/39227251414) · [源码完整性](https://github.com/ALV522/-SRW-/actions/runs/39227251510) · [真实 Windows GUI](docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md) · [E1–E5 沙盒](https://github.com/ALV522/-SRW-/actions/runs/39193776226) · [Native SOURCE Lab](https://github.com/ALV522/-SRW-/actions/runs/39196390613)。

**验收结果只适用于对应源码 SHA、运行环境和工件类型。** 不能使用旧版实验或已通过的 GUI 截图，证明今天的新版整包已验收。

## 产品能力和保留原则

| 业务域 | C11 中已有的主要能力 | 后续主要缺口 |
|---|---|---|
| 项目与标准 | 项目生命周期、四步建岗、JD 草案、Criteria/标准版本与发布 | 发布/重发的完整 UI 回归与上下文保真 |
| 候选人与材料 | 收件、Pipeline、Source/材料版本、联系方式和跟进计划 | 文件/PDF/OCR、批量异常恢复与去重 |
| Evidence/Decision | Claim、Criterion 核实、Decision Context、来源定位、复核队列 | 缺失证据与冲突判断、跨版本失效规则 |
| 面试/Offer | 电话筛选、独立 Scorecard（两位面试官评价/分歧保留）、人工决定、Offer；新增真实浏览器合法状态流测试 | Claim→Decision 全链路与真实 Windows 复核 |
| 运营/Knowledge | 优先级、交接、任务、历史五库治理与回滚 | 生产库来源/版本，真实业务性能与可靠性 |
| AI/OCR/ASR | Provider/处理器与隐私边界的源码能力 | 实际 API、模型质量、降级和长时运行 |
| 交付安全 | 备份/恢复、文件白名单、哈希、运行时/Host 门禁 | 当前 SHA 的完整 Portable/Native 实物、升级回滚验收 |

**历史 `v0.8.12-R2` 是成熟业务能力的对标对象，不是当前 C11 版本。** 不得为了 UI 或架构重写删除 Evidence、AI/OCR/ASR、Knowledge、人工决策、Offer、备份等成熟功能。历史 725 项测试也不是当前 C11 的 PASS 数。

## 运行与下载：区分工件

- **源码开发**：完整 checkout `main`，Python 3.12 + Node.js 22。下面的校验命令适用于源码，不代表自动生成 Windows Portable。
- **Windows 基础实机候选**：`d8d032d` 工件已做有限 GUI 验收，详情 [Prepared Native 指南](docs/PREPARED_NATIVE_WINDOWS_ACCEPTANCE.md) 与 [实机报告](docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md)。它不是当前 `main` 的正式发行版本。
- **HTML E1–E5/Native SOURCE Lab**：在 [隔离探索分支](https://github.com/ALV522/-SRW-/tree/explore/html-site-prototype)，使用临时合成 SQLite/Knowledge。Native SOURCE Lab 确实启动 WPF，但依赖外部 Python/运行时，**不是独立 Portable**。
- **历史 GitHub Release**：`v0.8` 的 `SRW_v0.8.8_Web_Portable.zip` 是旧 Web 包，不是新 C11 Windows Native。

不要把源码 ZIP、Host-only EXE 或临时 SOURCE Lab 预览包说成用户可以正式部署的完整 Windows 产品。任何测试不应向 GitHub 上传真实简历、SQLite、密钥、完整工作区锁及私人日志。

## 开发者验证

```bash
python -m pip install -r requirements-ci.txt
python scripts/check_source_integrity.py
python scripts/check_release_truth.py
python scripts/run_convergence_verification.py
```

真实 Chromium 验收位于独立 `.github/workflows/browser-e2e.yml`，它使用真实 C11 服务和一次性合成数据库。修改被跟踪文件（**包括文档**）必须更新 `SOURCE_MANIFEST.sha256`；历史 `SOURCE_RECOVERY_MANIFEST.sha256` 保持不变。CI 是否 PASS 应以**本次提交**的记录为准。

## 仓库与文档导航

| 位置 | 作用 |
|---|---|
| `backend/srw/`、`frontend/dist/`、`desktop/SRW.Desktop/` | Core/API、保留现有业务前端、Windows WPF Host |
| `convergence_tests/`、`browser_acceptance/`、`verification/` | 源测试、真实浏览器测试、工件与历史证据 |
| `scripts/`、`build-lock/`、`.github/workflows/` | 装配、依赖锁、供应链与完整性 CI |
| [开发状态](DEVELOPMENT_STATE.md) · [产品路线图](docs/ROADMAP.md) | 已有业务、待办、优先级、退出门槛 |
| [仓库治理](docs/REPOSITORY_GOVERNANCE.md) · [分支盘点](docs/BRANCH_INVENTORY.md) | main、历史分支、隔离探索与 PR 规则 |
| [发布规程](docs/RELEASE_PROCESS.md) · [业务验收计划](docs/ACCEPTANCE_PLAN.md) | SHA/工件边界与端到端业务验证 |
| [历史演进](docs/history/PRE_GIT_HISTORY.md) · [原始 ZIP 档案](docs/history/ARCHIVE_CATALOG.md) | 历史溯源，不能取代当前 release |

## 未来发展：以业务完整性为中心

1. **P0 业务纵向闭环**：建岗→标准发布→收件→Source/Claim→人工核实→面试/Scorecard→Decision→Offer→联系/交接，补齐真实浏览器及 Windows 业务测试。
2. **P1 Windows 产品交付**：以当前准确 SHA 重建 Runtime、五套生产 Knowledge、Host，验收连续启动、文件锁、备份/恢复、升级/回滚、真实 Provider；基础 GUI PASS 只是起点。
3. **P2 一个 Core，Web + EXE 两载体**：参考 E3 事务级乐观并发、E4 独立 Core 生命周期、E5 受保护 attach 与 Native SOURCE Lab 真实 WPF 读同一 Core 的证据，先经正式 Core/Host 改造与权限审计，再完成真实双端写入。
4. **P3 发行与维护**：冻结工件身份、完成能力回归与兼容性矩阵、建立 RC/GA 验收；不将 E0–E5 视作新产品版本号。

详细依赖与退出标准见 [路线图](docs/ROADMAP.md)。**近期不建议做两套独立 SQLite 的双向同步**，应围绕同一个权威 SRW Core 构建 Web 与 EXE。

### 最近的业务验收进展

当前 `c9d70cd` 已追加两条 Chromium 端到端业务场景：**两名面试官独立 Scorecard 与评分分歧保留**，以及 **Offer 从 Draft→Approved→Sent→Accepted 的合法人工状态流**（接受 Offer 不自动录用）。见 [Scorecard/Offer 浏览器闭环](docs/BUSINESS_E2E_SCORECARD_OFFER.md)；下一步重点仍是 Claim 核实→Decision Context→人工决定及上下文变化后的失效。

### 本轮新增：证据决策链的实际业务验收

[Decision Lineage 验收](docs/BUSINESS_E2E_DECISION_LINEAGE.md)：发布必须核实的岗位标准→录入材料→人工核实生成 Source/Claim/Judgment→显式提交 HumanDecision→新材料使旧决定失效→重新核实→显式重申，新增第六条真实 Chromium/SQLite 测试。UI 的“按当前证据重申”仅在当前服务端行动门槛满足时可用。这是浏览器业务验收，不是 Windows WPF 全流程验收；以同提交 CI 为准。

### 新增 P0 标准版本失效验收（E2E-07）

[招聘标准重新发布的决策失效验收](docs/BUSINESS_E2E_PROTOCOL_REVISION.md)：保留候选人 Source 不变，新发布第二版具有必须核实标准的岗位协议；验证旧 HumanDecision 失效、未核实时直接重申被拒绝、UI 重申按钮禁用。此流程与 E2E-06 的“材料变更→重申”互补。第七条 Chromium 场景以本提交的 CI 实际结果为准。
