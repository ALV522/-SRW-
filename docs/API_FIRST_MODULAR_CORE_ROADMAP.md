# SRW API-first 模块化 Core 重构路线图

状态：ACTIVE ARCHITECTURE ROADMAP · Issue #63 · 2026-10-21

本路线图实现 ADR-0002，并服从 PRODUCT_CHARTER、ADR-0001、CAPABILITY_MATRIX、#41/#42/#43。它是**渐进式重构计划**，不是另起一套 SRW，也不改变当前产品 VERSION、Schema 或发行状态。

## 1. 为什么现在开始

SRW 已经具备较丰富的招聘业务和真实测试，但当前代码增长方式开始出现结构性风险。基线 `c0bc192e346ab16aeb6fa63e60a40c617274a188` 的静态仓库审计如下：

| 区域 | 基线规模/观察 | 结论 |
|---|---|---|
| `backend/srw/` | 127 个文件，约 596 KB | 已有模块化 Core 基础，不应重写 |
| `backend/srw/modules/` | 17 个业务模块目录 | 领域边界已有雏形，应继续收口 |
| `backend/srw/api/*.py` | 141 个 Route 声明、129 个不同路径模板 | API 已是产品表面，需要正式 contract 治理 |
| `backend/srw/api/fullworkbench.py` | 约 126.8 KB / 1723 行 | 最大后端聚合热点，优先渐进拆分 |
| `backend/srw/api/app.py` | 约 38.6 KB / 737 行 | Core composition + 基础路由仍偏重 |
| `frontend/dist/` | 9 个文件，约 189 KB | 当前前端可继续复用，不换框架 |
| `frontend/dist/app.js` | 约 128.8 KB；大量页面/API 调用集中 | 最大客户端聚合热点，需统一 API client + feature 拆分 |
| `desktop/SRW.Desktop/` | 20 个文件，约 43 KB | 适合继续收敛为薄 Host/Carrier |
| `convergence_tests/` | 37 个文件，约 265 KB | 是安全渐进重构的关键资产 |
| `browser_acceptance/` | 真实 Chromium 操作链 | 用于证明前端拆分没有丢业务 |

这说明问题不是“缺少模块”，而是**已有模块没有被入口层和客户端严格尊重**。因此本轮目标是边界收口，不是新核心重写。

## 2. 最终工程模型

### 2.1 核心规则

任何新功能默认按以下顺序进入产品：

```text
业务需求 / operator outcome
        ↓
Domain invariant / state rule
        ↓
Application use case + transaction
        ↓
Versioned API contract
        ↓
Windows / Browser / future client
        ↓
Carrier-specific acceptance
```

禁止反向开发：先在某个 UI 塞业务判断，再事后尝试同步到另一端。

### 2.2 六个职责边界

**Domain**：定义“什么是合法业务状态”。例如 Decision stale、Offer 合法迁移、Source/Claim/Judgment lineage、人工决定边界。

**Application**：定义“操作者能完成什么业务动作”。例如 PublishProtocol、ReviewClaim、ScheduleInterview、SubmitScorecard、RecordHumanDecision、ReaffirmDecision、TransitionOffer、RestoreBackup。

**Infrastructure**：数据库、Blob、Knowledge、Provider、OCR/ASR/AI、Job Engine、Backup/Restore 的具体实现。

**API**：对外合同。负责 request/response、error code、session、revision、并发和 transport，不重新判断业务真相。

**Carrier**：Windows Host / Local Web launcher / future supervisor。负责进程和本地系统集成，不直接实施 Candidate/Decision/Offer 规则。

**Frontend**：展示与输入。可以做交互前置提示，但服务器/Core 必须独立重新校验所有权威操作。

## 3. API Contract 标准

每个重要写接口逐步形成可测试 contract，至少记录：

