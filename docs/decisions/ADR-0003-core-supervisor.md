# ADR-0003 Core Supervisor：双载体共用 Core 的进程、会话与事务设计

状态：Proposed（设计稿，待负责人批准后实施）· 2026-10-21 · 决策角色：产品负责人
关联：Issue #43、DUAL_CARRIER_PLAN M3、ADR-0001、ADR-0002、工作区租约合同

## 问题

当前一个工作区同时只允许一个权威写入者：先启动的载体持有 `data/app.lock` 租约并在进程内运行 Core（API+SQLite+JobEngine），另一个载体被拒绝。这是**互斥**，不是 M3 要求的**共存**。DUAL_CARRIER_PLAN D1–D8 与验收场景 T1–T10 要求：同一权威 Core 同时服务 WPF 与 Browser 两个载体、单写者、单 Job 调度器、冲突明确拒绝、关闭任一 UI 不误杀另一个。

现状存量（可复用）：双端对称的原子 `app.lock` 租约（Python `os.mkdir` / C# `CreateDirectoryW`，fail-closed 规则 + stale 双重确认恢复）；`JobEngine` 已有 worker 租约（`lease_next`/`lease_token`/`is_owned`）；Host 模式已有 `X-SRW-Session` 生命周期令牌检查；E3（事务级 CAS）与 E5（一次性附着）探索已验证可行性（合成数据，非生产结论）。

## 决定（设计）

### S1 Supervisor 进程模型：按需分离 + 引用计数生命周期

- 新增 `srw supervisor` 运行模式：**Supervisor 是唯一持有工作区租约的进程**（`app.lock/instance.json` 的 `edition="supervisor"`），独占运行 Core：HTTP API、SQLite、Job Engine、Blob/Knowledge。
- 载体（WPF Host、本地 Browser 启动器）退化为**附着客户端**：启动时先探测 Supervisor 租约；存在且健康 → 附着（S3）；不存在 → 由首个载体**派生分离的 Supervisor 进程**（非子进程，脱离载体生命周期），自身转为附着。
- Supervisor 生命周期 = 附着引用计数：最后一个载体 detach 后进入空闲宽限期（默认 300s，可配置）退出；宽限期内新附着即取消退出。崩溃的 Supervisor 由其 stale 租约规则（既有合同）回收，下一个启动者重新派生。
- 载体**永不持有工作区租约**——从根上消除“关闭 Host 杀死 Browser 所用 Core”（T5）与双写窗口（D1）。

### S2 事务级乐观并发（If-Match CAS）

- Schema 迁移（**独立的 v1_0015 迁移 PR**，含回滚）：为 Candidate/Source/Claim/CriterionJudgment/HumanDecision/OfferRecord/ActionPlan/Event 增加单调 `revision` 列。
- 写入口（PATCH/POST 变更类）接受 `If-Match: <aggregate>@<revision>`；服务端在**同一事务**内校验期望 revision、执行写入、落审计；不匹配返回 `412` + 当前 revision，**不产生任何成功审计**（D3）。
- 无 If-Match 的写请求按“Last-Write-Wins 但强制 revision 递增 + 审计记录缺失前提”处理，并在 API 契约文档标注为 legacy 兼容路径；新前端一律带 If-Match。

### S3 一次性会话附着与本地安全

- Supervisor 签发**每次附着独立的会话**：token 仅存内存（SessionSecretStore 家族）、绑定附着方身份（edition + 实例号）、Origin/Referer 白名单（仅 loopback）、变更请求强制 CSRF 令牌（双提交Cookie 禁用，改自定义头 `X-SRW-CSRF`）。
- 撤销：detach、超时（默认 8h）、Supervisor 退出即全部失效；重复附着申请返回新会话，旧会话按策略保留或撤销。
- 远程访问仍不在范围；loopback 绑定不变（D5）。

### S4 Job Engine 唯一所有权

- Supervisor 是唯一调度器（沿用现有 worker 租约机制）；载体只能经 API 提交任务（`idempotency_key` 已存在，双端重复触发同一 job 只执行一次——T6）。
- 任务执行结果（OCR/ASR/AI 运行）经审计落库，载体通过轮询/推送获取，不直连 Job 表。

### S5 生命周期协议

附着/重附/心跳/detach 四原语；Supervisor 崩溃 → 载体进入“无 Core”态（明确 UI 提示 + 只读缓存标注），按需重新派生；备份/恢复/Schema 迁移进行时拒绝新附着与写入（T8）；恢复完成后附着方缓存失效重取（T7）。

### S6 T1–T10 验收落法（合成工作区，双进程集成测试）

| 场景 | 落法 |
|---|---|
| T1/T2 跨端读写 | 测试驱动 A（Python 附着客户端）写 → 驱动 B（HTTP/WebView2）读，反之亦然 |
| T3 并发冲突 | 双驱动同版本并发写同一聚合 → 一成功、一 412、审计仅一条 |
| T4 标准变更失效 | B 发布新 ProtocolRevision → A 的旧 HumanDecision 两端均 stale |
| T5 关闭不误杀 | 关 A → Supervisor 存续 → B 继续读写 |
| T6 Job 唯一 | 双端触发同一 AI/OCR 任务 → 执行一次（idempotency_key） |
| T7 重启重附 | Supervisor 重启 → 两端重附成功、缓存/权限不串 |
| T8 备份互锁 | 备份/恢复中拒绝另一端写入 |
| T9 访问控制 | 跨站 Origin/未授权附着被拒 |
| T10 历史一致 | 同一候选人 Source/Claim/Judgment/Decision 导出两端一致 |

## 实施相位（每相独立可发布、可回滚）

1. **相位 1**：Supervisor 模式 + 附着协议（特性开关，默认关）。开关关时行为与今天逐字一致（Host 自派生 Core）。验收：单载体全回归 + 附着/重附/崩溃恢复集成测试。
2. **相位 2**：Schema v1_0015 + If-Match CAS + 一次性会话/CSRF。验收：412 冲突矩阵 + 会话撤销测试 + 前端全量带 If-Match（E2E 更新）。
3. **相位 3**：双载体并发验收（T1–T10 全量）+ 文档与 Owner Guide 更新。通过后才具备 DUAL_CARRIER_ACCEPTED 申报条件。

回滚：特性开关 + 独立 Schema 迁移回退脚本；任何相位失败不影响已发布载体行为。

## 明确不做

第二套数据库/双向同步、远程 TLS/云端登录、多租户、改造 Job 引擎选型、前端框架更换。

## 可重新讨论条件

有证据表明引用计数 Supervisor 在目标机（低资源 Windows）上不可靠；或负责人批准改变部署边界（如常驻服务）。
