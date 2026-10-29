# SRW · 智能招聘工作台

SRW（Smart Recruitment Workbench）是一套 **local-first、evidence-centered、AI-assisted** 的招聘执行工具。它的目标不是把招聘判断自动化，而是把岗位标准、候选人材料、证据核实、面试、人工决定、Offer、联系跟进、Knowledge、AI/OCR/ASR 和备份恢复放进一个可追溯的本地工作区。

当前架构方向已经明确：**一个权威 SRW Core，Windows 与 Local Browser/HTML 只是两个客户端/载体；所有业务能力先进入 Core/API，再由前端调用。** 后续采用 API-first modular monolith 的渐进式重构，不另起新业务内核，不拆微服务，不建立两套数据库，也不为重构更换整套前端框架。详细设计见 [ADR-0002](docs/decisions/ADR-0002-api-first-modular-monolith.md) 与 [API-first 模块化 Core 路线图](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)。

> **Agent / 协作者必读**：开始任何修改前先读 [AGENTS.md](AGENTS.md)，并按其顺序阅读产品宪章、开发治理、版本政策、能力矩阵、双载体计划、验收计划和无保护开发协议。`main` 当前未启用 GitHub Branch Protection；必须从最新 main 建任务分支、运行 `python scripts/agent_preflight.py --issue <Issue号> --acknowledge-reading`、走 PR，并以同一 PR Head SHA 的适用 CI 为合并依据。

## 当前进展与路线图位置（2026-10-29 核查快照）

**我们处于“已有招聘业务 Core 的产品化收口”阶段：API/前端渐进拆分已落地多批，恢复与工件可靠性持续补强；当前关键路径是最新 Windows Native 工件实机验收，以及双载体会话安全接线。尚未进入 RC/GA。** v0.8.12-R2 仍是功能保真对照，不能用新界面或更多治理文件替代成熟业务能力。