| 字段 | 要求 |
|---|---|
| Use case | 操作者想完成的业务动作，而不是内部函数名 |
| Request | 必填/可选字段、类型、输入限制 |
| Response | 稳定字段、资源身份、最新 revision/context |
| Errors | 400/404/409/412/422/5xx 等明确业务含义 |
| Concurrency | revision / If-Match / expected version / 幂等规则 |
| Human boundary | 是否必须明确人工 actor/确认 |
| Audit | 成功/失败是否写审计，写什么 lineage |
| Side effects | 是否创建 Source、MaterialRevision、Job、Backup 等 |
| Security | session/origin/local boundary/敏感数据处理 |
| Compatibility | 是否保持现有 URL；弃用窗口与迁移方式 |

**原则：前端可隐藏非法按钮，但不能成为唯一业务门禁。**

## 4. 渐进实施阶段

### R0 · 架构基线与治理（本 Issue 首轮）

交付：

- ADR-0002；
- 本专项路线图；
- 根 README、总 ROADMAP、ARCHITECTURE、PROJECT_OVERVIEW 与双载体计划对齐；
- 明确当前聚合热点和禁止事项；
- 不改变 Schema、Runtime、Knowledge、API 行为。

退出条件：同 PR Head 的 Governance、Source Gate、Chromium 成功；文档不得暗示 Windows/dual-carrier 新 PASS。

### R1 · API inventory 与 contract safety net

目标：先知道“现在对外承诺了什么”，再搬代码。

任务：

1. 自动生成或测试维护 API route inventory：method + path + owning module；
2. 将关键业务写入口映射到 operator use case 和产品不变量；
3. 建立 common error envelope/错误码契约的回归；
4. 标出所有 mutation 是否有 revision/CAS、audit 和 human actor；
5. 建立 frontend→API 使用矩阵，识别 UI 直接编码的业务规则；
6. 对现有 `/api/v1` URL 冻结兼容基线，不因文件拆分改变路径。

优先业务域：Decision/Evidence → Interview/Offer → Candidate/Protocol → Operations/Knowledge → System/Backup。

退出条件：主要 `/api/v1` 路由都能定位到 owner/use case；后续 route move 可以通过 contract test 证明 URL/方法/错误语义不变。

**R1 进度（2026-10-21）**：已交付 `scripts/api_inventory.py`、`verification/api_contract/inventory.json`（146 条 method+path，其中 73 条写操作）、`verification/api_contract/errors.json`、`convergence_tests/test_api_contract.py` 与生成文档 `docs/API_INVENTORY.md`。

已完成：route → 归属模块（取自运行中端点的 `__module__`，非文本匹配）→ 业务域归属；`/api/v1` 路径冻结（增删路由会使 contract test 失败）；前端 104 个 `/api/v1` 字面量与路由的对账（全部可解析）；错误封套现状记录。

仍属 R2：逐路由的 operator use case 映射，以及 concurrency/audit/human-actor 的**语义**归类。当前 `mutations.json` 只提供 73 条“不得增长”棘轮，`inventory.json` 里的三个 signal 列是端点源码静态标记，不代表不变量已被验证。

已知缺口（本轮未改行为）：404/405 仍返回纯文本，未使用 `{"detail", "error": {"code"}}` 封套，已在 `errors.json` 显式记录而不是隐藏。

### R2 · 后端 Route Decomposition

目标：让 `fullworkbench.py` 从“多领域控制器”变成逐步淘汰的兼容聚合层。

建议目标结构（可以逐步形成，不要求一次迁目录）：

```text
backend/srw/api/
  app.py                 # composition root
  errors.py              # transport error mapping
  contracts/             # request/response schemas/contracts
  routes/
    projects.py
    candidates.py
    evidence.py
    interviews.py
    decisions.py
    offers.py
    operations.py
    knowledge.py
    providers.py
    jobs.py
    system.py
```

迁移规则：

- 一次只迁一个业务域；
- route path/method 默认保持；
- handler 缩减为 transport adapter；
- 不把 repository/sql 查询复制到新 route；
- 每次迁移先跑该域 Source/API 回归，再跑适用 Chromium；
- 旧 `fullworkbench.py` 只删除已经完全迁出且有回归保护的内容。

