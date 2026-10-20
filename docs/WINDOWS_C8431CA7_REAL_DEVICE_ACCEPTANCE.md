# SRW C11 c8431ca7 Windows Native — 实机证据与下一次产品验收

> 证据来源：2026-10-19 用户上传的一张 WPF 工作台截图及一次完整 `host.log`（约 74 秒）。这是**旧候选包 c8431ca7 的真实设备验收**；日志含用户路径和内部工作区标识，**不得上传原始日志至 GitHub**。本文件仅记录脱敏摘要与可复核的行为结果。

## 实际验收

| 操作与 HTTP | 从实际日志可证实的结果 |
|---|---|
| WPF 主窗口启动 / WebView2 | `webview_initialized`、`frontend_loaded` |
| Core 监听本地回环端口 | `127.0.0.1`，`/runtime/ready` / `/runtime/info` 返回 200 |
| 工作台静态资源、Dashboard | HTTP 200，截图显示工作台指标与导航 |
| 新建项目 | POST `/api/v1/projects` → 200 |
| 发布岗位标准 | POST `/api/v1/protocol-revisions/{id}/publish` → 200 |
| 新建候选人 | 首次 POST 409；随后第二次 POST → 200，随后工作区 GET → 200；原始请求体不可见，不能断言第一次 409 是重复姓名还是其他业务不变量 |
| 新候选人 Assessment | GET `/assessment` → 409；候选人尚无有效材料/决策上下文时允许打开 Source 收件工作区，应避免该可选请求产生不必要 409 |
| 完整退出 | `shutdown_requested` → HTTP 202 → `backend_stopped` → `workspace_released` → `host_closed` |

截图中侧栏标记“服务已就绪”，顶部却仍标记“服务检查中”，源代码根因是健康检查在 `shell()` 初始渲染后完成、未同步更新顶部 badge，并非后端未就绪。

起始 `host_started` 到 `frontend_loaded` 约 4.3 秒；`shutdown_requested` 到 `host_closed` 约 0.36 秒。数字只是本次设备、一次运行，不能充当性能 SLA、可靠性长测或正式 Release 证据。

## 本 PR 的 P0 可用性与隐私修复

1. **就绪状态一致**：顶部 `#service-health-text` 与侧栏共享 `state.health`，初始化健康检查完成后更新；使用可访问的 `role=status`。
2. **新候选人无效 Assessment 请求**：先读取工作区，只有存在真实 `decision_context_hash` 才额外获取可选 Assessment，保留无材料时的收件界面和后续材料发布流程。真正已有上下文但 Assessment 失败的行为仍需独立业务排查。
3. **内嵌 favicon**：本地 data URI，无需发起 `/favicon.ico` 导致 HTTP 404。
4. **减少诊断日志中的招聘隐私**：Host 子进程输出不再直接记录原始 URL/查询、候选人 ID、项目 ID、异常文本和材料片段；改为 HTTP 状态、动作、路由类别及受控生命周期/异常类型。Host 自身不再默认记录真实数据目录路径与异常原文。
5. **自动验收**：Chromium 新增第 8 项真实 C11/SQLite 初次使用场景；Windows Host 编译工作流加入纯 C# 诊断分类器回归（使用虚构个人数据和敏感 Query 测试）。

日志最小化并不意味着**本地 SQLite、合法业务审计和 Source 证据会被擦除**。这些仍由业务 Core 正常持久保存。诊断隐私与业务事件溯源是不同职责。

## 尚缺少的产品验收

- 真正 Windows GUI 完整操作：Source/PDF 导入、人工 Claim/Criterion 核实、Decision（材料/标准变化）、独立面试 Scorecard、Offer、联系运营与备份恢复；
- 真实设备的二次启动/故障恢复、无僵尸后端、工作区锁与长期占用、Windows DPI 与键盘可访问性；
- 五套生产 Knowledge 质量、OCR/ASR/AI Provider 有效性、数据库升级和真实数据迁移；
- 修复后新的完整 `UNVERIFIED_GUI` ZIP 的实际 Windows GUI 验收。此前 `c8431ca7` 的截图和日志**不能证明修复后新 SHA 的 GUI 已通过**。

验收流程：从同 SHA 的 [Windows Host CI](https://github.com/ALV522/-SRW-/actions/workflows/windows-host-candidate.yml) 下载升级工具包，使用完整且 SHA 匹配的原始 `d8d032d` Prepared ZIP，在新的独立文件夹装配并启用全新 `--data-root`。不得在真实招聘数据工作区上试运行未验收的候选包。
