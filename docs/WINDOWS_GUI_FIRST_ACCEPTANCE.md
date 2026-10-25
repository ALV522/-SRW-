# C11 Windows Native 原生 GUI 首次实机验收证据（2026-10-19）

## 结论与边界

**正式认定：Windows Native GUI 基础启动与退出验收通过；创建招聘项目、修改招聘标准草案两项实际业务 HTTP 写操作通过。** 用户提供了桌面截图、PowerShell 运行结果、`*.pyc` 文件列表，以及完整 45 条 JSONL `host.log`（2026-10-19）。原始日志为用户本地运行证据，未将本机路径、随机 Session ID、UUID 等原始信息提交到 Git 仓库。

待验收版本：`SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip`，候选包源码和 Host Git SHA `d8d032de255c87839adbeedc5737124d7fbfc3cd`，SHA-256 `27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb`。后续源码修复在 `main` 中进行，不会悄悄更改这个候选包。

## 已经证实的运行行为

| 证据 | 本机观察 | 验收结论 |
|---|---|---|
| 早前 `verify_prepared_native.py` 输出 | 273 个源码、2332 个 Runtime、5 个 Knowledge DB、13 项 Python 依赖和 15 个 Host 成员被核验；嵌入式 Python 3.12.10，`WINDOWS_BACKEND_SMOKE_PASS_GUI_PENDING` | Windows 后端与 Runtime **PASS** |
| WPF 截图 | 桌面原生“智能招聘工作台”窗口可见；“服务正常”，工作台总览加载且显示空数据 | GUI 基础呈现 **PASS** |
| `host.log` | `host_started`、`workspace_lock_acquired`、`backend_process_started`、`backend_ready`、`webview_initialized`、`frontend_loaded` | GUI 启动顺序 **PASS** |
| `host.log` | `GET /api/v1/runtime/ready`、`GET /api/v1/runtime/info`、`GET /api/v1/dashboard` 均 HTTP 200 | 本地 API **PASS** |
| `host.log` | `POST /api/v1/projects` HTTP 200；`PATCH /api/v1/protocol-revisions/<id>` HTTP 200 | **项目新建和招聘标准草案修改通过** |
| `host.log` | `shutdown_requested`、`backend_stopped`、`workspace_released`、`host_closed`，正常程序退出 | 正常关闭/释放工作区锁 **PASS** |
| `host.log` | 未见后端崩溃、启动重试、WebView2 初始化失败、业务 HTTP 5xx | 当前这次会话未观察到致命错误 |
| `host.log` | `GET /favicon.ico` 404 | UI 图标资源小问题，**不阻断核心业务** |

按日志 UTC 时间戳精确计算：`host_started` → `backend_ready` 约 **3.03 秒**；至 `frontend_loaded` 约 **4.92 秒**；整个会话约 94.31 秒。它们只是这一台目标机器、这一次会话的观察值，不是跨设备的性能基准。

## 重复完整性验证失败的原因

候选包首次执行严格源/Runtime/Host 哈希验收成功，后续在同一个解压目录再次执行返回“unreviewed files”。Windows 上实际发现额外的 `runtime/Lib/c11-overlay/**/__pycache__/*.pyc`，因此之前关于 CPython 自发字节码缓存导致文件集变化的判断得到直接的文件证据。除该列表之外是否还有其他额外/丢失文件，需要利用新版验收器的差异样本判断；不能一概称所有额外文件安全。

已在 [PR #30](https://github.com/ALV522/-SRW-/pull/30) 中修复未来 Host 和 Python smoke 的字节码写入，并保留精确 SHA 白名单。此修复会作用于未来重新编译的 Host，不会修改现有 d8d032d ZIP。**原始首次通过的 `C11-Windows-smoke.json` 保留。**

## 可重复的 Host 日志核验

新增 `scripts/audit_windows_host_gui_log.py`（只读，默认不生成文件），根据同一 Host Session 的启动、就绪、WebView2 页面、退出状态及业务 HTTP 写操作判断最小 GUI 基线，不将不同 Session 拼接伪造一个“完成”的流程：

```powershell
py -3.12 D:\SRW\source\scripts\audit_windows_host_gui_log.py `
  --host-log D:\SRW\synthetic-workspace\logs\host.log `
  --evidence D:\SRW\evidence\C11-GUI-baseline-20261019.json
```

报告只输出启动步骤、汇总 HTTP 写操作数量和非阻断异常类别；不输出用户本机完整目录、UUID、Session ID 等原始日志内容，也不会改写 `host.log`。既有验收报告不会被覆盖。

## 未通过/未覆盖的验收

- 虽然用户反馈“界面与功能运转正常”，本次日志未记录实际新增候选人及附件导入的 HTTP 写入；不得据此标记“候选人完整 CRUD 已验收”。
- AI Provider 密钥、OCR/ASR、语义检索、面试 Scorecard、Decision、Offer、运营队列、Knowledge 维护、备份与恢复等完整业务场景尚未在这次 Windows GUI 会话证明。
- 是否存在 GUI 自动化层面问题（显示缩放、WebView2 再启动、长时运行、崩溃恢复、资源释放）需要进一步测试。
- 仅将 `Windows Native GUI 基础启动和退出` 以及实际日志明确证明的业务写入列为 PASS。**不得将整个 SRW C11 提升为正式 RC/GA 发行状态。**

## 后续 Native Host 脱敏 HTTP 证据的判定边界（2026-10-25，#42）

新版 WPF Host 在 `BackendOutputPrivacy` 中将后端访问日志映射为不含 URL、候选人 ID、项目 ID、源文件名和凭据的结构化 `backend_http` 事件，仅保留 `method`、`status`、`route`（路由族）。此前的 `audit_windows_host_gui_log.py` 仅从历史的 `backend_stdout` 解析 HTTP 成功动作，因此可能在真正执行过业务请求的新版 Host 会话里报告空白业务计数。

审计器现增加 `business_http_redacted_write_counts`：仅按固定白名单的 HTTP **写方法 × 脱敏路由族**统计 2xx 成功记录；若同一会话还包含旧访问行，优先使用结构化事件、**不重复计数**。其他未识别字段/方法/路由均不可直接写入验收 JSON，从而避免恶意或异常日志内容泄露。历史 `business_operations_http_success` 仅在无结构化记录时保留精确已知旧端点统计，用于历史日志兼容。

**严格限制**：`POST candidate_api` 等分类不能区分新增候选人、上传简历或其它业务动作，`PATCH protocol_api` 也不能单独证明发布、Decision stale 或人工复核；这些计数不能算作完整招聘流程 PASS。尤其 Native GUI 的基础导航/正常退出与招聘业务完整执行属于不同验收层级，仍需要真实窗口操作、持续化结果、重启、备份恢复及独立人工证据。