退出条件：新增功能不再默认进入 `fullworkbench.py`；文件规模持续下降，且不存在第二套业务实现。

**R2 进度（2026-10-21，第一刀）**：`offers` 域（3 条路由 / 2 条写操作）已迁出到 `backend/srw/api/routes/offers.py`，`install_full_workbench_routes` 改为 `*offer_routes(factory=factory)` 装配。同批把 `_s`/`_json_body`/`_body_dict` 三个纯传输助手移入 `backend/srw/api/http_utils.py`，避免新 route 模块反向依赖聚合层而形成循环导入。URL、方法、响应体、错误码与事务边界均保持不变，由 `convergence_tests/test_offer_routes.py`（5 项）与冻结清单共同证明。

本刀同时暴露两处**已记录未修改**的契约问题：创建 Offer 时缺少必填字段返回 `409 invariant_conflict`，而项目创建同类错误返回 `422 invalid_request`；Offer 状态迁移没有 `If-Match`/expected revision，属 last-write-wins。两者都要单独决策后才能改，不随搬迁顺手变更。

**R2 进度（2026-10-21，第二刀）**：`interviews` 域（5 条路由 / 3 条写操作）迁出到 `backend/srw/api/routes/interviews.py`，含 `events`、`add_event`、`update_event`、`event_scorecards` 与三个事件助手（`parse_iso`/`event_metadata`/`event_source_text`）。

同时把 `_publish_current` 提升为 `backend/srw/api/shared.py` 的 `publish_current_revision`：它被 intake、事件创建、事件修订与异步任务四处调用，留在聚合层会让新模块无法独立。**Issue #41 的 Source 修订语义（新 Source 标记 `supersedes_source_id`、旧 Source 与旧 MaterialRevision 保持不可变、相同文本幂等不发布）逐字保留**，由 `test_interview_routes.py`（6 项）与既有 `test_event_source_revision.py` 双重覆盖。

`fullworkbench.py` 1690 → 1530 行；累计从 1723 降至 1530（−193）。写操作归类 5/73，棘轮基线 73 → 68。同一轮记录的新事实：`PATCH /events/{id}` 与 `POST /events/{id}/scorecards` 均无 `If-Match`；评分卡用"提交后锁定"代替版本令牌。

**R2 进度（2026-10-22，第三刀）**：`tasks`（4 条）与 `templates`（6 条）共 10 条路由迁出到 `backend/srw/api/routes/operations.py`，`_latest_draft` 提升为 `api/shared.py::latest_draft`（`knowledge_apply` 仍在聚合层使用）。

**`GET /api/v1/dashboard` 刻意不随本次迁出**：该处理器 284 行，聚合项目/候选人/Claim/Offer/面试/联系六类数据，属读模型而非传输适配；放进 route 模块会把一个聚合热点换成另一个。它保留在聚合层，`inventory.json` 继续如实记录其 owner，待读模型切片单独处理。

`fullworkbench.py` 1530 → **1387 行**；累计从 1723 降至 1387（−336）。写操作归类 12/73，棘轮 68 → 61。本轮记录：任务 cancel/retry 与模板增删改**均不写审计**，且无 `If-Match`；cancel 对已成功任务是"如实返回 no-op"而不是拒绝。

**R2 进度（2026-10-22，第四刀）**：`system` 域 7 条路由（备份创建/列表/下载、恢复排期、恢复取消、诊断、诊断导出）迁出到 `backend/srw/api/routes/system.py`，builder 显式接收 `data_dir`/`knowledge_dir`/`database_path`/`frontend_dist` 四个工作区依赖，而不是继续闭包捕获。同步清理聚合层 6 条失效导入。

这批路由与 **#42 的恢复验收**直接相关：排期只校验归档清单并写 `pending_restore.json`，真正恢复发生在启动时、SQLite 打开之前，因此 route 层永不触碰在线数据。这一点写进了模块文档，避免以后有人把"排期成功"误读为"恢复已完成"。

