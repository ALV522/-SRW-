# SRW C11 当前源码基线

**主线**：GitHub `main`；**产品源码**：`1.0.0-alpha10-convergence11`；**Schema**：`v1_0014`。

此仓库是完整可审计的**开发源码**，不是双击可用的 Windows Portable 安装包。源码测试（现为 113 项）与 3 条 Chromium 真实浏览器操作测试必须以具体 Git SHA 的 CI 为准；Windows WPF/WebView2 目标机尚未验收。

源码核验：`python scripts/check_source_integrity.py`、`python scripts/check_release_truth.py`、`python scripts/run_convergence_verification.py`。

真实 Portable/Native 装配需要**单独审计**的 Python Runtime、五套生产 Knowledge DB 和精确版本的 Windows Host。缺失时必须返回 BLOCKED，而不是把合成 Knowledge 或历史 Web 包伪作正式发布。

仓库入口：[README.md](README.md) · [主线治理](docs/REPOSITORY_GOVERNANCE.md) · [版本现状](DEVELOPMENT_STATE.md) · [历史开发包](docs/history/ARCHIVE_CATALOG.md) · [发布要求](docs/RELEASE_PROCESS.md)。
