# SRW · 智能招聘工作台

SRW（Smart Recruitment Workbench）是一套 **local-first、evidence-centered、AI-assisted** 的招聘执行工具。它的目标不是把招聘判断自动化，而是把岗位标准、候选人材料、证据核实、面试、人工决定、Offer、联系跟进、Knowledge、AI/OCR/ASR 和备份恢复放进一个可追溯的本地工作区。

当前架构方向已经明确：**一个权威 SRW Core，Windows 与 Local Browser/HTML 只是两个客户端/载体；所有业务能力先进入 Core/API，再由前端调用。** 后续采用 API-first modular monolith 的渐进式重构，不另起新业务内核，不拆微服务，不建立两套数据库，也不为重构更换整套前端框架。详细设计见 [ADR-0002](docs/decisions/ADR-0002-api-first-modular-monolith.md) 与 [API-first 模块化 Core 路线图](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)。

> **Agent / 协作者必读**：修改前阅读 [AGENTS.md](AGENTS.md) 及关联 G1 文件。无主线保护期间允许 **Local Git 原 preflight** 或负责人批准的 **[GitHub API-native SHA→任务分支验证](docs/decisions/ADR-0003-github-api-native-preedit.md)**，后者无需在无 Git checkout 环境伪造 `git ls-remote`；两者均必须独立任务分支、更新 Source Manifest、PR、准确 HEAD CI 与复审，禁止 direct-push main。

## 当前产品化状态（2026-11-04 主线快照）

**本节仅属于 `main=70756e291d79858b97f7cadc7a5b20655b6b67b7` 的核查结果。** 每轮工作须重新查询 GitHub，不能把 README 当作实时 CI 或最新协作命令。最新产品裁决、任务、PR 和阻断以 [#103 主线指挥板](https://github.com/ALV522/-SRW-/issues/103) 及具体 [#206 用户体验任务](https://github.com/ALV522/-SRW-/issues/206) 为准。

| 维度 | 2026-11-04 实际情况 | 不可混淆的边界 |
| --- | --- | --- |
| 产品身份 | `VERSION=1.0.0-alpha10-convergence11`；Schema `v1_0014`；`development` | 不等于 RC/GA；`v0.8.12-R2` 仍是成熟功能保真参照 |
| main 已合并 | [#190](https://github.com/ALV522/-SRW-/pull/190)、[#191](https://github.com/ALV522/-SRW-/pull/191)、[#202](https://github.com/ALV522/-SRW-/pull/202)、[#205](https://github.com/ALV522/-SRW-/pull/205) 等 | 人工 Source→Claim、恢复保护等已在主线，不应重做 |
| 当前唯一 UI PR | [#207](https://github.com/ALV522/-SRW-/pull/207) HEAD `7140c75356d0`，**OPEN/HOLD** | 已隐藏面试技术 key 的工作在 PR，**尚未进入 main**；修订同 key 漂移、电话筛选完成、跨候选人 Scorecard 读取及定义展示仍需修复 |
| main 源码 CI | [Source Ubuntu+Windows](https://github.com/ALV522/-SRW-/actions/runs/41758256171)、[Chromium](https://github.com/ALV522/-SRW-/actions/runs/41758256084)、[Governance](https://github.com/ALV522/-SRW-/actions/runs/41758256057)、[Integrity](https://github.com/ALV522/-SRW-/actions/runs/41758256140)、[Host](https://github.com/ALV522/-SRW-/actions/runs/41758256060)、[Wheelhouse](https://github.com/ALV522/-SRW-/actions/runs/41758256059) 已报告 SUCCESS | PR #207 自己的 CI 与 main push CI 不是同一 SHA；Windows 源码测试不是 WPF GUI |
| Windows Native | 固定旧 `45148fa` 完整 ZIP 有 B/C 报告的分段 WPF 验收；更早 `e6fab773` ZIP 的 evidence_extract 曾 FAIL | **新 main / #207 工件的真实 Windows WPF、完整招聘链、恢复复验 NOT RUN** |
| 同 Core 双端 | Core/API 与 Local Browser 有合成流程证据 | #43 T1–T10 同工作区/会话/并发尚未验收 |
| RC 阻断 | #41/#42 完整人机链、#43 双端、#124 私有资产许可与两故障域、#130 真实物理故障 | 保持 `development`，不提升发行身份 |

**近期唯一业务优先序**：① B/C 在 #207 修复结构化面试/电话筛选/两份 Scorecard 正确性，由 A 复审后合规集成；② A 在不冲突文件域推进文档真实性、源码树/Native 体积审计；③ 新准确 SHA 的 WPF/WebView2 人工复验与候选人列表直达（S1b）。暂不实施 S2 全站 8→4/5 导航重做，也不开展新内核、SaaS、云登录。

**保留的历史证据**：旧基线、运行日志、PR/CI 链接与决策仍在 [GitHub 历史](https://github.com/ALV522/-SRW-/commits/main/README.md)、[DEVELOPMENT_STATE.md](DEVELOPMENT_STATE.md)、[验证目录](verification/) 及 [#103 评论](https://github.com/ALV522/-SRW-/issues/103)。此 README 不再堆叠 2026-10-21、10-29、11-02 等多组互相冒充“最新”的快照。

## Native 体积与保管

2026-11-04 对精确 main Git tree 的只读清点：**437 个受跟踪文件、2,916,869 原始字节**（含根 Manifest）；其中 `convergence_tests/`、`browser_acceptance/`、`docs/`、`verification/` 共 **1,436,109 字节**。这是未压缩的 Git 文件体积，**不是**安装包体积或实际可删字节。完整审计及安全裁剪的先决条件见 [仓库与 Native 体积审计](docs/REPOSITORY_FOOTPRINT_20261104.md)。

历史完整 Native ZIP 约 100 MB 的主要载荷来自**独立的 Python Runtime、五个 Knowledge 库和 Host**；Source Manifest 当前同时决定 SOURCE ZIP 与 Native 候选允许文件集，不能直接删除测试、审计文件或私有依赖来假装瘦身。#124 的 Runtime/Knowledge 保管、许可与第二故障域仍需独立验证，私有字节不上传 Git。详情见 [Native 外部资产保管](docs/NATIVE_ARTIFACT_CUSTODY_AND_REPRODUCIBILITY.md)。

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

## 近期路线

按 #103 当前用户任务导向：优先完成 #206 S1a（结构化面试与两份独立 Scorecard，无需 HR 输入内部 ID）；随后 S1b（从候选人列表进入正确动作）、最新 Native 真机复验。#63 渐进式 Core 模块化和 #43 同 Core 双载体继续保留，不以重构或全站 UI 重新设计抢主流程。

版本迁移 #44 独立进行；本架构转向不自动修改 VERSION。

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
