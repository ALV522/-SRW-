> **暂不使用主线保护（2026-10-20）**：负责人决定暂不启用 GitHub Ruleset；以 [无保护期协议](NO_BRANCH_PROTECTION_PROTOCOL.md)、根目录 AGENTS.md、预编辑脚本、PR/CI 和 main 推送事后审计作为临时补偿。**不等于真正的分支权限保护**，不得直接向 main 推送。

> **G1 加强规范（2026-10-20）**：所有 Agent 从仓库根目录 [AGENTS.md](../AGENTS.md) 开始，按序阅读产品/版本/双载体/验收契约。PR 使用 .github/pull_request_template.md，运行 Governance Contract CI；如要防止绕过，仓库管理员必须将合并要求和治理检查设置为 main 的必需规则。原有分支盘点是历史快照，未经逐一审计不得删除分支。

# SRW 仓库治理与分支规则（2026-10-19）

## 唯一整合主线与版本身份

**`main` 是唯一经过 PR/CI 约束的产品开发源码整合主线**。当前版本 `1.0.0-alpha10-convergence11`、Schema `v1_0014`。历史 `v0.8.12-R2` 仅作为成熟业务能力的保留/对标对象，不是同一源码身份。

真实 Windows 的 `d8d032d` WPF GUI 基础验收已通过，但不表示更新的 `main` 已经发布正式 Native/Portable。E1–E5/Native SOURCE Lab 成果属于独立 `explore/`，不能无审计地整体合并或访问真实用户数据。

## 分支管理

本次 GitHub API 盘点前有 **35** 条分支；创建本次 `docs/repository-status-readme-20261019` 文档 PR 分支后，快照为 **36 条（含 main）**。详细 SHA 见 [分支盘点](BRANCH_INVENTORY.md)。数量是随分支变动的快照，不是固定项目版本数。

| 前缀 | 角色与合并规则 |
|---|---|
| `main` | 唯一可作为正式整合源码的主线，不允许 force-push |
| `dev/`、`fix/` | 垂直业务开发、缺陷修复与回归；从最新 main 分出，经 PR 合并 |
| `docs/` | 文档、历史证据和版本治理；同样必须更新源码 SHA 清单并通过 CI |
| `explore/` | HTML E1–E5、Native SOURCE Lab 等技术实验；单独验收，不直接提升为正式产品 |
| `integration/`、`repair/` | 旧整合/源恢复记录；保留溯源，不能当作发行分支 |

**不自动清理任何旧分支**。逐项 compare `main...branch`、查看 PR 合并、唯一修改和工件来源，确认可复原后再讨论归档或删除；不要根据名称或时间直接删掉研发证据。

## 源码与 CI

| 目录 | 当前职责 |
|---|---|
| `backend/srw/kernel/`、`modules/`、`surfaces/` | 业务不变量、领域模型及读模型 |
| `backend/srw/api/`、`runtime/` | HTTP Core、本地数据库、任务、身份、备份恢复 |
| `frontend/dist/`、`desktop/SRW.Desktop/` | 保留业务前端、WPF/WebView2 Host 源码 |
| `convergence_tests/`、`browser_acceptance/` | Python 业务回归、Chromium 真浏览器集成 |
| `scripts/`、`build-lock/`、`verification/` | 源码 SHA、封包与供应链证据 |
| `docs/history/` | Pre-Git 和历史 ZIP 溯源 |
| `.github/workflows/` | 源回归、Repository Integrity、Chromium、Windows Host/Wheelhouse；探索分支另有隔离工作流 |

