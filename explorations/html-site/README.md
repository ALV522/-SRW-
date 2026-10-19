# SRW HTML / Web + Windows 探索（E0–E5 & Native SOURCE Lab）

本目录属于**隔离技术探索分支** `explore/html-site-prototype`。目标是让 SRW 保留本地 SQLite、Blob/Source、Knowledge、OCR/ASR/AI、证据/审计与成熟招聘业务能力，同时以浏览器和 Windows WebView2 作为两种 UI 载体。

**原则：一个权威 SRW Core + 一个数据工作区 + 可拆卸的多个 UI。** 不能把“HTML 网站形式”误理解为一个无后端的纯静态 HTML 文件，也不要新建两套 SQLite 再做脆弱的同步。

## 当前实验的事实边界

| 实验 | 已实现的主要能力 | 验收与限制 |
|---|---|---|
| E0 | `index.html` 单文件产品外观与 Mock 数据 | 只用于产品体验，不是真实后端 |
| E1 | `e1-live.html` + GET-only 同源 Bridge | 真正 C11 API + 临时 SQLite + 候选人/Source/工作台读取 |
| E2 | 仅合成 Candidate Action Plan PATCH，ETag/If-Match | **代理层**版本协调，不能当作正式数据库事务 |
| E3 | SQLite `BEGIN IMMEDIATE`、版本比较、业务写入、审计同事务 | 实验性临时 Core 路由，不是 main Schema 迁移 |
| E4 | 独立控制器持有一个 Core、两浏览器载体可 detach/reattach | “桌面载体”是浏览器替身，不是真实 WPF EXE |
| E5 | 一次性附着能力、HttpOnly SameSite Cookie、Core 身份固定、会话失效 | 本地合成身份协议，**不是正式用户认证/授权** |
| Native SOURCE Lab | Windows CI 编译**真实 WPF/WebView2 Host**，从外部 Python 3.12 虚拟环境启动临时 C11 Core；浏览器 E1 附着**同一个 Host-owned Core/SQLite**，检测 `frontend_loaded` | 已跑通真实 WPF/浏览器只读共用后端，但不同于 E4 的 detached Core，且**不是独立 Windows Portable** |

**通过的确切运行记录**：

- [E1–E5 真实 C11/Chromium/Windows 合成验收](https://github.com/ALV522/-SRW-/actions/runs/39193776226) — PASS。
- [WPF Source + Native SOURCE Lab](https://github.com/ALV522/-SRW-/actions/runs/39196390613) — Windows 两个 Job PASS：真实 WPF Host 启动、WebView2 `frontend_loaded`、浏览器 E1 读取同一个临时 Core。
- [Native SOURCE Lab 技术/工件说明](NATIVE_SOURCE_LAB.md) 与 [Native Host 构建门禁](NATIVE_HOST_BUILD_GATE.md)。
- 真正用户电脑上的 **`d8d032d` Native 候选包已经完成基础 GUI 验收**，但属于 [主线工件证据](https://github.com/ALV522/-SRW-/blob/main/docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md)，不等于本分支 E1–E5 或 Native Lab 已正式发布。

## 推荐下载和试用

**E1–E5 HTML 演示**：在 [E1–E5 工作流](https://github.com/ALV522/-SRW-/actions/workflows/html-site-sandbox.yml) 找最近一次成功运行的 `SRW-HTML-E1-E5-WINDOWS-SOURCE-DEMO-` Artifact。完整解压，需 Python 3.12，首次联网安装隔离虚拟环境依赖；顶层入口为：

```text
START_HERE.cmd   # E1：只读真实 C11/临时合成数据
START_E2.cmd     # E2：代理锁/ETag 写入实验
START_E3.cmd     # E3：SQLite 事务 CAS
START_E4.cmd     # E4：独立 Core + 两个浏览器代理
START_E5.cmd     # E5：受保护的本机载体附着
```

不要下载单独的 `run_e1_demo_windows.cmd` 或把它移出文件夹：它需要完整后端源码，早期因此出现“full exploration branch source checkout is required”。

**Native SOURCE Lab**：在 [Windows Native Host Sandbox](https://github.com/ALV522/-SRW-/actions/workflows/native-host-sandbox.yml) 的成功运行中下载 `SRW-C11-WPF-SOURCE-SYNTHETIC-PREVIEW-NOT-PORTABLE-` 工件，完整解压并按 [说明](NATIVE_SOURCE_LAB.md) 使用。它需要系统 Python 3.12 和 .NET Desktop/WebView2 Runtime，Knowledge 与工作区均为临时合成数据。

**不要将任意实验连接到真实招聘数据库，也不要上传简历、Provider Key、Session Token 或本机工作区锁。** 退出后测试脚本会结束临时服务并清理一次性 SQLite/Knowledge；Windows 文件锁有有界重试。

## 架构核心

```text
                一个 SRW Core（唯一权威）
            /             |             \
       Windows WPF      Browser       Future private client
        WebView2         HTML
            \             |             /
            同一 Project / Candidate / Source / Claim / Audit
                      SQLite + Blob + Knowledge
                           OCR / ASR / AI Jobs
```

E4 展示了**独立 Core Owner**；Native SOURCE Lab 则确认**真正 WPF EXE 与浏览器共享同一个 Host-owned Core**。二者尚未统一：现有真实 Windows Host 关闭时仍会终止它拥有的后端，距离独立网页长期运行还有进程监督/授权/退出策略的集成工作。

E3 的事务要推广到正式产品，必须为所有 Action Plan 和其它敏感业务写入建立正式 revision/If-Match/审计的数据库事务，不允许旧写入口绕过。E5 的 localhost 能力协议要正式化，须包括 Windows 用户/进程身份、权限与会话撤销、CSRF/Origin 以及对远程模式的 TLS/租户隔离审计。

## 仓库位置与文档

- [E1 状态](E1_STATUS.md) · [E2 条件写入](E2_CONTROLLED_WRITE_GATE.md) · [E3 SQLite 原子事务](E3_ATOMIC_CAS.md) · [E4 独立 Core](E4_SHARED_CORE.md) · [E5 受保护附着](E5_ATTACH_CONTRACT.md)
- [双载体产品契约](DUAL_CARRIER_PRODUCT_CONTRACT.md) · [双载体验收方案](DUAL_CARRIER_TEST.md) · [完整实验计划](EXPERIMENT_PLAN.md)
- [Windows 无 EXE 源码试用](USER_ACTIONS_NO_EXE.md) · [Windows EXE 附着测试](USER_ACTIONS_WINDOWS.md) · [Native SOURCE Lab](NATIVE_SOURCE_LAB.md)

## 向正式主线发展的顺序

1. 完成 C11 招聘核心纵向业务和目标 Windows GUI/Portable 可重复验收；**不为 Web 牺牲历史 v0.8.x 业务能力**。
2. 将 E3 的事务 CAS、E4 的单 Core 进程所有权和 E5 的附着保护**逐项重做为可审查的产品实现**，确保 Schema/业务不变量/权限/安全/审计不被绕过。
3. 使用真正 WPF/浏览器对同一个受信任 Core 同时读写候选人和证据，验证互斥、冲突、退出/重启和后台任务不重复；然后才讨论 Web 与 EXE 同步发版。
4. 未来远程 Web 需要独立身份认证、TLS、安全运营与数据治理，不能直接将 loopback 服务监听到 LAN。

**当前实验是证据和设计输入，不是第二套生产产品。** 当前产品主线与下一步业务计划以 [main README](https://github.com/ALV522/-SRW-/blob/main/README.md) 和 [ROADMAP PR](https://github.com/ALV522/-SRW-/pull/33) 为准。
