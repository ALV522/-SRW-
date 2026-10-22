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

## D1 单写者合同：独立后台入口不能绕过互斥

除 WPF Host 已持有工作区租约的 `--workspace-lock host` 模式外，直接运行 `scripts/run_local.py --workspace-lock backend` 的 C11 写入者，必须先按 Local Web 的既定顺序取得 legacy `.srw-instance.lock` 文件锁和共享 `data/app.lock` 原子目录租约，**随后**才能执行 pending restore、打开 SQLite 或启动后台任务。租约贯穿 Uvicorn 整个生命周期，异常退出须释放自己的租约；live/foreign/corrupt 锁必须拒绝，不能删除其他写入者锁。Windows Host 负责的 backend 不重复获取其父 Host 已经持有的租约。

这仅补齐此前 #59 中的独立 backend 入口例外，不改变核心身份、SQLite Schema、Host 权威进程或 Legacy 的历史行为。该合同以 `convergence_tests/test_standalone_backend_lease.py` 的纯合成测试验证；并不代表单独 Supervisor、CAS、Origin/CSRF、Web+EXE 同时共用同一 Core 的正式验收，仍需 #43 后续工作。

### M1 安全增量：直接 Core 启动的本地边界与 WPF Host 身份

`run_local.py` 直接启动的 C11 Core 不再接受 `0.0.0.0`、外部网卡、主机名或 IPv6 wildcard，HTTP 只能在 `127.0.0.1` 的 1024–65535 端口绑定；输入不合规时必须在创建工作区、恢复备份或打开 SQLite 之前拒绝。

`--workspace-lock host` 是**仅供真正 WPF Host 子进程使用**的例外：除需要 instance/session/token 环境身份外，还需看到活跃的 schema-v2 `data/app.lock`，其 edition、父 PID、instance_id、session_id、端口与工作区路径必须与启动上下文匹配。单靠伪造三个环境变量不得绕过工作区单写者租约。WPF Host 在启动 backend 前已获取租约并更新端口，故不需要在 backend 二次获取。此检查限制误配置或不受支持的独立进程，不能替代针对同一 OS 用户下恶意进程的完整认证。

`convergence_tests/test_standalone_backend_lease.py` 使用完全合成的临时文件夹、伪 Uvicorn 测试这些拒绝/合法路径；仅为 Source/API 合同验证。**本增量不代表** Windows GUI 实机通过，亦不替代 #43 正式 Origin/CSRF/会话撤销、CAS、独立 Core Supervisor 或同一 Core 双载体联调。

## 现有基础及不可过度外推的证据

隔离分支 explore/html-site-prototype 已有 E0 静态展示、E1 真实只读 API、E2 代理条件写入、E3 SQLite 事务级 CAS、E4 独立 Core owner、E5 本地受保护附着。Native SOURCE Lab 真实 WPF EXE + 浏览器读同一个合成 Core/SQLite，但 Core 仍由 WPF Host 拥有、外部 Python Runtime、合成 Knowledge，尚非 Portable/生产写入。

不得把 E1–E5 或 Windows Lab 的 PASS 直接升级成当前 main 的正式双端验收。

## API-first 边界（ADR-0002）

双载体不再仅理解为“两个界面连接同一个数据库”，而是两个客户端连接**同一个业务 API / Application / Domain**。从本路线图起，新增业务能力默认先进入 Core，再由 WPF/WebView2 与 Browser 调用。

- Windows Host 不实现 Candidate/Decision/Offer 状态机，只负责 Core lifecycle、workspace/session、WebView2/native integration；
- Browser UI 不成为唯一业务门禁，所有权威 mutation 必须由 Core 重新验证；
- API route 按 operator use case 提供稳定 contract；内部 helper/repository 不机械暴露；
- `fullworkbench.py` 与 `app.js` 的拆分由 [API-first 模块化 Core 路线图](API_FIRST_MODULAR_CORE_ROADMAP.md) 渐进推进，默认保持现有 URL/Schema/业务语义；
- Supervisor/session/CAS 属于统一 Core 生命周期，不是“Web 专用后端”；
- 未来 CLI/Agent/Automation 若加入，也必须使用相同 Core contract，不得绕过审计、revision 或人工决定边界。

因此 #43 的最终成功标准不是“Windows 与网页都能打开”，而是两者作为真正客户端，对同一权威 Core 的状态、错误、并发和审计语义一致。

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

### D5: local HTTP Fetch Metadata / ambiguous forwarding fail-closed (#43)

The shared `LocalBoundaryMiddleware` now rejects browser write requests (`POST`,
`PUT`, `PATCH`, `DELETE`) with `Sec-Fetch-Site: cross-site` or `same-site`,
**even when Origin and Referer are omitted**. Same-origin browser requests and
WPF native API requests without Fetch Metadata retain their existing behavior;
explicit non-local Host and mismatched Origin/Referer continue to be rejected.
Ambiguous duplicate Host, Origin, Referer and Fetch Metadata headers fail closed,
preventing intermediary/application disagreement about request provenance.

The regression `test_convergence09.py` first demonstrated that these synthetic
requests previously **created projects successfully**, then checks that Core
now rejects them without changing legitimate same-origin/native writes.
This is a narrowly scoped browser boundary hardening increment: the local
browser does **not** yet have a supervisor-issued bearer session, authenticated
attachment/revocation, or full CSRF token flow; it does **not** protect against
an already-malicious process running as the same OS user. The existing
workspace single-writer lease and eventual Supervisor/Session/CAS track remain
separate release gates; real WPF GUI acceptance is still NOT RUN.