源码基线：[`979863218c7fbcfc2c3fd5ff041237f0110c4350`](https://github.com/ALV522/-SRW-/commit/979863218c7fbcfc2c3fd5ff041237f0110c4350)（#165 已合并）；VERSION `1.0.0-alpha10-convergence11`，Schema `v1_0014`，release channel `development`。以下是该 SHA 的日期快照，不替代每轮读取最新 main。

| 总路线 / 专项阶段 | 已进入主线 | 尚未达到的完成条件 |
|---|---|---|
| **Track 0：业务完整性（#41）** | 结构化重评估及上下文守卫、归档/合并候选人的写入门禁、Source 哈希验证后读取、备份原子发布/验证后下载、恢复 journal 与 `FINALIZED_CLEANUP_PENDING` 终态（#110/#115/#127/#139/#149/#153） | 完整招聘链、Provider/OCR/ASR、备份恢复在当前准确 Native 工件上的真实操作验收；合成故障注入不等于真实 AV/断电验证 |
| **Track A：模块化 Core（#63），R0–R4** | 架构/契约安全网与多轮路由拆分；`api-client.js` 统一传输入口，`reevaluation.js`、`jobsetup.js` 分离 feature（#109/#110/#114） | R2 路由拆分继续收口；R3 应用用例层未整体完成；R4 仅部分 feature 拆出，不能称前后端重构全部完成 |
| **Track B：Windows Native（#42/#123/#124）** | Source/Host/Wheelhouse 构建、固定哈希装配、外部双副本校验工具及 Windows 文件身份修复（#157/#162）；历史特定工件有用户报告的 GUI/业务验收 | 当前 SHA 完整 Native ZIP 的 WPF/业务/恢复验收；两份独立故障域保管、干净 Windows 重建与五套 Knowledge 许可核实 |
| **Track C：共享 Core 双载体（#43），R5 / M3** | 单写者基础、纯 `SessionPolicy`、有界 `SessionRegistry`，根 SPA 路径与畸形 token 拒绝策略（#145/#158/#165） | **生产 HTTP gate 尚未接线，默认 OFF**；Host 身份通道、Browser cookie/CSRF attach、shutdown/business token 分离，以及 T1–T10 同机交叉验收 |
| **Track D：发行（#44），与 R6 包装相接** | 工件身份、构建与验收工具持续推进 | 正式版本迁移、两载体发布验收与负责人 RC/GA 裁决；可扩展接口长期目标不作为当前新增平台任务 |

总路线见 [ROADMAP](docs/ROADMAP.md)，R0–R7 见 [专项架构路线图](docs/API_FIRST_MODULAR_CORE_ROADMAP.md)，M1–M5/T1–T10 见 [双载体计划](docs/DUAL_CARRIER_PLAN.md)。这些阶段并行推进，不用一个未经定义的“完成百分比”替代退出条件。路线图的 Track A/B/C 是工作方向，协作中的 A/B/C 是责任轨，二者不能混同。

### 当前证据与交付物

- **该 SHA 的 CI**：[Source Gate](https://github.com/ALV522/-SRW-/actions/runs/40829730586) Ubuntu / Windows 均 SUCCESS；[Chromium](https://github.com/ALV522/-SRW-/actions/runs/40829730524)、[Governance](https://github.com/ALV522/-SRW-/actions/runs/40829730712)、[Repository Integrity](https://github.com/ALV522/-SRW-/actions/runs/40829730484)、[Host](https://github.com/ALV522/-SRW-/actions/runs/40829730574)、[Wheelhouse](https://github.com/ALV522/-SRW-/actions/runs/40829730494) 已 SUCCESS。该 SHA 的六类主线工作流均已成功；这些是源码、构建与浏览器证据，不等于 WPF 实机或双端验收。
- **最新 Source+Host kit**：[97986321 构建工件](https://github.com/ALV522/-SRW-/actions/runs/40829730574/artifacts/12877853965)，标记 `NO_RUNTIME`。它不包含 Runtime 和私有 Knowledge，**不是可直接运行的完整 Native Release**。已有逐字节校验证据及目标机装配步骤记录在 [#42](https://github.com/ALV522/-SRW-/issues/42#issuecomment-6489758901)；当前 SHA 的 WPF 实机、完整双端和私有数据重建仍未验收。
- **可靠性修复与诊断分开**：#153 已实现恢复后可重试清理；#162 已修复 Windows 文件身份误拒绝。#156/#164 只是增加浏览器保存/真实 Core 停机超时诊断，原始时序根因仍未知，见 [#154](https://github.com/ALV522/-SRW-/issues/154)、[#159](https://github.com/ALV522/-SRW-/issues/159)；重跑通过不代表根因解决。

### 接下来按什么顺序推进

1. **A：最新 Native 验收与数据可恢复性**——核对当前 main CI 终态，使用同一 SHA 的 Source+Host kit 和受限旧 Prepared ZIP 装配全新候选，完成 #42/#123 的 Windows 真实业务/证据/恢复验收；#124 独立副本和许可另行取证，不上传私有数据。
2. **C：双载体安全接线合同**——在现有 policy/registry 上明确 Host、Browser、raw ASGI 头、Origin/CSRF 和生命周期凭据边界，再以合成负例驱动原子接线。[#148](https://github.com/ALV522/-SRW-/pull/148) 保持 RED 测试合同，不单独合并，不提前开启 gate。
3. **B：有界工程效率修复**——[#166](https://github.com/ALV522/-SRW-/issues/166) 增量 manifest 工具及 Windows CRLF/Git index 一致性；仍执行全量完整性校验。七领域报告只是只读试点，根 `SOURCE_MANIFEST.sha256` 仍是唯一权威。

协作与集成以 [#103](https://github.com/ALV522/-SRW-/issues/103) 的最新分页回复和 [G1](docs/DEVELOPMENT_GOVERNANCE.md) 为准：准确 HEAD CI、非作者轨正式审查、P4 明确处置、合并后主线复验；同一 GitHub 账号下的轨道审查不等于平台独立审批。历史 [#101](https://github.com/ALV522/-SRW-/pull/101) 不整包合并；不为整理删除未评估的独有分支内容。

## 外部 Native 工件保管与可复现性（2026-10-26）

Native 输入已有固定哈希、Source/Host/Wheelhouse CI 与实机 Smoke，但不等于丢失外部 ZIP 后可独立恢复。历史 alpha10 依赖 5/13 的状态不等于当前 overlay 的 13/13。风险/保管校验/独立重建规划见 [Native Runtime/Knowledge 外部工件保管与重建](docs/NATIVE_ARTIFACT_CUSTODY_AND_REPRODUCIBILITY.md)（#124）；私有 Runtime、Knowledge、密钥和候选人数据不得上传 Public Git。

## 历史事实基线（2026-10-21，非实时）

以下为 **2026-10-21 的历史快照**（SHA `c0bc192e346ab16aeb6fa63e60a40c617274a188`），不是当前 main 或准确 CI；必须每次重新核验 GitHub SHA 与工件身份：

- Product/runtime version：`1.0.0-alpha10-convergence11`（历史旧格式，仍为 development）；
- Schema：`v1_0014`；
- Source Gate：Ubuntu / Windows Python 3.12 各 **241 tests，2 skipped，PASS**；
- Chromium：**10 个**真实浏览器 + C11 Core + 临时合成 SQLite 场景 PASS；
- Source integrity：**329** 条 SHA-256 清单 PASS；
- Windows Host rebuild / offline wheelhouse：当前 SHA 的构建门禁 PASS，但**不是**完整 Windows 产品验收；
- 已有真实 Windows GUI 基础证据仍来自历史特定候选工件，不能自动转移到当前 main；
- 当前并未达到 RC/GA，也没有正式证明同一 Core 下 EXE + Browser 的完整双端并发写入。

精确 CI：

- [Source Gate · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114875)
- [Chromium Business Acceptance · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114881)
- [Repository Integrity · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114802)
- [Windows Host Rebuild Candidate · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114984)
- [Windows Offline Wheelhouse · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114916)
- [Governance Contract · c0bc192e](https://github.com/ALV522/-SRW-/actions/runs/39470114808)

任何 PASS 只属于对应 SHA、环境和工件。Source/API、Chromium、Windows WPF、完整 Native/Portable、Web+EXE 双端、Provider/生产 Knowledge 必须分别记录。

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

当前推进不是“暂停业务，先重构半年”。四条线并行：

1. **业务真实性与功能保真（#41）**：继续关闭完整招聘链与异常路径；
2. **API-first 模块化 Core（#63）**：contract inventory → route decomposition → application use cases → frontend feature split；
3. **Windows 产品化（#42）**：当前准确 SHA 的 Native 工件、真实 WPF/业务/恢复验收；
4. **双载体统一 Core（#43）**：Supervisor、session、CAS、Job ownership、同机 EXE+Browser 交叉验收。

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
