# SRW 业务 ↔ 代码逻辑映射（2026-10-21）

> 目的：把“业务上完整”与“代码上不臃肿”变成可核对的两张表。本文是结构性裁判依据，不替代 [CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md)（验收证据矩阵）与 [API_V1 契约](contracts/API_V1.md)（路由契约）。所有行状态以本文标注的代码位置为准；验收状态另见上述两份文档。

## 1. 架构总览：一个 Core、一个契约、两个载体

```
业务不变量与状态机   backend/srw/kernel + backend/srw/modules/*（17 个域，纯领域逻辑，可单测）
读模型/投影          backend/srw/surfaces/*（候选人工位/项目/协议/工作台/Pipeline/导出）
HTTP 契约层          backend/srw/api/*（app.py 核心 + fullworkbench.py + 8 个辅路由模块，146 条 /api/v1 路由）
载体 A（Windows）    desktop/SRW.Desktop（WPF/WebView2 Host：派生后端进程、loopback HTTP、工作区租约、日志脱敏）
载体 B（Browser）    frontend/dist（index.html + app.js + convergence03–08，ES module + window 总线）
数据                 SQLite（Schema v1_0014）+ Source Blobs + 5×Knowledge + 审计流（modules/audit）
```

宪法约束：业务判断只发生在 Core（D2）；载体不得自建第二套真相（A6）；HTTP 层只做校验/序列化/错误映射（ADR-0002）。

## 2. 业务域映射表

