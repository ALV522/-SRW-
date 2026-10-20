# SRW 项目总述与事实基线

状态：G1 产品/架构基线 · 2026-10-21。本文说明“SRW 是什么、当前真实状态是什么、以后按什么结构发展”；动态 PASS 仍以准确 Git SHA、CI 和工件证据为准。

## 1. 产品目的

SRW（Smart Recruitment Workbench）是一个 **local-first、evidence-centered、AI-assisted** 的招聘执行工作台，面向独立 Recruiter、小型招聘执行团队或专职招聘人员。

它要完成的不是“让 AI 替人决定”，而是把招聘业务放进一个有版本、有来源、有人工边界、可恢复的本地系统：

**岗位/Criteria → 候选人收件 → Source/MaterialRevision → Claim/人工核实 → Interview/Scorecard → HumanDecision → Offer → 联系/交接 → 上下文变化后的失效/复核/重申 → 备份恢复。**

同时保留 Knowledge、身份复核、任务、AI Provider、OCR/ASR、项目导入导出、诊断与回滚能力。

## 2. 历史与能力保真

历史 `v0.8.12-R2` 是成熟业务能力对照，不是当前 C11 源码或正式发行物。过去曾出现架构/UI 重构后成熟功能缩水，因此 G1 明确要求：任何重构都必须保留 Source/Claim/Judgment/Decision、Interview、Offer、Follow-up、Knowledge、AI/OCR/ASR、Backup/Restore 和 provenance 的实际价值。

当前不建设全新业务内核、不用 UI 简化交换功能缩水、不把历史 725 项测试当作当前 PASS。

## 3. 当前事实基线

当前核查基线为 `main`：`c0bc192e346ab16aeb6fa63e60a40c617274a188`。

- VERSION：`1.0.0-alpha10-convergence11`（旧格式，development）；
- Schema：`v1_0014`；
- Source Gate：Ubuntu / Windows Python 3.12 各 241 tests、2 skipped、PASS；
- Chromium：10 条真实浏览器 + C11 API + 临时合成 SQLite 场景 PASS；
- Source integrity：329 条 SHA-256 entries PASS；
- Windows Host rebuild 与 offline wheelhouse 在该 SHA 构建门禁成功；
- 这些源码/构建结论**不证明**当前 SHA 的完整 Windows Native GUI、完整业务、Provider/生产 Knowledge 或 EXE+Browser 双端正式并发已经验收。

历史 `d8d032d` 等特定候选的 Windows GUI/后端实机证据继续保留，但不得转移为新 main 的 PASS。

## 4. 当前架构判断

SRW 不是“完全未分层的巨石”。当前仓库已经出现：

- `backend/srw/modules/`：candidate、protocol、decision、identity、work、knowledge、planning、feedback 等领域/服务模块；
- `backend/srw/runtime/`：数据库、Schema、Jobs、Backup、local boundary；
- `backend/srw/providers/`：Provider contract/runtime；
- `backend/srw/surfaces/`：业务读模型/workspace；
- `frontend/dist/`：Browser/WebView2 客户端；
- `desktop/SRW.Desktop/`：WPF/WebView2 Windows Host。

主要问题是入口层重新聚合：当前 `fullworkbench.py` 约 126.8 KB/1723 行，`app.js` 约 128.8 KB；静态扫描 API 模块有 141 个 Route 声明、129 个不同路径模板。继续直接叠加功能会增加跨端业务规则漂移和回归成本。

因此产品负责人已批准 [ADR-0002](decisions/ADR-0002-api-first-modular-monolith.md)：在 ADR-0001“一个权威 Core”之上，将 SRW 转向 **API-first modular monolith**。

## 5. 目标架构

```text
Windows WPF/WebView2       Local Browser       future CLI / Agent
          \                    |                    /
           +--------------- SRW API ---------------+
                              |
                     Application Use Cases
                              |
                           Domain
                              |
       +----------------------+----------------------+
       |                      |                      |
 SQLite / Blob          Jobs / Providers        Knowledge
       |                      |                      |
       +-------------- authoritative Workspace -----+
```

核心含义：

1. Core 才是业务权威，前端/载体只消费接口；
2. API 对应 operator use case，而不是内部 helper；
3. Route 薄化，业务规则进入 Domain/Application；
4. Windows Host 收敛到 lifecycle/workspace/session/WebView2/native integration；
5. Browser 使用同一 API/业务语义；
6. 单一 Core、单一 Workspace authority、单一 SQLite writer、单一 Job Engine；
7. 前端先统一 API client，再渐进 feature 拆分；
8. 不拆微服务、不拆多仓库、不同时更换前端框架。

完整实施路径见 [API_FIRST_MODULAR_CORE_ROADMAP.md](API_FIRST_MODULAR_CORE_ROADMAP.md)。

## 6. 当前主要阻断点

### 业务/正确性

继续完成 #41 的 V1/V2：完整招聘纵向业务与异常链，特别是 Evidence/Decision lineage、面试修订、Offer、人类边界、恢复与真实文件处理。

### Windows 产品化

#42 需要当前准确 SHA 的完整 Native 工件和目标 Windows 实机验收：启动/重启、业务、OCR/ASR/Provider、Backup/Restore、升级/回滚和长期运行。

### 双载体

#43 需要把探索中的 Core owner/CAS/session 设计正式化：Supervisor、attach/revoke、Origin/CSRF、事务 revision、单 Job Engine、EXE+Browser 同机交叉读写。

### 架构债务

#63 需要逐步建立 API inventory/contract，拆 `fullworkbench.py` 和 `app.js`，形成 Application use cases。该工作必须与业务产品化并行，不能停工半年做 rewrite。

### 版本/发行

#44 和 RELEASE_PROCESS 继续独立管理版本迁移与发布身份。架构文档不自动启用 `1.0.0-alpha.11`。

## 7. 开发原则

后续新增或修复默认顺序：

```text
operator outcome
→ Domain invariant
→ Application use case
→ API contract
→ Browser / Windows client
→ exact carrier acceptance
```

如果发现某个 UI 已包含独立业务规则，应优先把权威判断收回 Core；前端可以做提示和禁用，但服务器必须重新校验。

所有重构采用 Strangler Refactoring：先建立行为安全网，再逐域迁移；URL/Schema 默认保持；等价验证后才删除旧聚合代码。

## 8. 权威文档

- `AGENTS.md`：强制协作入口；
- `PRODUCT_CHARTER.md`：A/B/C 产品不变量与授权；
- `CAPABILITY_MATRIX.md`：业务能力和验收边界；
- `ADR-0001`：一个权威 Core；
- `ADR-0002`：API-first 模块化单体；
- `API_FIRST_MODULAR_CORE_ROADMAP.md`：专项架构路线；
- `ROADMAP.md`：总体产品路线；
- `DUAL_CARRIER_PLAN.md`：Windows/Browser 正式统一 Core；
- `ACCEPTANCE_PLAN.md`：业务/工件验收；
- `VERSION_POLICY.md`：版本、Schema、SHA、carrier、channel；
- `DEVELOPMENT_GOVERNANCE.md`：Issue/PR/证据制度；
- `RELEASE_PROCESS.md`：发布和回滚。

**事实 ≠ 规划 ≠ 代码存在 ≠ 验收 PASS。** 所有状态报告继续严格区分。