`fullworkbench.py` 1387 → **1346 行**；累计从 1723 降至 1346（−377，−21.9%）。写操作归类 15/73，棘轮 61 → 58。浏览器套件的时序 flake 已记入 `docs/BROWSER_ACCEPTANCE.md`，稳定化另开 PR。

**R2 进度（2026-10-22，第五刀）**：`providers` 域 3 条路由（配置读取 / 更新 / 探测）迁出到 `backend/srw/api/routes/providers.py`。三个 provider 助手（`profile_view` / `api_key_name` / `probe_provider`）与 `httpx` 加载器移入新的 `backend/srw/api/provider_support.py`——它们同时被留在聚合层的 OCR/ASR 字节处理使用，放进 route 模块必然循环依赖。

本轮同时补上一条**安全回归**：`test_provider_routes.py` 断言 `/api/v1/settings/providers` 的序列化响应里不出现原始 API key，连前 8 位也不允许出现，并覆盖"探测失败不得回显密钥"。此前只有诊断包层面的脱敏断言，没有 API 层的。

`fullworkbench.py` 1346 → **1311 行**；累计从 1723 降至 1311（−412，−23.9%）。写操作归类 17/73，棘轮 58 → 56。搬移中发现并修正一处自我引入的偏差：清理 `_probe` 时因位置在 `_task_begin` 之后而漏删，导致模块级定义遮蔽同名导入别名——已删除并验证 `_probe.__module__` 指向新模块。

**R2 进度（2026-10-22，第六刀）**：`decisions` 域的重评估三件套（草稿列表 / 创建 / 应用）迁出到 `backend/srw/api/routes/decisions.py`，`_judgment_payload` 随域迁移。

本轮先评估了 `knowledge` 的"跨模块归并"，结论是**不做**：那 15 条路由分布在 `capability_recovery*.py` 三个共 261 行、本身已按域组织的模块里，按分类桶硬拆会制造错误边界并复制共享助手。判断依据写入了 PR，避免以后有人重复评估。

`fullworkbench.py` 1311 → **1217 行**；累计从 1723 降至 1217（−506，−29.4%）。写操作归类 19/73，棘轮 56 → 54。新增 `test_reevaluation_routes.py`（5 项），首次为重评估补上真实 HTTP happy path + stale 拒绝，此前只有 dashboard 计数间接覆盖。

### R3 · Application Use-case Layer

目标：把“一个用户动作需要串联多个模块”的逻辑从 route/UI 中提取到应用层。

候选 use case：

- CreateProject / PublishProtocol；
- IntakeCandidate / PublishMaterialRevision；
- ReviewClaim / VerifyCriterion；
- ScheduleInterview / CompleteInterview / SubmitScorecard；
- RecordHumanDecision / ReaffirmDecision；
- CreateOffer / TransitionOffer；
- PlanContact / HandoffProject；
- CreateBackup / ScheduleRestore；
- SubmitEvidenceExtractionJob。

Application 层负责事务边界、调用 Domain、写审计/lineage 和 orchestration；不能吞掉 Domain invariant。

退出条件：重要 mutation 可以在不启动 Web UI 的情况下直接通过 use-case test 验证，route 主要做输入输出适配。

### R4 · Frontend API Client + Feature Decomposition

目标：缩小 `frontend/dist/app.js`，但不借机更换框架或重新设计整套 UI。

建议演进：

```text
frontend/dist/
  core/
    api.js
    router.js
    state.js
    errors.js
  features/
    dashboard/
    projects/
    candidates/
    evidence/
    interviews/
    decisions/
    offers/
    knowledge/
    settings/
  app.js
```

首要动作：

