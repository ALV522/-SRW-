# SRW Convergence 09 源码基线

版本：`1.0.0-alpha10-convergence09`。数据库结构：`v1_0014`，本轮无迁移。

以 v0.8.12-R2 的能力完整性为基线，保留 C08 业务能力，整合 C09 本机访问边界、诊断、资源释放和双平台验证。

本包是源码包，不包含内嵌 Windows Python、五个生产知识库或原生宿主二进制。不能把源码 ZIP 当作双击即用的 Portable 成品。`START.bat` 用于资源完整的 Portable 装配；`BUILD_WINDOWS_NATIVE.bat` 仍需要精确历史 Windows 载体。

源码验证步骤见 README.md；当前通过与否以对应提交的 GitHub Actions 日志为准。历史验证报告保持原样，不充作本次运行结果。
