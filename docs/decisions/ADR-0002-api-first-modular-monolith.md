# ADR-0002 API-first 模块化单体 Core 与薄载体边界

状态：Accepted as product/architecture direction · 2026-10-21 · 决策角色：产品负责人

关联：Issue #63、ADR-0001、#41、#42、#43。

## 1. 背景

ADR-0001 已确定 Windows WPF/WebView2 与本地 Browser/HTML 共用一个权威 SRW Core，不维护两套数据库或两套业务真相。当前 C11 已经具备明显的领域模块化基础：`backend/srw/modules/` 下存在 candidate、protocol、decision、identity、work、knowledge、planning、feedback 等模块，`runtime/`、`providers/`、`evidence/`、`surfaces/` 也已承担相对明确的职责。

但入口层正在重新形成大型聚合点。以 2026-10-21 基线 `c0bc192e346ab16aeb6fa63e60a40c617274a188` 为例：

- `backend/srw/api/fullworkbench.py` 约 126.8 KB / 1723 行，承担候选人、Offer、Interview、Knowledge、Task、Backup、Dashboard 等多个业务域的 HTTP 适配；
- `backend/srw/api/app.py` 约 38.6 KB / 737 行，同时承担 Core 组装、基础路由、静态前端和多个 route installer；
- `frontend/dist/app.js` 约 128.8 KB，页面渲染、状态、API 请求和业务交互高度集中；
- 对 `backend/srw/api/*.py` 的静态扫描得到 141 个 `Route(...)` 声明、129 个不同路径模板，API 已经成为真实产品表面，但尚未被完整视为版本化产品契约。

继续直接向这些聚合点增加功能，会使 Windows / Browser 客户端更容易复制业务判断，也会增加测试、并发控制、审计和长期维护成本。

## 2. 决定

SRW 采用 **API-first modular monolith（API-first 模块化单体）** 作为长期目标架构。

这不是创建新业务内核，也不是迁移到微服务。现有 C11 Core 继续作为唯一权威业务核心，采用渐进式 Strangler Refactoring 收紧边界：

1. **业务能力先进入 Core，再由载体消费。** Windows、Browser、未来 CLI/Agent/Automation 都不得各自实现权威招聘规则。
2. **公开接口按业务用例设计，不按内部函数设计。** `PublishProtocol`、`ReviewClaim`、`RecordHumanDecision`、`TransitionOffer` 等 operator use case 可以形成应用接口；内部 repository/helper/hash 函数不直接成为公共 API。
3. **HTTP/API 是适配层，不是业务规则层。** Route 负责请求解析、契约验证、身份/并发前置、调用 application service、错误映射和响应序列化；核心状态机与不变量仍由 Domain/Application 决定。
4. **一个 Core 进程、一个 Workspace authority、一个 SQLite authority、一个 Job Engine。** 本阶段不拆微服务、不建立数据库同步、不把每个领域模块变成独立进程。
5. **Windows 与 Browser 是薄载体。** Windows Host 重点负责 Core 生命周期、workspace lease、session、WebView2/native integration、诊断/更新；Browser 负责交互和展示。两者共享同一业务 API/contract。
6. **前端建立统一 API client 与 feature boundary。** 不在本阶段更换 React/Vue/Svelte 等框架；先在现有技术栈内拆分 `app.js`，禁止页面代码散布重复的 transport/error/concurrency 逻辑。
7. **API Contract 作为产品资产。** 对重要接口明确 request、response、error code、revision/concurrency、audit effect、side effect、权限/人类确认边界和兼容策略。
8. **行为保真优先于目录美观。** 所有模块拆分先由现有 Source/API/Chromium/Windows 证据保护；没有行为等价证明，不进行大规模文件搬迁或 Schema 重写。

## 3. 目标逻辑分层

目标是职责边界，而非要求一次 PR 立即移动所有文件：

```text
Clients / Carriers
  Windows WPF/WebView2       Local Browser       future CLI / Agent
             \                  |                  /
              +------------ SRW API ------------+
                              |
                       Application Use Cases
                              |
                           Domain
                              |
        +---------------------+----------------------+
        |                     |                      |
   Repositories/DB       Jobs/Providers        Blob/Knowledge
        |                     |                      |
        +---------------- authoritative Workspace ---+
```

