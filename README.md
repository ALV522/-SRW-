# SRW · 智能招聘工作台

> **2026-11-10 主线身份快照（合并 #251 后）**：main [`2a330d354fcff7b0e920892ec3cc477b27286632`](https://github.com/ALV522/-SRW-/commit/2a330d354fcff7b0e920892ec3cc477b27286632)，VERSION `1.0.0-alpha10-convergence11`，Schema `v1_0014`，development，**非 RC/GA**。#248（浏览器 API client fail-closed 依赖）和 [#251](https://github.com/ALV522/-SRW-/pull/251)（SQLite/browser fixture 清理、面包屑负例）已合并；对合并前准确 HEAD 的 Source/Chromium/Governance CI 完成成功，新 main 的 push CI 与新 Windows ZIP 应以其自己的 SHA/工件重新验证，不继承旧结果。[#250](https://github.com/ALV522/-SRW-/pull/250) 已合流至此 main，准确 HEAD `390bc84995cd06dad0d95b2c39b2d78bbe5a6ecc`，源/浏览器 CI 执行中、非作者对新 HEAD 的复核待办；[#252](https://github.com/ALV522/-SRW-/pull/252) UX-2a 旧 HEAD `fa4b0321` 内容复核 ACCEPT，但 Windows [#159](https://github.com/ALV522/-SRW-/issues/159) 25 秒真实退出失败与旧基线仍使其 HOLD。B/C 暂不可用，A 先处理非冲突事务；同帐号工作轨非独立 GitHub 审批。#43/#124/#130/#159 继续阻断 RC。动态实况以 [#103](https://github.com/ALV522/-SRW-/issues/103)、[Actions](https://github.com/ALV522/-SRW-/actions) 和目标 PR 准确 HEAD 为准。

