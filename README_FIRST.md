# SRW · 从这里开始

当前唯一产品整合研发主线：[main](https://github.com/ALV522/-SRW-/tree/main)；C11 源码版本 `1.0.0-alpha10-convergence11`，Schema `v1_0014`。

SRW 是本地优先、证据驱动的智能招聘工作台。AI/OCR/ASR 用于可追溯的辅助处理，**不自动作出录用决定**；历史 v0.8.x 是业务功能完整性对标对象。

**截至 2026-10-19**：主线 `c9d70cd48d03` 已通过 Ubuntu/Windows 各 **146 项**源码测试、**5 条**真实 Chromium 业务测试和 **280 项**源码完整性校验。较早的 `d8d032d` Windows Native 候选包已在真实电脑上通过 WPF/WebView2 **基础启动**、项目新建、招聘标准草案更新和正常退出验收，但不是最新 main 的正式 Portable/RC/GA。

源代码开发应从 [README](README.md) 开始；项目缺口和未来计划见 [开发状态](DEVELOPMENT_STATE.md)、[路线图](docs/ROADMAP.md)。真实工件边界见 [Windows GUI 验收](docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md) 和 [发布规程](docs/RELEASE_PROCESS.md)。

[E1–E5/Native SOURCE Lab](https://github.com/ALV522/-SRW-/tree/explore/html-site-prototype) 在独立探索分支：已经验证真实 C11、临时 SQLite、浏览器及合成 WPF 联调，但不代表正式 Windows Portable 或生产认证服务。没有必要下载旧 E1 单文件启动器来替代完整源码包。

源码完整性：`python scripts/check_source_integrity.py`；发布身份：`python scripts/check_release_truth.py`；回归：`python scripts/run_convergence_verification.py`。一切 PASS 都须对应实际 commit SHA 和运行证据。

最新的 5 项 Chromium 场景包括独立 Scorecard 与 Offer 状态闭环，详情见 [业务验收记录](docs/BUSINESS_E2E_SCORECARD_OFFER.md)。
