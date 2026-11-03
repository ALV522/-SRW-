# C11 本地 HTML/Browser 实际业务入口：源码预览阶段

本入口直接调用**现有** `srw.api.app.create_v1_app`，使用真实 C11 HTTP/API/SQLite/业务前端；没有开发另一套 Web 业务内核，也没有新增 SQLite 同步系统。

**工件状态：SOURCE PREVIEW / NOT PORTABLE / NOT RC / NOT GA**。
它不是共享 Windows WPF 生命周期的完整双载体成品，不得同时向同一个 Windows 工作区启动独立 Core。

## 条件

- 完整 SRW C11 源码 checkout；Python 3.12；按 requirements-ci.txt 安装依赖。
- 正式数据模式需合法来源、经验证的五套 Knowledge DB；默认期望 `knowledge/active/{taxonomy,job_info,competency,market_reference,reference}/knowledge.db`。文件头检查只是最小文件识别，不代表 Knowledge 质量或来源验证。
- 必须明确提供**源代码外部、非正在使用**的独立工作区。默认拒绝非空目录，防止无意读取用户真实数据库。
- 所有 HTTP 都只在本机 127.0.0.1，前端使用 `/v1`。这仅是来源限制，不是远程身份系统。

## 用法

新工作区的本地 Web：
```powershell
py -3.12 scripts\start_local_web.py --workspace "D:\SRW\local-web-workspace"
```

重开**明确由此预览创建、且已停止使用**的工作区：
```powershell
py -3.12 scripts\start_local_web.py --workspace "D:\SRW\local-web-workspace" --reuse-workspace
```

缺少生产 Knowledge 时，不能伪造正式数据。开发者可以用合成数据验证真实 Core：在全新空工作区使用：
```powershell
$env:SRW_SYNTHETIC_BROWSER_ACCEPTANCE='1'
py -3.12 scripts\start_local_web.py --workspace "D:\SRW\synthetic-local-web" --synthetic
```

合成模式只用于调试/自动验收，不可与真实招聘工作区混用。停止服务请在控制台按 Ctrl+C；Linux 上正常发送单次 SIGTERM 也应让服务完成退出并释放本进程持有的工作区租约（#195）。SIGKILL、断电及 Windows 服务管理器关闭不属于该项验收；真实模式下的 SQLite 不会因关闭浏览器而自动删除。

## 会话 ON：真实本机终端配对（#43 M3A）

默认会话 OFF 与上述启动方式保持不变。需要验证本地浏览器受保护入口时，先在**交互式 PowerShell/CMD 终端**中启用：

```powershell
$env:RECRUITMENT_SESSION_ENFORCE = '1'
py -3.12 scripts\start_local_web.py --workspace "D:\SRW\local-web-session-on"
```

Core 启动时只向该终端显示一次 **60 秒有效、单次使用**的配对码；浏览器访问 `http://127.0.0.1:8765/v1`（如使用 `--port`，按实际端口），在“本机配对”表单中手工输入。配对码不得写入 URL、脚本参数、文件、工单或日志；会话 Cookie 为 HttpOnly，CSRF 由同源浏览器请求携带。输入错误次数超限、配对码过期或主动注销后，当前源码预览没有在线补发入口，须**正常关闭 Core，再在已确认不被其他进程使用的原工作区上以 `--reuse-workspace` 重启**，获取新码；不要删除锁文件或复用真实生产工作区。

ON 模式下，重定向 stdout、管道、CI 或无交互终端的启动会在创建工作区前以退出码 `3` 拒绝，不会把一次性凭据打印到日志。后台服务部署、Windows Host 附着与共享 Core Supervisor 尚未通过 M3B 验收；不得通过关闭会话门禁来冒充 ON 模式成功。Linux Chromium 的合成 PTY→真实启动器→HTTP/SQLite 用例与 Windows Native/WPF 验收分开记录。

## 核心限制与后续

1. 此预览的 Core 由 Local Web 进程拥有，无法让 Windows WPF 自动接管；关闭 Desktop 后浏览器独立续用、跨端并发 CAS、任务唯一所有权**仍待 Issue #43** 的正式 Supervisor/契约。
2. 工作区单写者已由 [工作区租约合同](WORKSPACE_LEASE_CONTRACT.md) 保证：本入口与 Windows Host 竞争同一个 `data/app.lock` 目录，用原子创建失败而不是"看一眼文件是否存在"。跨端 Supervisor、事务级 CAS 与任务唯一所有权**仍待 Issue #43**
3. Windows Host 的最新 Native 完整包仍待 Issue #42 验收；本入口不能为任何 Native 构建背书。
4. `--reuse-workspace` 是显式授权读取/修改既有 SRW Web workspace 的操作，建议仅用于此前本入口创建的独立目录，并始终先备份。
5. 浏览器真实业务验收将使用此启动入口的 `--synthetic --no-browser` 模式，经 Playwright/Chromium 操作当前前端和真实 API/SQLite。
6. Windows 用户的最终零配置浏览器启动入口、已审核的运行时/Knowledge 合包及双载体同实例安全性尚未完成。

## 下一验收

- 核对当前准确提交的 Chromium E2E 能否经此预览入口运行全部既有业务场景；
- 使用真实生产 Knowledge 的合法数据源，对同一运行版号做实际打包、再启动及备份/恢复验收；
- 在正式 Core Supervisor 就绪后，验证 WPF 与 Browser 同一进程所有权下的读写/冲突/关闭行为。