> **2026-11-10 同 SHA 仓库体积审计**：读取上述 main 的 Git tree（`recursive=1`, `truncated=false`），454 个源码/文档 blob，未压缩共 **3,228,618 B**；最大单文件 `frontend/dist/app.js` 为 157,511 B，`backend/srw/api/fullworkbench.py` 为 55,021 B。这**不是 Native ZIP**。已知上一正式 Windows ZIP 对应旧 main `8a99d7f8`，102,260,233 B、SHA256 `7299031f563c05a4eecea45354bed18e673906a7110b69f7d3f31a6d428f6f74`，在 1920×1200/135% 目标机完成窗口、侧栏、退出、DB 独占四项 PASS（见 [#42](https://github.com/ALV522/-SRW-/issues/42)），但不等于当前 main 的 WPF/全业务/跨载体验收。未取得同一工件的 Runtime/Knowledge 压缩分项与许可/可删证明，不宣称 ZIP 已瘦身，不清理私有工件。

SRW（Smart Recruitment Workbench）是一套 **local-first、evidence-centered、AI-assisted** 的招聘执行工具。它的目标不是把招聘判断自动化，而是把岗位标准、候选人材料、证据核实、面试、人工决定、Offer、联系跟进、Knowledge、AI/OCR/ASR 和备份恢复放进一个可追溯的本地工作区。

当前架构方向已经明确：**一个权威 SRW Core，Windows 与 Local Browser/HTML 只是两个客户端/载体；所有业务能力先进入 Core/API，再由前端调用。** 后续采用 API-first modular monolith 的渐进式重构，不另起新业务内核，不拆微服务，不建立两套数据库，也不为重构更换整套前端框架。详细设计见 [ADR-0002](docs/decisions/ADR-0002-api-first-modular-monolith.md) 与 [API-first 模块化 Core 路线图](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)。

> **Agent / 协作者必读**：修改前阅读 [AGENTS.md](AGENTS.md) 及关联 G1 文件。无主线保护期间允许 **Local Git 原 preflight** 或负责人批准的 **[GitHub API-native SHA→任务分支验证](docs/decisions/ADR-0003-github-api-native-preedit.md)**，后者无需在无 Git checkout 环境伪造 `git ls-remote`；两者均必须独立任务分支、更新 Source Manifest、PR、准确 HEAD CI 与复审，禁止 direct-push main。

## 历史产品化状态（2026-11-06，SHA 固定快照）

> **历史事实补充 · 2026-11-06（main `3f6dc196ba45b493cee0eee4be02db0ea162fdbf`；非 RC/GA）**：六类 main push CI 已对该 SHA 报告 SUCCESS；B/C 在由该 main 组装的完整 Native ZIP（**102,222,665 B，SHA256 `829d1264e65854d20aac00d1c9abf227f10e05927cd930361ed314505dfb7858`**）上实际操作了 WPF/WebView2：发布标准→创建候选人→人工核实与 Judgment→HumanDecision advance→两个面试事件与同一事件的两份独立 Scorecard，以及备份、恢复和正常退出/释放锁。**此 PASS 仅对指定 ZIP、机器和步骤有效**，不包括 Offer、真实 Provider、物理断电、双载体同 Core。实机又发现 **135% DPI 导致窗口标题栏和侧栏被屏幕裁切**：[PR #234](https://github.com/ALV522/-SRW-/pull/234) 对应 [#232](https://github.com/ALV522/-SRW-/issues/232)，有修复后 Win32 RECT；B/C 已在 PR merge-ref `80088e03` 的正式组装 ZIP（SHA256 `1eb71063b3081d60e01b9093341021a783a8dbe7d17f64773bb5b87773f8826c`）目标机复测三键、正常退出及 DB 独占 PASS。#234 已合并 main `b1afe24b`，其新主线身份的正式 ZIP 仍待独立重建和验收；[已关闭 #233](https://github.com/ALV522/-SRW-/issues/233) 的 CSS 横向滚动归因已被原始 DOM 测量推翻。另有独立的**用户验收阻断** [#235 工作台 UI 信息层级](https://github.com/ALV522/-SRW-/issues/235)：允许现有前端骨架的可逆重排，不重写 Core、删除能力或更换框架。A 的 [#230 WPF Host opt-in 会话附着](https://github.com/ALV522/-SRW-/pull/230) 精确 HEAD 源码/浏览器/Host CI 已绿，但非作者安全复核与新 Native 真实 ON 仍 PENDING；[#231 Windows Chromium 退出超时诊断](https://github.com/ALV522/-SRW-/pull/231) 精确 HEAD 源码/浏览器/Governance CI 已绿，但并未修复 #159 的偶发 hang。#124 许可及独立故障域、#130 物理恢复仍阻断发行。**下面 `aa828635` 表格继续作为其对应的历史快照，不可覆盖本段新事实。**

> 本段是 **main `aa82863528d0ee78d102371433e6cb679429516e`** 的历史定位，不会自动随未来合并更新。实时工作状态以 [#103 协作板](https://github.com/ALV522/-SRW-/issues/103)、[PR 队列](https://github.com/ALV522/-SRW-/pulls) 和 [GitHub Actions](https://github.com/ALV522/-SRW-/actions) 的准确 SHA 为准。根 Source Manifest **446 项**；该提交的 main push CI 在本次文档编写时并未全部结束，**不预报六项 PASS**。

| 维度 | 已合入 main / 尚缺证据 |
| --- | --- |
| 产品身份 | `1.0.0-alpha10-convergence11` / Schema `v1_0014` / development；非 RC/GA。历史 `v0.8.12-R2` 为功能保真对照。 |
| 招聘业务 | #207/#209/#211/#212/#220 交付无内部 Criteria ID 的面试/面评可用路径；[#221](https://github.com/ALV522/-SRW-/pull/221) 完成 IA-1 侧栏 6→3、项目页签 8→3；[#224](https://github.com/ALV522/-SRW-/pull/224) 生产 Scorecard 已使用 project/candidate/event scoped Core GET。 |
| 已确认合流 | [#227](https://github.com/ALV522/-SRW-/pull/227) 已合并：跨项目面评阻断→准确原候选人/面试事件一键恢复→返回原项目并保留筛选，Core 归属 TOCTOU 仍 fail-closed；对应 PR HEAD Ubuntu/Windows Source、Ubuntu Chromium、Governance 和 B/C Windows 单文件复核全通过。**主线新 SHA 与 Native WPF 需独立验证**。 |
| 已集成的回归与 Windows 工具链 | [#223](https://github.com/ALV522/-SRW-/pull/223) Claim 持久化/Scorecard 隔离回归已入主线；[#226](https://github.com/ALV522/-SRW-/pull/226) Windows Wheelhouse 13 个依赖固定哈希的校验已入主线；[#228](https://github.com/ALV522/-SRW-/pull/228) Windows Chromium 独立单文件 `test_flows.py` **17 条**与全套 **52 条（2 skip）** 双验收已入主线；以上各 PR 精确 HEAD CI 已全绿，**不代表新 main 的 WPF Native 实测**。 |
| 当前发行阻断 | #42 新 SHA Windows WPF/完整招聘业务及真实备份恢复、#43 EXE+Browser 同 Core 会话、#124 私有 Runtime/五库许可与第二故障域、#130 物理恢复；均不得从 Source 或 Chromium PASS 推出已完成。 |

**当前执行队列**：#227/#223/#226/#228 已集成；下一优先是 #42 最新 main Windows Native 组装及完整招聘/恢复实机、#43 M3B 单一 Core 的 WPF+Browser 会话同源验收、#124 受许可 Runtime/Knowledge 保管与 #130 物理恢复；#159 Windows graceful-stop 诊断仍需独立跟进。IA-2/IA-3 暂不以新界面取代上述业务闭环。普通工程更改由 A 执行，涉及产品不变量与正式发行再向负责人升级。

## Native 体积与保管

主线 `aa828635` 的只读 Git tree 实测：**447 个 blob、3,083,875 B 未压缩源码与文档（Manifest 446 条）**；2026-11-04 旧基线 `70756e2` 为 437 个 blob / 2,916,869 B，`8e7f9b6` 为 439 个 blob / 2,993,287 B。复算方法：GitHub `GET /repos/ALV522/-SRW-/git/trees/aa82863528d0ee78d102371433e6cb679429516e?recursive=1`，确认 `truncated=false`、只计 `type=blob` 的 `size` 之和。**这不是** Native ZIP 的压缩体积或实际可删字节；不同 SHA 不可混算。完整审计及安全裁剪的先决条件见 [仓库与 Native 体积审计](docs/REPOSITORY_FOOTPRINT_20261104.md)。

历史完整 Native ZIP 约 100 MB 的主要载荷来自**独立的 Python Runtime、五个 Knowledge 库和 Host**；Source Manifest 当前同时决定 SOURCE ZIP 与 Native 候选允许文件集，不能直接删除测试、审计文件或私有依赖来假装瘦身。#124 的 Runtime/Knowledge 保管、许可与第二故障域仍需独立验证，私有字节不上传 Git。详情见 [Native 外部资产保管](docs/NATIVE_ARTIFACT_CUSTODY_AND_REPRODUCIBILITY.md)。

\nWindows Wheelhouse 的 13 个 wheel 已由 #226 采用人工审阅 SHA256 固定。未来升级依赖必须单独提出 PR，取得原始下载字节、独立核对来源及实际哈希后**人工修改** `build-lock/windows-c11-wheelhouse.sha256`，再运行 Windows Wheelhouse 离线安装/导入校验；不可让 CI 自动下载新包、自动改锁、再用自己刚写的锁自证。\n
新增只读、离线的 [Native ZIP 体积分析器](scripts/report_native_zip_footprint.py)：`python scripts/report_native_zip_footprint.py --zip <旧候选.zip> --zip <新候选.zip>`。它只扫描 ZIP central directory、统计 Runtime/Knowledge/Host/Source 分组压缩字节并计算整包 SHA256，不解压、修改、运行或上传私有文件。该报告**不代表** ZIP 完整性验收，必须另用 `scripts/native_payload.py audit-zip`；在实际取得前后大小及真实 Windows 验收之前，不能宣称已瘦身。


## 产品不变量

SRW 的长期能力扩展不能突破以下边界：

- 人类控制候选人推进、HumanDecision 与 Offer 关键动作；AI 只能辅助；
- Source、Claim、核实、Judgment、Decision Context 和历史决定必须保留来源与版本关系；
- 缺失证据不是否定事实，冲突证据不能被静默合并；
- MaterialRevision / ProtocolRevision 变化后，旧决定不能冒充当前决定；
- v0.8.12-R2 中实际有价值的岗位/候选人/Evidence/Interview/Decision/Offer/运营/Knowledge/AI/OCR/ASR/备份能力是功能保真对照；
- 用户本地数据、SQLite、简历、密钥、Knowledge、日志不得意外进入 Git/CI/工件；
- Windows 与 Browser 共享一个权威 Core、Workspace、业务状态和审计，不维护两套“真相”；
- 测试、升级、探索程序不得静默打开或修改现有用户工作区。

权威条款见 [PRODUCT_CHARTER.md](docs/PRODUCT_CHARTER.md)。

## 目标架构：Core 是产品，前端是客户端

SRW 的长期逻辑结构：

```text
Windows WPF/WebView2       Local Browser       future CLI / Agent
          \                    |                    /
           +--------------- SRW API ---------------+
                              |
                     Application Use Cases
                              |
                           Domain
                              |
       +----------------------+----------------------+
       |                      |                      |
 SQLite / Blob          Jobs / Providers        Knowledge
       |                      |                      |
       +-------------- authoritative Workspace -----+
```

职责原则：

| 层 | 主要职责 | 不应该做什么 |
|---|---|---|
| Domain | Candidate、Protocol、Evidence、Decision、Interview、Offer 的状态语义与不变量 | 依赖具体 UI |
| Application | 面向操作者的业务用例、事务编排、审计/lineage | 变成 HTTP/DOM 代码 |
| Infrastructure | SQLite、Blob、Knowledge、Provider、OCR/ASR/AI、Jobs、Backup | 决定 UI 行为 |
| API | Request/Response/Error/Revision/Session/Concurrency 契约 | 重复实现业务状态机 |
| Carrier | Windows/Browser 的 Core 生命周期、workspace/session/native integration | 拥有 Candidate/Decision/Offer 规则 |
| Frontend | 展示、输入、导航、客户端视图状态 | 成为唯一业务门禁 |

接口按**业务动作**设计，而不是把内部函数机械暴露为 endpoint。例如 `PublishProtocol`、`ReviewClaim`、`RecordHumanDecision`、`TransitionOffer` 是合理的应用用例；数据库 helper、hash 计算或 repository 内部查询不应该成为公共接口。

## 为什么现在要做结构性重构

当前 C11 并不是“一个完全没有结构的巨石”。相反，`backend/srw/modules/` 已经有 candidate、protocol、decision、identity、work、knowledge、planning、feedback 等领域模块；问题主要发生在入口层重新聚合。

以下数字是 **2026-10-21 重构起点的历史静态审计**，用于说明当时的拆分动因，不是当前文件规模：

- `backend/srw/`：127 个文件，约 596 KB；
- `backend/srw/modules/`：17 个业务模块目录；
- `backend/srw/api/*.py`：141 个 `Route(...)` 声明、129 个不同路径模板；
- `backend/srw/api/fullworkbench.py`：约 126.8 KB / 1723 行；
- `backend/srw/api/app.py`：约 38.6 KB / 737 行；
- `frontend/dist/app.js`：约 128.8 KB，并集中页面、状态和大量 API 请求；
- `desktop/SRW.Desktop/` 已较接近薄 Host 形态。

因此本轮不是 `src2`/新 Core 重写，而是 **Strangler Refactoring**：先建立 contract 安全网，再逐域迁出大型聚合层，保持现有 URL、Schema、数据和业务语义，最后删除已经被等价替代的旧聚合代码。

## 后续开发的默认顺序

任何新增或修复原则上遵循：

```text
业务动作 / operator outcome
        ↓
产品不变量 / Domain rule
        ↓
Application use case
        ↓
API contract
        ↓
Browser / Windows client
        ↓
各自真实验收
```

这意味着：

- 新业务逻辑不再默认直接加进 `frontend/dist/app.js`；
- 新 HTTP 能力不再默认继续膨胀 `fullworkbench.py`；
- Windows Host 不新增招聘状态机；
- 浏览器 UI 可以提前禁用非法动作，但 Core/API 必须再次权威校验；
- AI/OCR/ASR 通过 Provider/Job capability 扩展，不让页面直接拥有 Provider 语义；
- 未来 CLI、Agent、自动化如果加入，应调用同一应用/API 能力，不绕过 audit、human boundary 与 revision control。

## 当前仓库地图

| 位置 | 当前角色 | 发展方向 |
|---|---|---|
| `backend/srw/kernel/` | ID/hash/clock/error 等基础原语 | 保持小而稳定 |
| `backend/srw/modules/` | 领域能力与业务服务 | 继续成为业务核心，不复制到客户端 |
| `backend/srw/surfaces/` | Candidate/Workbench 等读模型与产品投影 | 保持 read-model 职责 |
| `backend/srw/api/` | 当前 HTTP Core/route installers | 逐步拆成薄 route + contract |
| `backend/srw/runtime/` | DB、Schema、Jobs、Backup、Local boundary | 基础设施/运行期边界 |
| `backend/srw/providers/` | AI Provider contract/runtime | 继续作为 Provider abstraction |
| `frontend/dist/` | 当前 Browser/WebView2 前端 | 统一 API client 后按 feature 渐进拆分 |
| `desktop/SRW.Desktop/` | WPF/WebView2 Host | 收敛到 lifecycle/workspace/session/native integration |
| `scripts/` | 启动、装配、完整性、恢复和验收工具 | 不承载第二套业务核心 |
| `convergence_tests/` | Core/API/供应链回归 | 作为重构安全网 |
| `browser_acceptance/` | 真实 Chromium 操作验收 | 保护用户级行为 |
| `verification/` | 历史/当前证据 | 不把历史结果冒充新 SHA PASS |
| `docs/` | 产品、治理、架构、验收和历史 | 权威路线与证据边界 |

## 当前业务范围

主业务链仍是：

**建岗/Criteria → Candidate Intake → Source/MaterialRevision → Claim/人工核实 → Interview/Scorecard → HumanDecision → Offer → 联系/交接 → 上下文变化后的失效/复核/重申 → 备份恢复。**

此外保留 Knowledge、Provider、OCR/ASR、身份复核、判断纠错、任务队列、项目导入导出和诊断能力。各项真实验收边界见 [CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)。

## Windows 与 Local Web

### Local Web 源码预览

完整 checkout 后，可以使用显式独立工作区启动现有 C11 Core + 前端：

```bash
python scripts/start_local_web.py --workspace <绝对路径的独立工作区>
```

详见 [LOCAL_WEB_SOURCE_PREVIEW.md](docs/LOCAL_WEB_SOURCE_PREVIEW.md)。它不是静态 HTML，也不是正式 Local Web Release；当前同一 workspace 仍必须遵守单一 Core writer/lease 规则。

### Windows

Windows WPF/WebView2 Host、Native 候选装配和 Runtime/Knowledge 审计已有工程基础，但旧 Windows GUI 验收不能替代当前 main 的新工件验收。参见 [Windows GUI 首次实机证据](docs/WINDOWS_GUI_FIRST_ACCEPTANCE.md) 与 [Native candidate upgrade](docs/C11_NATIVE_CANDIDATE_UPGRADE.md)。

长期目标不是“Windows 版 Core”和“Web 版 Core”，而是：

```text
Windows Host ─┐
              ├── same SRW Core / same Workspace authority
Browser ──────┘
```

## 2026-11-09 历史路线快照

截至 2026-11-09 的主线事实：`main=f4afefc6f5caed0a9cbfcbb8ed1b414c4890e414`，VERSION 仍为 `1.0.0-alpha10-convergence11`、Schema `v1_0014`、development；该 main 的 Source/Chromium/Governance/Repository Integrity/Windows Host/Offline Wheelhouse 六类 push CI 已完成并成功，但这**不等于**当前 SHA 的 WPF/Native GUI、Provider、物理断电恢复或双载体实机 PASS。

当前产品 P0 是 [#235](https://github.com/ALV522/-SRW-/issues/235) 的工作台信息层级与主任务路径。第一切片 [PR #237](https://github.com/ALV522/-SRW-/pull/237) 仍为 OPEN/HOLD；本次文档更新开始时准确 HEAD 为 `43ef1fab2479aaa64a34887b07726f08313dbb10`，相对已验证的 `164f996d` 只增加真实 Chromium 场景测试与 Manifest 更新，生产代码未继续扩张。B/C 暂不可用期间不以 A 自己的同账号复核冒充独立 reviewer，也不继续向 #237 叠普通 UI 微优化。

下一产品切片是 [#240](https://github.com/ALV522/-SRW-/issues/240)：在 #237 正式集成后，从**新的 main** 将“首页起 9 次显式点击”的可比较面试/面评路径压缩到目标 ≤6；不得为凑点击数删除人工核实、对象归属、版本/审计和人类决定门禁。A 同期独立推进 [#159](https://github.com/ALV522/-SRW-/issues/159) Windows Core 偶发退出诊断与 [#63](https://github.com/ALV522/-SRW-/issues/63) 的小步模块化/体积取证/仓库治理；[#241](https://github.com/ALV522/-SRW-/pull/241) 已合入只读 Native ZIP footprint 取证工具，但尚无证据证明完整 Native ZIP 已实际瘦身。

发行阻断保持：[#43](https://github.com/ALV522/-SRW-/issues/43) 双载体共享 Core 实机、[#124](https://github.com/ALV522/-SRW-/issues/124) Runtime/Knowledge 工件保管与许可、[#130](https://github.com/ALV522/-SRW-/issues/130) 物理恢复、[#159](https://github.com/ALV522/-SRW-/issues/159) 偶发退出根因。版本迁移 #44 独立进行；任何文档/架构清理都不自动修改 VERSION。

完整路线见 [ROADMAP.md](docs/ROADMAP.md)；重构细节见 [API_FIRST_MODULAR_CORE_ROADMAP.md](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)。

## 明确的非目标

当前不做：

- 全面业务内核重写；
- 新 UI framework 大迁移；
- 微服务 / Kubernetes / 消息总线式基础设施；
- Windows/Web 两个 SQLite 再双向同步；
- 多仓库拆分；
- SaaS、云登录、多租户、企业 ATS 平台扩张；
- 动态第三方插件 marketplace；
- AI 自动产生权威录用决定。

## 开发验证

源码开发基线：Python 3.12 + Node.js 22。

```bash
python -m pip install -r requirements-ci.txt
python scripts/check_source_integrity.py
python scripts/check_release_truth.py
python scripts/run_convergence_verification.py
```

真实 Chromium 验收由 `.github/workflows/browser-e2e.yml` 执行。修改任何受跟踪文件，包括文档，都必须更新 `SOURCE_MANIFEST.sha256`；`SOURCE_RECOVERY_MANIFEST.sha256` 是历史证据，不得修改。

## 文档导航

- [AGENTS.md](AGENTS.md)：所有 Agent 的强制入口；
- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)：产品与事实基线；
- [PRODUCT_CHARTER.md](docs/PRODUCT_CHARTER.md)：不可突破的产品不变量；
- [ADR-0001](docs/decisions/ADR-0001-single-authoritative-core.md)：一个权威 Core、双载体；
- [ADR-0002](docs/decisions/ADR-0002-api-first-modular-monolith.md)：API-first 模块化单体；
- [API_FIRST_MODULAR_CORE_ROADMAP.md](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)：专项重构计划；
- [ROADMAP.md](docs/ROADMAP.md)：产品总路线；
- [CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)：业务能力与验收边界；
- [DUAL_CARRIER_PLAN.md](docs/DUAL_CARRIER_PLAN.md)：Windows/Browser 共用 Core；
- [ACCEPTANCE_PLAN.md](docs/ACCEPTANCE_PLAN.md)：业务与工件验收；
- [VERSION_POLICY.md](docs/VERSION_POLICY.md)：版本/SHA/Schema/carrier/release 身份；
- [DEVELOPMENT_GOVERNANCE.md](docs/DEVELOPMENT_GOVERNANCE.md)：Issue→PR→验收流程；
- [RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)：发布与回滚。

历史 `v0.8.12-R2` 是能力完整性对照，不是当前源码或发行版本。任何“已实现”“已通过”“已发布”的说法都必须回到准确 SHA、环境和工件证据。
