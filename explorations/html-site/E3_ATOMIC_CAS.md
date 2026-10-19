# E3 — 事务级并发控制实验（仅合成数据）

## 已完成的代码

- `e3_core_server.py`：全新临时工作区启动真实 C11 Starlette Core；
- `e3_atomic_action_plan.py`：替换**仅在实验服务器中**的 Action Plan GET/PATCH 处理；
- `e3_web_bridge.py`：浏览器代理只转发合成候选人 Action Plan 的受控 PATCH，将 `If-Match` 交给 Core；
- `e3-live.html`：支持浏览器双窗口的事务冲突反馈；
- `run_e3_demo.py`、`START_E3.cmd`：临时 SQLite + 受控网页演示。

## 核心事务

E3 的 `AtomicActionPlan.update` 依次执行：

1. 用 SQLite `BEGIN IMMEDIATE` 获取数据库写入锁；
2. 读取当前实体 revision，并与客户端的 `If-Match` 比较；
3. 冲突时返回 HTTP 412，不调用业务变更函数、不生成成功审计事件；
4. 版本相符时调用现有 `upsert_action_plan`（保留业务校验与审计事件写入）；
5. 同事务中递增实验性 revision 表；
6. 成功提交后返回最新 Action Plan 和 ETag。

两个独立 SQLite 连接即使绕过代理，也必须通过这个数据库事务规则竞争同一个版本。版本不是浏览器本地状态，更不是 Python `threading.RLock`。

## 实验范围与限制

E3 使用独立 `e3_synthetic_action_plan_revision` 实验表，不修改主线 `v1_0014` schema。

这**不是正式 C11 schema migration，也不是正式 API 的可用版本**。旧的未改造接口若绕过 E3 写入，仍可能形成版本漏报。因此真实 Web/EXE 统一写入必须由正式 Core 接管原子事务及版本递增，不能让浏览器自行选择是否遵循 E3 协议。

E3 尚未解决正式授权、角色控制、长时间运行的数据库迁移、Windows Native、五份生产 Knowledge DB、OCR/ASR/AI provider 以及历史 0.8.x 业务等价性。

## 正式化需要的工作

- 将 revision 放入正式 Action Plan 的实体/迁移，并为已有记录初始化版本；
- 所有修改入口（含 EXE、批量 API、后台任务）统一进入相同的事务服务；
- 用数据库级条件更新或锁保护 revision 与实际业务行，覆盖删除、归档、取消；
- 失败不生成成功审计、重复请求采用幂等键以避免超时重试重复审计；
- 将通用业务角色授权及审计 actor 与 HTTP 会话绑定；
- 对 Claim/Judgment/Decision/Offer 各自设计更严格的业务不变式。

验收只在合成数据中进行；所有实验文件位于独立探索分支，不进入 main。

## Latest verified exploration CI

[Windows + Ubuntu + Chromium full E1–E4 acceptance (all jobs passed)](https://github.com/ALV522/-SRW-/actions/runs/39189966339) · code `2257195887bde102fd3ae77042c0e088cf039ffd`. [Verified source-only ZIP](https://github.com/ALV522/-SRW-/actions/runs/39189966339/artifacts/12160145418). This is not a production Windows executable.