1. 所有 HTTP 访问经过统一 API client；
2. transport error/session/revision handling 只实现一次；
3. feature module 不直接知道 SQLite/Provider 实现；
4. 同一业务门禁由 API 返回 authoritative state，前端只负责呈现；
5. 保留现有 DOM/UI 行为，使用 Chromium E2E 证明功能没有缩水。

退出条件：新增前端功能不再继续扩大单体 `app.js`；关键 feature 可独立定位和测试。

### R5 · Core Supervisor / Session / CAS 与双载体正式化

此阶段与 #43 合流。

目标：Windows 和 Browser 真正成为同一个 Core 的并列客户端，而不是各自启动写入 Core。

需要：

- 单一 Core owner / Supervisor；
- workspace lease 与生命周期协议；
- session attach/revoke；
- Origin/CSRF/local authorization；
- revision/If-Match/CAS；
- 一个 Job Engine；
- backup/restore/Schema migration 时写入互锁；
- Windows + Chromium 同机交叉读写测试。

退出条件遵循 DUAL_CARRIER_PLAN V3/T1–T10；E1–E5 探索不能替代正式验收。

### R6 · Carrier Thinness 与正式包装

Windows Host 只保留：Core lifecycle、workspace/session、WebView2、native file/dialog integration、更新/诊断等 carrier 责任。Local Web launcher 只负责安全启动/附着同一 Core 和浏览器。

两端共享产品版本/API/Schema，但分别记录 carrier 工件 SHA 与验收。

### R7 · 可扩展能力接口（在核心稳定之后）

优先采用**代码级 capability/provider abstraction**：

- TextAIProvider；
- OCRProvider；
- ASRProvider；
- Embedding/Knowledge provider；
- Document parser；
- Export/automation adapter。

本阶段不做动态第三方插件 marketplace，不允许插件绕过审计、隐私、Decision human boundary 或 workspace authority。

## 5. 与现有 P0/P1 工作的关系

架构重构不是暂停产品化的理由：

- #41 继续关闭业务真实性/功能保真缺口；每个修复优先落在正确 Core/Application 边界；
- #42 继续 Windows Native 产品化；不要等待全部模块拆完；
- #43 继续共享 Core/双端安全；R5 与其直接共用验收；
- #44 版本迁移独立进行，不因架构文档改变当前 VERSION。

原则是 **边修业务、边收口边界**，而不是“先停工半年重构，再恢复业务开发”。

## 6. 禁止事项

在当前阶段明确禁止：

- 新建第二套 `new-core` / `src2` 并逐步重写全部业务；
- 微服务、容器编排、消息总线作为默认架构；
- Windows 与 Web 分别直接写 SQLite；
- 为架构拆分改变 HumanDecision、Evidence lineage 等 A 类语义；
- 同时更换前端框架；
- 为目录整洁做大规模 Schema rewrite；
- 拆成多个 Git repository；
- 把内部 helper 机械映射成大量公共 HTTP endpoint；
- 先删旧能力、以后再补 parity 测试。

## 7. 每个重构 PR 的最小验收模板

1. Base main SHA；
2. 迁移的 operator use case；
3. before/after route/API contract；
4. 业务不变量；
5. Schema/Runtime/Knowledge 是否变化；
6. Source/API tests；
7. Chromium E2E（适用时）；
8. Windows WPF（仅受影响且有真实工件时）；
9. dual-carrier（仅 R5+）；
10. rollback；
11. SOURCE_MANIFEST diff 解释。

## 8. 何时认为“重构完成”

不是以文件数量或目录名称判断。至少需要满足：

- 主要业务 mutation 都有明确 application use case；
- API route owner/contract 可追踪；
- `fullworkbench.py` 不再是新增功能默认落点；
- `app.js` 不再承载全部 feature + transport；
- Windows/Browser 均不复制权威业务规则；
- Core 是唯一 Workspace/DB/Job authority；
- API compatibility/concurrency/audit 有自动化验证；
- v0.8.12-R2 关键能力没有因重构缩水；
- Windows 与 Browser 最终通过各自及共享 Core 的真实验收。
