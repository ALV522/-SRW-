# SRW 仓库与交付证据地图（以 G1 为准）

这是一份**导航/工作分配说明**，不取代 `AGENTS.md`、`PRODUCT_CHARTER.md`、`CAPABILITY_MATRIX.md`、`ROADMAP.md`，更不将某个历史 SHA 的验收状态更新为当前 main PASS。每次工作前重新读取远程 main 与 Actions。

## 1. 当前仓库代码的权威位置

| 区域 | 职责和约束 | 当前优先任务 |
|---|---|---|
| `backend/srw/modules/`, `runtime/`, `evidence/`, `providers/` | 唯一权威业务状态、SQLite、Source Blob、备份恢复、Evidence、Job/Provider | 不破坏人工决定与材料溯源；#41/#42 P0 数据正确性 |
| `backend/srw/api/{app.py,fullworkbench.py,routes/}` | 单一 Core 的 HTTP 适配与业务用例组合 | API 合同与路由回归，渐进拆聚合，不增加第二 Core |
| `frontend/dist/` | Windows WebView2 和 Local Browser 共用的 API 前端 | 已有 API-client/Job Setup/复评与恢复告警；以真实用户验收缺口为先，不为减少行数拆文件 |
| `desktop/SRW.Desktop/` | WPF Host、进程/Workspace Lease、WebView2、隐私日志 | 当前同 SHA Host 编译并非 GUI/整包验收 |
| `scripts/` | Source/Native 组装、供应链核验、离线工作区验收 | #42 Native 输入保全/独立重建；严格 ZIP identity；不可写真实用户数据 |
| `convergence_tests/` | Core/API/数据、业务规则与恢复故障回归 | 对真实人工业务动作/损坏/并发保证做正反例 |
| `browser_acceptance/` | 真 Core + Chromium 的合成 UI 端到端 | #121 取消恢复、重启后 Source/审计真实保真；不替代 Windows GUI |
| `docs/decisions/`, `docs/` | G1、ADR、发布/回退、能力矩阵和架构路线 | 保留历史证据原始记录；新增带日期 SHA 的验收结论 |
| `verification/`、`SOURCE_MANIFEST.sha256` | 冻结 API/源码 hash 与合同门禁 | 更新清单仅反映审查后的字节，`SOURCE_RECOVERY_MANIFEST.sha256` 不改 |

## 2. 版本与验收是多轴的

Runtime VERSION / Schema / Git main SHA / Native ZIP SHA / Local Browser ZIP / 原始私有 Runtime & Knowledge 的字节来源**彼此不同**。独立分级为 Source/Ubuntu & Windows CI、真实 Chromium、完整 Native 装配与内嵌 Python、WPF UI、完整招聘纵向操作、Provider/Knowledge、双载体同一 Core。任一层 PASS 都不能外推到后续层。

- 历史 alpha/旧 ZIP/`DEVELOPMENT_STATE.md` 或旧 `ROADMAP.md` 中带 SHA 的行是**历史观察**，不是实时 CI 仪表盘。
- `docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md`、`docs/C11_NATIVE_CANDIDATE_UPGRADE.md` 及 Issue #42 按**候选 SHA**记录；目标设备的手工报告不等于机器 JSON。
- `docs/NATIVE_ARTIFACT_CUSTODY_AND_REPRODUCIBILITY.md` 记录 Runtime/五库的外部保全与独立供应链缺口；已哈希审计的历史 ZIP 不是永远可取得的依赖仓库。

## 3. 开发优先顺序（每次 WIP ≤ 3）

1. **P0 #41/#42 数据与业务**：Source 文件读/显示完整性、备份/恢复原子性、复评 CAS、人类审批→Interview→Scorecard→Offer 闭环；分别以 Source/API、Chromium 和真实 Windows 工件证明。
2. **P0 #42 Windows 发行输入**：受控双副本+恢复演练 → 官方 Windows Python/固定 Wheelhouse 可重建 → 五库来源/授权/完整性 → 实际 Native GUI 和六组嵌入业务套件。
3. **P1 #43 单一 Core 双载体**：统一租约/会话与任务主控、attach/revoke、Origin/CSRF、CAS、故障恢复、双入口互通。

**明确暂停**：全新 UI 框架、整仓迁目录、旧 #101 多领域分支直接覆盖 main、微服务/SaaS、正式 RC/GA 虚报。

## 4. 多 Agent 当前交接

- **Track A**：跨 PR 审查与合并、P0 Core/备份/证据、Native Runtime 与五库保全、Windows/发行工件验收。
- **Track B**：经 #103 明确批准的真浏览器恢复正反例（#121），修复真实 Source 内容持久性断言并更新最新主线清单；下一片备份中断测试先做只读计划。
- **Track C**：#43 的 lease/session/restore 一权威 Core 只读合同；任何跨 Core/Schema/Host 修改先审合同，旧 #101 不整体合并。

权威动态同步入口 [Issue #103](https://github.com/ALV522/-SRW-/issues/103)；Windows 工件 [Issue #42](https://github.com/ALV522/-SRW-/issues/42)；外部依赖 [Issue #124](https://github.com/ALV522/-SRW-/issues/124)。