按当前 `main` `c9d70cd48d03` 的正式 CI： [Ubuntu/Windows 146 项 Source Gate](https://github.com/ALV522/-SRW-/actions/runs/39227251473)、[5 项 Chromium](https://github.com/ALV522/-SRW-/actions/runs/39227251414)、[280 项 Source Integrity](https://github.com/ALV522/-SRW-/actions/runs/39227251510)，均 PASS。Windows [Host Candidate](https://github.com/ALV522/-SRW-/actions/runs/39227251307) 和 [Offline Wheelhouse](https://github.com/ALV522/-SRW-/actions/runs/39227251286) 是各自构建门禁，不能替代实际目标机的完整 GUI/业务验收。

探索实证：[E1–E5 CI](https://github.com/ALV522/-SRW-/actions/runs/39193776226)、[Native SOURCE Lab](https://github.com/ALV522/-SRW-/actions/runs/39196390613)。后者确实在 Windows CI 启动了真实 WPF EXE，浏览器 E1 与它读取相同合成 Core/SQLite；但使用临时 Python/Knowledge，没有认证为正式 Portable。


## API-first 模块边界（2026-10-21）

产品负责人已批准 [ADR-0002](decisions/ADR-0002-api-first-modular-monolith.md) 和 [专项重构路线图](API_FIRST_MODULAR_CORE_ROADMAP.md)。仓库仍保持 monorepo 与单一 `main`，但代码边界要逐步强化：Domain/Application/API/Carrier/Frontend 分责，Windows 与 Browser 均通过统一 Core contract 取得业务能力。

当前静态热点是 `backend/srw/api/fullworkbench.py` 与 `frontend/dist/app.js`。后续拆分必须使用小 PR、保持 URL/Schema/业务行为，并用 Source/API/Chromium/需要时 Windows 测试证明等价；不得为了目录整洁建立第二套 Core、第二套 SQLite、微服务或新前端框架。

## 每次提交、发布应执行的门禁

1. 从最新 `main` 开分支，确定业务问题、用户操作与验收用例；小范围 PR 优于一次合并多个实验体系。
2. 修改任何受跟踪文件（包含 README/文档）时更新 `SOURCE_MANIFEST.sha256`；`SOURCE_RECOVERY_MANIFEST.sha256` 是历史记录，**不能重建来掩盖修改**。
3. 正式源码 PR 跑完所需 Ubuntu/Windows、Repository Integrity、Chromium/Native 回归；只以**同一提交的 SHA** 为依据合并。合并后再次核对 main 的 CI。
4. Windows 发布物逐一标识 Source ZIP、Host-only、实验 Preview、Prepared Native、Native Candidate、Portable、RC/GA；保留准确源码 SHA、Host、Runtime、五库 Knowledge、输入哈希、工件哈希和机器验收结果。
5. 禁止将真实简历、候选人 SQLite、Provider 密钥、私人路径/会话令牌、工作区锁或原始隐私日志上传仓库、CI 或公共 Releases。
6. 历史 ZIP（[档案清单](history/ARCHIVE_CATALOG.md)）仅经过来源/隐私/完整性审查后才能作为独立 Historical/Unverified assets 发布。旧 `v0.8` Release 的 Web ZIP 不是 Windows Native。
7. 不为 UI 美化牺牲 0.8.x 成熟 Evidence、Decision、Offer、AI/OCR/ASR、Knowledge、Backup 能力；优先用业务验收来确认保真。

详细开发顺序见 [ROADMAP](ROADMAP.md)，当前事实以 [README](../README.md) 和 [WINDOWS_GUI_FIRST_ACCEPTANCE](WINDOWS_GUI_FIRST_ACCEPTANCE.md) 为准。

## 仓库整理边界（2026-10-26 起）

旧 `docs/BRANCH_INVENTORY.md`、`DEVELOPMENT_STATE.md`、`docs/history/`、E1–E5 与 PR #101 是历史证据：**本轮不删文件、不删远端分支、不重写提交或 tag**。日后每条分支都要先审计与 main 的唯一提交、PR 关联、可恢复性、隐私风险与工件来源，再决定去留。

最新进度参阅[集成队列](INTEGRATION_QUEUE.md) 与[风险台账](ENGINEERING_RISK_REGISTER.md)；不把历史静态统计改写成当前测试结果。
