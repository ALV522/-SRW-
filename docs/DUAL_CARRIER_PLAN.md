# SRW 双载体产品化计划 · Windows / HTML / Web (G1)

## 目标

将 Windows WPF/WebView2 EXE 和本地 HTML/Browser 视为同一 SRW 软件的**两个真实产品入口**。从现在开始并行研发，争取首个可用产品同期提供。不要等待 Windows GA 才开始 Web，也不要因此牺牲 Windows 正式验收。

- 一套 SRW Core、业务状态机、API、SQLite、Blob/Source、Knowledge、审计、AI/OCR/ASR 任务调度。
- Windows EXE 提供桌面原生窗口；Local Web 通过本机启动器和浏览器打开相同业务前端。
- HTML 是展示载体，不意味着双击无后端 index.html 就有 OCR/SQLite/AI 全功能。
- 暂不做远程公网部署、云端登录、多租户和不同数据库双向同步。


## M1 增量：正式主线的 Local Web 源码预览

`scripts/start_local_web.py` 已以显式独立工作区、真实 C11 API/HTML 前端及受控合成模式实现源码预览；与 Windows WPF 共用源码层面 Core 而不是另建一套业务。已有工作区默认拒绝，禁止复用活跃 Windows 工作区。详见 [LOCAL_WEB_SOURCE_PREVIEW.md](LOCAL_WEB_SOURCE_PREVIEW.md)。当前没有独立 Supervisor、正式 CAS/会话附着与双端并发验收，不应将源码预览标为发行成品。

### M1 增量：D1 单写者由同一租约强制（源码级）

两个载体现在竞争**同一个** `data/app.lock` 目录：浏览器 Core 用 `os.mkdir`，WPF Host 沿用 `CreateDirectoryW`，原子创建失败即拒绝启动。此前浏览器侧只是在校验阶段"看一眼" `app.lock` 是否存在，然后用另一个锁文件保护自己；Host 在浏览器 Core 运行期间仍能取得工作区，形成同一 SQLite 的双写窗口。该缺陷已由 [工作区租约合同](WORKSPACE_LEASE_CONTRACT.md) 关闭。

证据边界：`convergence_tests/test_workspace_lease.py` 与 `test_start_local_web.py` 为真实文件系统的源码回归；**不构成** WPF+浏览器同时运行的双端验收，Supervisor、事务 CAS、会话附着、任务唯一所有权仍是 M3 的范围。

## 现有基础及不可过度外推的证据

隔离分支 explore/html-site-prototype 已有 E0 静态展示、E1 真实只读 API、E2 代理条件写入、E3 SQLite 事务级 CAS、E4 独立 Core owner、E5 本地受保护附着。Native SOURCE Lab 真实 WPF EXE + 浏览器读同一个合成 Core/SQLite，但 Core 仍由 WPF Host 拥有、外部 Python Runtime、合成 Knowledge，尚非 Portable/生产写入。

不得把 E1–E5 或 Windows Lab 的 PASS 直接升级成当前 main 的正式双端验收。

## 统一核心的强制不变量

D1. 同一个 Workspace 在任意时刻只有一个权威 Core 写入者和一个 Job Engine 权威调度器；不可让两个 UI 分别打开 SQLite 写入。
D2. Candidate/Source/Claim/Judgment/Decision/Offer 的权限、状态机、记录版本和审计由 Core 判断，不由载体 JS 单独决定。
D3. 所有重要写入通过事务级 revision/If-Match /冲突校验；读、校验、更新、审计属于单一原子事务；过期写入明确拒绝，不产生虚假审计。
D4. 两载体关闭、重连、Core 重启、退出、锁释放和任务恢复的生命周期必须是明确协议，不得意外停止仍在使用的另一载体。
D5. 本地 HTTP 绑定 loopback 且有来源、会话和授权保护；具备撤销、CSRF/Origin 防护。实验 E5 仅是设计输入。
D6. 共享版本和业务契约，**分别**记录 Windows 和 Local Web 的构建 SHA、工件 hash、运行环境和验收。
D7. 内部业务能力保真：Evidence、Decision、AI/OCR/ASR、Knowledge、备份/恢复、人工确认不可因适配浏览器减少。
D8. 任何双端集成测试都只用临时合成工作区，不触碰用户现存工作区。