建议长期职责：

- Domain：Candidate、Protocol、Source/Claim/Judgment、Decision、Interview、Offer 等不变量与状态语义；
- Application：面向操作者业务动作的用例编排、事务边界、权限/人工动作要求；
- Infrastructure：SQLite/Blob、Knowledge、Provider、OCR/ASR/AI、备份、任务执行；
- API：HTTP contract、序列化、错误、session、revision/If-Match；
- Carrier：进程生命周期、工作区、端口、会话、WebView2/浏览器启动、native integration；
- Frontend：呈现、输入、导航、客户端视图状态，不拥有权威招聘规则。

## 4. 兼容与迁移策略

采用渐进迁移，不建设 `src2`、`new-core` 或第二套产品：

- 先做 route/API inventory 与 contract tests；
- 在保持 URL、HTTP method、response/error 语义不变的情况下，将 `fullworkbench.py` 路由按业务域迁出；
- 从 route handler 中抽出可测试的 application use case；现有 domain/service/repository 优先复用；
- 前端先引入统一 API client，再按 feature 拆分渲染和动作；
- 只有在回归证明等价后才删除旧聚合代码；
- Schema 迁移、API 破坏性变更、数据权威变化继续按 G1 单独审查，不被本 ADR 自动授权。

## 5. 明确不做的方案

### 方案 A：全面重写 Core / UI
拒绝。历史 alpha 演进已经证明“架构/外观重做导致成熟业务缩水”是实际风险，并与 PRODUCT_CHARTER A4 冲突。

### 方案 B：按领域拆成多个微服务
拒绝。当前 SRW 是 local-first 产品，微服务会引入进程编排、网络失败、分布式事务、版本协调和更复杂的安装维护，无法证明收益大于成本。

### 方案 C：Windows/Web 各自实现业务逻辑，再同步数据
拒绝。违反 A6 和 ADR-0001，Decision lineage、审计与任务幂等尤其难以安全同步。

### 方案 D：立即拆多个 Git 仓库
拒绝。当前跨 Core/API/Browser/Windows 的同 SHA 回归和发布绑定更适合 monorepo。代码边界先强分离，仓库边界暂不分离。

### 方案 E：同时更换前端框架
拒绝。框架迁移与业务/API 重构叠加会显著扩大回归面；如未来确有需要，必须另行证明收益并经过产品负责人决策。

## 6. 验收原则

每个重构 PR 至少回答：

- 哪个 operator use case 的行为保持不变或变得更明确；
- 旧 URL/contract 是否保持；若变化，迁移与兼容策略是什么；
- 哪些业务规则从 UI/API handler 收回 Core；
- Source/API、Chromium、Windows、dual-carrier 哪些实际运行，哪些 NOT RUN；
- 是否改变 Schema、workspace、runtime、Knowledge、Provider 或 release identity；
- 如何回滚而不破坏用户工作区和历史 Source/Decision。

纯结构拆分不得用“代码更漂亮”作为完成标准；必须降低耦合且保留行为证据。

## 7. 后果

正向后果：

- Windows、Browser 以及未来客户端共享真正相同的业务语义；
- API 可独立测试、版本化，并成为扩展 CLI/Agent/自动化的稳定入口；
- 大型聚合文件可以渐进缩小，降低单点改动风险；
- Provider/OCR/ASR/Knowledge 等能力可通过内部接口扩展，而无需修改每个 UI；
- 双端并发/CAS、session、审计可在一个权威 Core 内解决。

代价：

- 一段时间内会存在旧聚合层和新 route/application 层并存；
- contract test 和 compatibility test 数量会增加；
- 每次迁移必须同步维护 Source Manifest 和精确验收；
- 在拆分完成前，不应仅根据目录结构宣称“架构重构完成”。

## 8. 可重新讨论条件

只有在以下情况重新讨论：

- 可重复证据表明单体 Core 在目标本地负载下无法满足性能、可靠性或隔离需求；
- 产品边界改变为远程多租户 SaaS，并由负责人明确批准；
- 现有前端技术栈出现无法通过渐进拆分解决的维护/安全阻断，并有完整替代迁移证据。
