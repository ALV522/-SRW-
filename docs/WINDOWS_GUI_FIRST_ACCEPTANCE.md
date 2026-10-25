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

## Native embedded Python 的合成业务回归（#42；独立于 WPF UI 验收）

新增 `scripts/accept_native_business.py` 为 **Native 已装配候选** 的独立源代码/嵌入式 Python 回归工具。它先通过 `inspect_rebuilt` 严格核对完整候选目录及原始 ZIP 的指定 SHA-256，再使用该 ZIP 内的 `runtime/python.exe -I -B` 执行六组现有 Core 回归：岗位与准则、候选人/人工决定、面试/独立 Scorecard、Offer 人工转换、复评上下文 CAS、真实 Core 关闭/重启/损坏恢复拒绝。所有测试只处理其自建的临时 SQLite/Source/Knowledge 合成数据，输出仅含固定测试组名、通过数和候选 SHA 的聚合 JSON。

**不同证据等级**：脚本的状态 `NATIVE_EMBEDDED_BUSINESS_SOURCE_REGRESSIONS_PASS_UI_NOT_EVALUATED` 只说明 *当前 ZIP 自带* 的内嵌 Windows Python 执行了被选定的业务 Core 测试且所有结果成功。它**不操作真实 WPF 控件**，不证明 Windows WebView2 实际招聘全过程、人类点击路径、真实 Provider/OCR/ASR、工作区升级、双端同时写入或发行质量。不能因为这个脚本通过而改写已有 GUI 验收报告或宣布 RC。

在目标 Windows x64 电脑运行时，使用**本次候选 ZIP 对应源码或受审查的独立验证脚本**，将证据文件放在候选根目录之外，且必须为从未存在的新路径：

```powershell
& py -3.12 'D:\SRW\reviewed-source\scripts\accept_native_business.py' `
  --root 'D:\SRW\synthetic-accept-0cbd-001\candidate-extracted' `
  --zip 'D:\SRW\synthetic-accept-0cbd-001\SRW_C11_0cbd_UNVERIFIED_GUI.zip' `
  --expected-zip-sha256 'f01a5da88ba5c306608bcbe0a50b0a3cfa1a40cf52d62a40534a5e75e55f4962' `
  --evidence 'D:\SRW\synthetic-accept-0cbd-001\synthetic-evidence\business-unique.json'
```

以上路径仅为该次已核验的 0cbd 候选的**示例**，运行前须确认目录、哈希和验证器来源准确匹配。验证器与相关 `scripts/` 依赖必须来自受审查的同一源码快照，不得直接复制进正在被验证的 `candidate-extracted` 目录，否则破坏严格文件白名单。CLI 仅 Windows 可执行 Native 验收；Linux/Ubuntu Source CI 的同套回归只记为源码级合同测试，不会输出 Native Windows 通过声明。脚本按组失败关闭：缺少/跳过/失败用例、篡改或更换 ZIP、损坏输出以及已有验收文件都会被拒绝。
