# SRW C11 源码基线

版本：`1.0.0-alpha10-convergence11`。数据库结构：`v1_0014`。

本包是 GitHub 源码产物，不包含内嵌 Windows Python、五个生产 Knowledge DB 或经过当前版本实机验收的原生宿主。不能把源码 ZIP 视为双击即用的 Windows Portable 成品。

使用 `python scripts/portable_input_preflight.py` 检查外部载体、运行时和生产 Knowledge 的必要输入。任何缺失会返回 BLOCKED。装配与 Windows GUI 实机验收必须另外进行。

当前源代码与验收边界请参考 README.md、DEVELOPMENT_STATE.md、docs/ACCEPTANCE_PLAN.md；实际通过与否以对应提交的 GitHub Actions 日志为准。
