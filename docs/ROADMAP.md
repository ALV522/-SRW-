# SRW 产品与架构总路线图

状态：ACTIVE · 2026-10-29 进度复核（目标与退出条件不变）

本路线图以 [PRODUCT_CHARTER](PRODUCT_CHARTER.md)、[ADR-0001](decisions/ADR-0001-single-authoritative-core.md) 和 [ADR-0002](decisions/ADR-0002-api-first-modular-monolith.md) 为约束。当前开发主线是 `main`；历史 v0.8.12-R2 是功能保真对照，不是当前源码身份。

## 1. 总目标

把 SRW 从功能丰富但入口层逐渐臃肿的 C11 原型，演进为一个可以真实交付、可恢复、可验证、可长期扩展的本地招聘产品：

- 一个权威 SRW Core；
- Windows WPF/WebView2 与 Local Browser 两个正式入口；
- API-first 的模块化单体；
- 完整招聘业务闭环和证据/人工决策保真；
- 可重复 Windows/Browser/双端验收；
- 清楚的版本、Schema、源码和工件身份；
- 不通过大重写牺牲 v0.8.x 已成熟能力。

## 2. 当前基线与证据边界

当前进度快照对应 main `979863218c7fbcfc2c3fd5ff041237f0110c4350`，VERSION `1.0.0-alpha10-convergence11`、Schema `v1_0014`、development。准确 CI、工件链接与未验收边界集中见 [README 当前进展](../README.md#当前进展与路线图位置2026-10-29-核查快照)，避免在多份文档重复维护测试计数。

**当前位置：Track 0 持续业务/恢复收口；Track A 的契约与路由拆分已有多批交付、前端共享 client 和两个 feature 已拆出，Application 层尚未整体完成；Track B 最新 Native 实机验收待完成；Track C 已有纯策略与 registry，但 HTTP/Host/Browser 安全接线未完成；Track D 尚未进入 RC/GA。**

历史特定工件的 WPF/业务验收保留，不迁移为当前 SHA 的 PASS。Source+Host NO_RUNTIME kit 是装配输入，不是可直接运行的完整 Native 产品。源码与合成测试完成不等于 T1–T10 双端实测完成。

## 3. 不再采用“P0 做完后才重构”的顺序

旧路线把大型 workbench/frontend 拆分放在较晚阶段。现在改为：**业务闭环、Windows 产品化、双载体和 API-first 边界收口并行推进。**

原因是新增功能如果继续进入巨型 route/frontend 聚合层，会不断增加之后的迁移成本；但反过来，也不能为了重构暂停业务验收。因此采用“小 PR、行为保真、边开发边收口”的方式。

## 4. Track 0 · 产品不变量与业务完整性（#41，最高优先级）

持续验证并关闭：

- Job/Criteria Draft 与显式发布；
- Candidate Intake、MaterialRevision、Source provenance；
- Claim review、criterion verification、冲突/缺失证据；
- Interview、独立 Scorecard、面试证据修订；
- HumanDecision、Decision Context、stale/reaffirm；
- Offer 合法状态迁移且不自动 hired；
- 联系、Action Plan、handoff；
- Archive/restore、Backup/restore；
- Knowledge、Provider、OCR/ASR 的真实降级和边界。

退出条件不是“API 已存在”，而是 Capability Matrix 对核心流程具备可复现 Source/API、Browser 和需要的 Windows 证据；未实测保持 NOT VERIFIED/BLOCKED。

## 5. Track A · API-first 模块化 Core（#63，从现在开始）

这是横向工程约束，不是另起一个版本。

### A0 架构治理

ADR-0002、专项路线图、README/ROADMAP/ARCHITECTURE 对齐。

### A1 API inventory / contract safety net

建立 method/path/owner/use-case 清单；对关键 mutation 明确 request、response、errors、revision/CAS、human boundary、audit 和 side effects。

### A2 后端 route decomposition

按业务域渐进拆 `backend/srw/api/fullworkbench.py`，默认保留 URL/方法/错误语义；`app.py` 收敛为 composition root。禁止复制 service/repository 逻辑到新 route。

### A3 Application use cases

为跨模块业务动作建立可直接测试的应用层事务边界，使 route 变薄；Domain invariant 仍保留在核心模型/服务。

### A4 Frontend decomposition

先统一 API client，再按 dashboard/projects/candidates/evidence/interviews/decision/offers/knowledge/settings 拆 feature。保留当前技术栈，不同时换框架。

### A5 Extensibility

AI/OCR/ASR/Knowledge/Parser/Export 等通过代码级 capability/provider abstraction 扩展。动态第三方插件系统不是当前目标。

完整退出标准见 [API_FIRST_MODULAR_CORE_ROADMAP.md](API_FIRST_MODULAR_CORE_ROADMAP.md)。

## 6. Track B · Windows Native 产品化（#42）

继续独立推进，不等待 Track A 完成：

1. 当前准确源码 SHA 的 Runtime/Knowledge/Host/Source 绑定；
2. 候选 ZIP 完整成员和 SHA 审计；
3. 真实 Windows 冷启动、重启、WebView2、后端就绪、关闭/锁释放；
4. 完整招聘主链点击操作；
5. PDF/OCR、ASR、Provider 故障/降级；
6. Backup/restore、升级、回滚和故障恢复；
7. 工件 SHA、测试机器、日志证据与 known issues 固化。

退出条件：一个**具体准确工件**在目标 Windows 上重复通过规定业务与恢复验收，才进入 RC 讨论。

## 7. Track C · 一个 Core、两个正式载体（#43）

此 Track 与 Track A 的 Application/API 边界直接耦合，但不另建 Web Core。

已经完成/正在形成的基础：共享 workspace lease、Local Web 真实 C11 API、WPF Host、探索 E1–E5 的 CAS/Core owner/session 设计输入。

仍需：

- 独立 Core Supervisor；
- Windows/Browser attach/revoke；
- Origin/CSRF/local authorization；
- 事务 revision/If-Match/CAS；
- 单一 Job Engine；
- backup/restore/migration 写入互锁；
- Core 重启和客户端重连；
- 同一真实 Windows 机器 EXE + Chromium 交叉读写。

退出条件：DUAL_CARRIER_PLAN T1–T10 真实通过，而不是仅有探索分支 PASS。

## 8. Track D · 版本、发行与维护（#44 + Release）

- 当前旧格式 VERSION 不因文档/架构重构自动升级；
- 产品 SemVer、Git SHA、Schema、carrier、artifact SHA、release channel 独立记录；
- Source ZIP、Host-only、Prepared Native、Native Candidate、Local Web、RC、GA 分开；
- 下一产品版本迁移必须原子更新 release truth 文件并重新验收；
- 正式 RC 要求 P0=0、功能冻结、两载体各自达到规定门禁，负责人明确批准。

## 9. 跨 Track 的工程规则

### 9.1 新功能默认落点

```text
operator outcome
→ Domain/Application
→ API contract
→ frontend/client
→ carrier acceptance
```

不得先把业务规则写死在某一前端。

### 9.2 重构方式

- Strangler Refactoring；
- 小业务域、小 PR；
- 先测试再迁移；
- URL/Schema 默认不变；
- 新旧代码短期并存可以接受；
- 行为等价证明后再删除旧聚合代码。

### 9.3 明确禁止

当前不开展：

- `new-core` / `src2` 全面重写；
- 微服务/消息总线/容器编排；
- 两套 SQLite 同步；
- 前端框架大迁移；
- 多仓库拆分；
- SaaS、云登录、多租户；
- 因架构拆分删除成熟 Evidence/Decision/Knowledge/AI/OCR/ASR/Backup 能力。

## 10. 当前执行顺序（2026-10-29）

1. **#42/#123/#124：准确工件的 Windows 验收与可恢复性。** 最新 Source+Host kit 已构建，下一步是保留受限原 Prepared ZIP、装配新完整候选并做真实 WPF/招聘/恢复验证；外部独立副本、干净重建和 Knowledge 许可未完成。
2. **#43：从纯组件进入跨载体安全接线。** #145/#158/#165 已交付 policy/registry 与输入边界；先确认 Host 身份、Browser attach/CSRF、重复原始 header、生命周期 token 分离合同，再把 #148 的 HTTP RED 合同与实现原子推进。现有 gate 默认 OFF；不另造第二 Core。
3. **#41/#63：在真实业务缺口上继续应用层与 feature 收口。** API inventory、多轮 route 拆分、共享 API client、重评估和建岗 feature 已有交付，不再把“第一刀路由/第一个 feature”列成未来任务。R3/R4 未整体完成；保持现有技术栈与功能保真。
4. **#154/#159：保留时序故障的诊断与关闭条件。** #156/#164 已改善失败信息；不因重跑成功关闭未知根因。
5. **#166：清单工具的小范围改进。** 增量写入与 Windows/index 字节一致性，继续全量验 SHA；正式七域权威迁移暂不实施，不占用 P0/P1 产品化关键路径。

以上按风险和可用证据并行推进；不以目录、PR 数或治理文档数量作为产品完成度。版本迁移 #44 和 RC/GA 仍须独立门禁及负责人裁决。

## 11. 最终 1.0.0 判定

1.0.0 不是“重构完成”的别名。至少要求：

- 核心招聘业务与关键异常路径真实可完成；
- Windows 与 Local Web 有各自可发布工件和明确安装/恢复说明；
- 同一 Core 的双端一致性、安全、并发和任务所有权有实测；
- Evidence/Decision/Offer/AI/OCR/ASR/Knowledge/Backup 等能力达到已声明范围；
- API/Schema/版本和工件身份可追溯；
- P0 为 0，重大 P1 有明确处理或发布阻断；
- 产品负责人批准 RC/GA。