## 发展路径与各轨任务

### M1 源与接口对齐（并行）
Core：整理正式 API 行为与数据版本、对照旧 v0.8.12-R2。
Windows：当前 SHA 的 Native 装配/基础生命周期/真实 GUI 操作。
Web：把 E1 由探索专用适配逐步改为正式 Core 路由，真实业务只读和操作路径。
共同退出：相同业务样本在两端具有相同资源身份/状态含义，且无第二套数据库。

### M2 业务闭环（并行）
Core：岗位→标准→候选人→Claim 核实→Scorecard→HumanDecision→Offer→联系/交接、失效/重申均有权威状态门禁。
Windows：完成相应真实 WPF 操作和恢复测试。
Web：完成等价真实 Chromium 操作，遇到无法实现的动作明确 BLOCKED。
共同退出：逐项 Capability Matrix 的 Browser、Native 证据齐全，不按按钮数量验收。

### M3 双端同时运行（并行）
Core：正式事务 CAS、独立 Supervisor、工作区锁、一次性会话、任务唯一所有权。
Windows + Web：同时读写相同 Candidate 和联系计划；冲突拒绝、修改标准后另一端旧 Decision 失效；关闭任一 UI 不误杀另一个；重复操作不重复 Job。
共同退出：同一机器同时运行、跨端冲突及异常退出测试 PASS。

### M4 包装与交付（并行）
Windows：同 SHA 完整 Native ZIP，包括审计过的 Runtime/Knowledge/Host，验证 OS 依赖。
Local Web：本机 Core 启动器+浏览器 UI 完整自洽包，记录 Python/依赖/端口前提；可考虑与 Windows 合包。
共同退出：两个真实可用启动入口、清楚数据路径/备份恢复、同版本异工件的 SHA/验收；不使用静态 demo 替代。

### M5 RC/GA
分别记录每个载体是否达到 RC 条件；争取同步发布，但**不能**用一端 PASS 给另一端背书。若某端阻断，保留另一端验收，不作假。

## 双端验收最低场景

T1 EXE 新建候选人→Browser 读取。
T2 Browser 写 Action Plan→EXE 读取。
T3 双端同版本并发写→一个成功、旧版本拒绝，审计准确。
T4 Browser 发布 Criteria 新 revision→EXE 旧 HumanDecision 失效。
T5 EXE 关闭→独立 Core/Browser 生命周期符合约定；Browser 关闭同理。
T6 两端触发同一 AI/OCR/ASR job→按幂等规则执行一次。
T7 Core 重启→两端重新附着，缓存与权限不串联。
T8 备份/恢复/Schema 迁移时，另一端不能对旧 workspace 继续写入。
T9 纯本地运行时，访问控制阻断跨站请求和未授权附着。
T10 同一候选人的 Source/Claim/Judgment/Decision 历史和导出在两端一致。

## 工程界面与合并

- main 是唯一产品集成主线；explore/ 只做风险试验，不独立发展完整招聘产品。
- 共同 Core/API 和两端的已证明增量以小 PR 并入 main，严禁一次性合并整个探索目录。
- 核心资源应单例：不要另起“Web 版知识库”“Web 版决策引擎”。
- 目标工程资源权重：约 40% 共同业务/可靠性，30% Windows，30% Local Web；按 P0 风险动态调整。
- 不用新 UI 框架、不进行业务内核重写和云端扩张作为并行开发的前提。

## 重要记录

实验详情：explore/html-site-prototype/explorations/html-site/README.md；Windows First Acceptance：docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md；Native Upgrade：docs/C11_NATIVE_CANDIDATE_UPGRADE.md；发行规程：docs/RELEASE_PROCESS.md。
