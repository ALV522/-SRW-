# E4 — 独立 Core 生命周期与双载体沙盒

## 核心问题

现有 Windows Host 拥有后端进程和 WorkspaceLease。当 Host 关闭时，后端也随之退出。假如 Web 浏览器只附着该端口，那么关闭 EXE 后，浏览器会失去数据服务。

远期“Web 版和 EXE 版并存、数据互通”的合理单机方案需要 **一个独立持有数据目录的 Core 进程 + 两个只持有 UI 的载体**。不能让两个 SRW Python 进程同时打开同一生产 SQLite/Blob 工作区。

## E4 已实现的隔离原型

`e4_shared_core.py` 在全新临时目录启动**唯一** C11 Core，并初始化合成候选人。其独立控制器再启动两个不同的浏览器入口：

- `web`：浏览器版代理；
- `desktop_surrogate`：第二个浏览器代理，模拟 WebView2 的客户端生命周期。

两端共享 `instanceId`、`sessionId`、`dataScopeId`，访问同一数据库。即使其中一端被主动 detach，另一端仍然可以读取及操作临时 Action Plan；全部 UI detach 后，Core 仍由控制器持有，可重新 attach。只有停止控制器才会终止 Core、释放文件句柄并清除一次性数据目录。

启动入口 `run_e4_demo.py` / 完整源码包的 `START_E4.cmd`。加 `--smoke` 可验证 attach→跨界面写入→关闭其中一端→继续写入→关闭全部→重新附着的流程。

## 严格的真实性边界

**这里的 desktop_surrogate 不是 Windows EXE，也不是已验收的 WebView2。** E4 只证明通过独立控制器持有 Core 可以实现 UI 生命周期解耦，不证明 Windows 桌面宿主已经完成独立服务化改造。

E4 无持久服务、Windows Service/Tray、生产安装器、真实账号/授权、跨网络访问或孤儿进程清理。实际 Windows 产品不能直接部署 E4 demo。

## 实际产品化阶段

1. 先完成 API 兼容、可实机验收的 C11 Windows Native 打包；
2. 将 WorkspaceLease/后端生命周期从 GUI 进程转到单独的 Local Core Supervisor；
3. Windows EXE 与 HTML Web 独立向 Supervisor 注册并校验 Core 身份；
4. 定义关闭 EXE、关闭浏览器、系统注销及重启的 Core 停止策略；
5. 统一数据库事务版本检查、授权、文件能力与 Job Worker 所有权；
6. 通过真实 WPF/WebView2 及浏览器同时使用同一招聘项目的验收。

不应在该流程开始前擅自改变主线 Windows Host 的锁/迁移逻辑。

## Latest verified exploration CI

[Windows + Ubuntu + Chromium full E1–E4 acceptance (all jobs passed)](https://github.com/ALV522/-SRW-/actions/runs/39189966339) · code `2257195887bde102fd3ae77042c0e088cf039ffd`. [Verified source-only ZIP](https://github.com/ALV522/-SRW-/actions/runs/39189966339/artifacts/12160145418). This is not a production Windows executable.