| # | 业务域（操作者动作） | 领域逻辑（modules） | 读模型（surfaces） | HTTP 落点（api） | 测试 | 载体覆盖 |
|---|---|---|---|---|---|---|
| 1 | 建岗与标准发布（四步向导、Draft、显式发布、重发布） | `protocol`（repository/状态机）、`recruiting.workbench`（job setup） | `protocol_workspace`、`projects` | app.py（protocol-workspace/publish）+ fullworkbench（job-setup） | test_01/06/07 浏览器 + 收敛测试 | Browser ✅ / Windows 部分（d8d032d 历史） |
| 2 | 候选人收件与材料版本（新增、粘贴/文件材料、去重、归档） | `candidate`（commands/repository）、`intake.service`、`importer`（v0.8 迁移） | `candidate_workspace` | fullworkbench（candidates/ingest/batch）+ app.py（sources/text） | test_02/08 浏览器 + 收敛 | Browser ✅ / Windows NOT VERIFIED |
| 3 | 证据链 Source→Claim→Judgment（提取、人工核实、冲突保留） | `evidence`（pipeline/grounding）、`candidate`、`decision` | `candidate_workspace` | app.py（extract/review/verifications） | test_06 浏览器 + 收敛 | Browser ✅（文本）/ OCR 真实链路 NOT VERIFIED |
| 4 | 人工决策与失效/重申（HumanDecision、stale、reaffirm gate） | `decision`（commands/context/lineage/shortlist） | `candidate_workspace` | app.py（decision/decision-history） | test_06/07 浏览器 + 收敛（含无当前上下文 stale 修复） | Browser ✅ |
| 5 | 面试与独立评分（排期、完成、双评委 Scorecard 不可覆盖） | `recruiting.workbench`（scorecard）、`modules.fullworkbench`（RecruitmentEvent） | `candidate_workspace` | fullworkbench（events/scorecards） | test_03/04 浏览器 + 收敛（event source 归属/修订） | Browser ✅ |
| 6 | Offer 生命周期（Draft→Approved→Sent→Accepted，不自动录用） | `recruiting.operations`（offer 状态机） | `candidate_workspace` | fullworkbench（offers/offer-status） | test_02/05 浏览器 + 收敛 | Browser ✅ |
| 7 | 联系运营与交接（Action Plan、联系队列、Brief/Handoff、CSV） | `recruiting.workbench`（action plan/contact queue）、`modules.work` | `candidate_exports`（compare/CSV，切片 4 归位） | fullworkbench（action-plan/contact-queue/brief/handoff/*.csv） | test_02/11/12 浏览器 + 收敛 | Browser ✅ |
| 8 | 质量治理（身份评审/合并、判断校准） | `identity`（service 454 行）、`calibration`、`feedback` | — | governance.py（identity-reviews/merge/calibration） | 收敛测试（identity/calibration） | Browser 部分（merge UI 有 E2E 缺口，见 §5） |
| 9 | 知识与治理（五库检索、受控 apply/rollback、建议进 Draft） | `knowledge_governance`（apply_result_as_criterion，切片 2 归位）、`knowledge_packages`（两阶段摘要激活） | — | fullworkbench（knowledge/apply）+ capability_recovery06（rollback） | test_10 浏览器 + 收敛（digest 守卫/精确回滚） | Browser ✅ |
| 10 | 招聘智能（渠道观测、市场参考、仅 advisory） | `recruitment_intelligence`（importer）、`planning` | — | capability_recovery06/07 | 收敛测试（test_06 家族） | Browser 部分（UI 存在，无专项 E2E） |
| 11 | AI/OCR/ASR（Provider 探测、隐私投影、降级） | `providers`（contracts/runtime/openai_compatible/probing，切片 1 归位）、`ai_runs`、`privacy` | — | app.py（settings）+ fullworkbench（providers/test/ai-runs/tasks） | 切片 1 单测 16 项 + 收敛 | Browser 设置页 ✅ / 真实 Provider NOT VERIFIED |
| 12 | 运行时与交付（备份/恢复/迁移、诊断、版本身份、任务引擎） | `runtime`（backup_truth/jobs/db/settings/diagnostic_bundle/portable_migration）、`release` | — | fullworkbench（backups/restore/diagnostics）+ project_portability.py | 收敛测试（backup 完整性/篡改拒绝/legacy 兼容） | Browser 部分 / Windows 备份恢复未验收 |

支撑层（非业务域）：`kernel`（clock/errors/hashing/ids——跨域原语）、`audit`（全部写操作审计）、`workspace_lease`（跨载体单写者）、`modules.fullworkbench`（BlobStore/KnowledgeService/TaskRecord 等共享设施）。

## 3. 臃肿清单（有证据的“不再臃肿”靶点）

| # | 靶点 | 证据（2026-10-21） | 处置建议 | 优先级 |
|---|---|---|---|---|
| 1 | `api/fullworkbench.py` 仍 1485 行 | 分解后余量：dashboard/events/cockpit/intake-batch/tasks/templates/contact/brief-handoff/backups/restore/diagnostics 等闭包 | 继续按域切片：events（域 5）→ cockpit/brief（域 3/4）→ backups/diagnostics（域 12）；每片配域单测 + 路由契约同步 | P1 |
| 2 | 命名混淆：`modules/fullworkbench.py` 与 `api/fullworkbench.py` 同名并存 | 249 行 vs 1485 行，职责不同（共享设施 vs HTTP 路由） | 将 `modules/fullworkbench.py` 更名 `modules/shared_facilities.py`（纯文件移动 + import 更新，清单 diff 可审） | P2 |
| 3 | `api/capability_recovery*.py` 三个文件名不副实 | 实际路由是 operations-learning/planning/intelligence/sourcing，与“恢复”无关（C08 时代命名） | 重命名为 `api/operations_routes.py` / `api/intelligence_routes.py` / `api/sourcing_routes.py` | P2 |
| 4 | 前端六代重复基建 | convergence03–08 共 44KB，每代自带 api/toast/modal/esc；`__c05*` 跨代共享全局 | 合并为一份共享模块（**BLOCKED**：需真实 Chromium 全量回归兜底，本地已有 13 场景环境，可排期） | P1（有环境后） |
| 5 | `app.js` 单文件 126KB | 276 行致密代码承载全部 UI | 按域拆分为多模块（同上，E2E 兜底后执行；`check_frontend_contract.py` 已是拆分安全网） | P1（有环境后） |
| 6 | 历史证据与现行代码混杂 | `verification/` 快照、`docs/history/`、旧收敛文档 | 保持只读不动（宪章：不覆盖历史）；仅在新文档中注明现状指针 | 不做 |

## 4. 缺口清单（“功能完整”的另一半）

| # | 缺口 | 影响 | 建议 |
|---|---|---|---|
| 1 | 身份合并 UI 无 E2E（域 8 仅有 API/收敛覆盖） | 合并是高风险人工操作，缺点击级回归 | 新增 test_14：两人选同项目→扫描→合并预览→执行→历史保留断言 |
| 2 | 备份/恢复无 UI E2E（域 12） | 恢复正确性只有 API 级证据 | 新增 test_15：UI 触发备份→下载→（合成）恢复验证 |
| 3 | 渠道观测/市场参考 UI 无 E2E（域 10） | advisory 数据入口未验证 | 排期 test_16 |
| 4 | OCR/ASR/真实 Provider 全链路 | 依赖负责人授权与真实样本 | 维持 NOT VERIFIED，不伪造 |
| 5 | Windows 双端并发（V3/T1–T10） | #43 核心 | Supervisor 设计后按 M3 推进 |

## 5. 维护规则（防止再次臃肿）

1. 新业务能力一律落在 `modules/`（逻辑）+ `surfaces/`（投影）；HTTP 层只加薄适配器——ADR-0002 红线。
2. 新路由必须同步 `docs/contracts/api-v1-inventory.txt`（CI 强制，`check_api_contract.py`）。
3. 新前端交互必须通过 `check_frontend_contract.py`（内联处理器不得引用模块作用域）。
4. 新业务场景必须落真实 Chromium E2E（本地环境已可用：D:/srw-tools venv + Playwright 1.56.0）。
5. 每个域的重大变更在本文更新一行状态；状态只用证据说话。
