# SRW 产品与架构总路线图

> **动态状态只维护一个入口**：当前 main、PR、CI 与 Windows 工件请看 [README 的事实入口](../README.md#事实入口与带-sha-的历史检查点)、[#103](https://github.com/ALV522/-SRW-/issues/103) 及 [Actions](https://github.com/ALV522/-SRW-/actions)。本页以下带日期或 SHA 的段落都是当时的历史检查点，不代表当前已验收能力；本页负责长期 Track/退出标准，不再复制 README 的动态状态段。

状态：ACTIVE · 长期架构路线（历史记录注明日期/SHA）

本路线图以 [PRODUCT_CHARTER](PRODUCT_CHARTER.md)、[ADR-0001](decisions/ADR-0001-single-authoritative-core.md) 和 [ADR-0002](decisions/ADR-0002-api-first-modular-monolith.md) 为约束。当前开发主线是 `main`；历史 v0.8.12-R2 是功能保真对照，不是当前源码身份。

> **2026-11-09 历史主线与执行优先序（main `f4afefc6f5caed0a9cbfcbb8ed1b414c4890e414`，非 RC）**：VERSION=`1.0.0-alpha10-convergence11`、Schema=`v1_0014`、development；该 main 的 Source Ubuntu/Windows、Chromium Ubuntu/Windows、Governance、Repository Integrity、Windows Host Build、Offline Wheelhouse push 工作流均已完成并成功。#63 的 [PR #241](https://github.com/ALV522/-SRW-/pull/241) 已合入只读 Native ZIP footprint 同文件身份取证工具，解决“目录统计与 SHA 可来自不同路径重开文件”的 TOCTOU 证据缺口；它不是 Native 裁剪器，也没有证明 Runtime/Knowledge 可删除、可再分发或完整 ZIP 已减小。产品 P0 [#235](https://github.com/ALV522/-SRW-/issues/235) 的第一结构切片 [#237](https://github.com/ALV522/-SRW-/pull/237) 仍 OPEN/HOLD；本次路线图更新开始时 HEAD=`43ef1fab2479aaa64a34887b07726f08313dbb10`，最新增量仅为真实 Chromium 场景测试/Manifest，没有新增生产字节。B/C 暂不可用时 A 不代签独立 reviewer，不将旧 HEAD CI 或历史 Native 证据迁移到新 HEAD。[#240](https://github.com/ALV522/-SRW-/issues/240) 作为下一独立 UX 切片，等 #237 正式集成后从新 main 开始，目标处理首页 9 次显式点击的可比较路径而不删除人工/审计门禁。#159 偶发 Windows Core 退出仍 UNKNOWN；#43/#124/#130/#159 继续阻断 RC。以下 11-06 及更早段落均作为带 SHA 的历史快照保留。

> **2026-11-06 真实进展与下一阶段优先序（主线 `3f6dc196ba45b493cee0eee4be02db0ea162fdbf`）**：#42 指定完整 Native ZIP（SHA256 `829d1264e65854d20aac00d1c9abf227f10e05927cd930361ed314505dfb7858`）已在实际 Windows WPF/WebView2 完成发布 Criteria→候选人→核实/Judgment→人工 advance→独立双面评、备份→恢复、正常关闭与锁释放。该证据替代下面旧的“新主线 WPF/备份恢复未跑”历史判断，但 Offer/Provider、#43 T1–T10 双载体、#130 断电、#124 许可/第二故障域未完成。**新增 P0 用户可用性门禁 [#235](https://github.com/ALV522/-SRW-/issues/235)**：现有产品的页面骨架与信息层级必须可逆改进且经过相同合成数据截图/真实 Chromium/Native 验收，不是另起新 UI 设计体系。近期顺序：[#232/PR #234](https://github.com/ALV522/-SRW-/pull/234) 已合并 main `b1afe24b`，PR merge-ref `80088e03` 的实机窗口、退出、DB 独占 PASS；main `b1afe24b` 的正式 Native ZIP 仍待新 SHA 复验。B/C 单执行者现在推进 #235 首页/项目工作区有界结构 PR；此前误判的 [#233](https://github.com/ALV522/-SRW-/issues/233) CSS 裁切归因已撤回关闭。A 独占 #230 WPF Host attach 的安全复核及后续 #43 双载体 Core 附着、#231/#159 退出超时诊断、主线合流与 #124/#130 发行边界。当前 #230 精确 HEAD CI 已绿但复核/Native ON 待测，#231 CI 已绿但 #159 根因未知；不得将这些源码绿灯升级为 RC/GA。以下按更旧 SHA 的进展仍保留为历史，不能直接作为当前否定或证明。

> **2026-11-06 核准快照（main `aa82863528d0ee78d102371433e6cb679429516e`，非 RC）**：Track 0/#41 已合入 #207/#209/#211/#212/#220/#221/#224/#227；最后一项是真实 HR 错项目 Scorecard 的“前往所属项目→原候选人/事件面评→返回原项目保留筛选”用户可见恢复路径，既有 scoped Core 校验、零额外写入和只读历史保护不变。#223 浏览器回归、#226 Wheelhouse 13 依赖人工哈希锁及 #228 Windows Chromium 单文件+全套真实 CI 门禁均已按各自准确 HEAD 验证并合入当前 main；新主线 Windows WPF、全套备份恢复仍 NOT RUN。IA-1 已合入，IA-2/IA-3 未交付。Track B/#42 当前准确 SHA 的 WPF/备份恢复尚无实机证据；Track C/#43 会话/双端互操作及 #124/#130 仍为 RC BLOCK；Track D 未进入 RC/GA。本段只保证变更状态及来源，main 新 SHA 六类 push CI 未全部终结前不声称全绿。以下 11-05/11-02/10-29 条目均是历史快照。

> **2026-11-02 历史审查快照（main `e6fab773127e49052aaec227b39a76f338c439ae`；开发中，不是 RC）**：Track 0/#41 的完整招聘/人工决策/恢复 Windows 实机链仍 P0；Track B/#42 只有该 SHA 的候选 ZIP 基础 WPF 有限实测（51 embedded tests，恢复组仅 1 项），#124 独立工件保管未闭环；Track C/#43 新 M3A Local Browser 会话 PR #187 HEAD `5bb3956` 通过 Source 双 OS 707/427 + Chromium/G1，处于复审/未合并，Windows WPF ON 和 EXE/Browser 同 Core M3B 实测未运行。Track A/#63 继续局部薄化，不能取代业务验收。**下一优先 #187 主线集成审查 → #41/#42 全业务 Windows 实测 → #43 M3B。** 本段为带 SHA 的历史快照，动态真相以 [#103](https://github.com/ALV522/-SRW-/issues/103) 为准；下文 2026-10-29 数字保留仅供历史追溯。

> **治理传输**：已批准 Local Git 和 [GitHub API-native 预编辑模式](decisions/ADR-0003-github-api-native-preedit.md) 两条等效的分支身份检查路径；PR/exact-HEAD CI 和安全/发行门禁不变。

## 1. 总目标

把 SRW 从功能丰富但入口层逐渐臃肿的 C11 原型，演进为一个可以真实交付、可恢复、可验证、可长期扩展的本地招聘产品：

- 一个权威 SRW Core；
- Windows WPF/WebView2 与 Local Browser 两个正式入口；
- API-first 的模块化单体；
- 完整招聘业务闭环和证据/人工决策保真；
- 可重复 Windows/Browser/双端验收；
- 清楚的版本、Schema、源码和工件身份；
- 不通过大重写牺牲 v0.8.x 已成熟能力。

## 2. 历史基线与证据边界

当前进度快照对应 main `979863218c7fbcfc2c3fd5ff041237f0110c4350`，VERSION `1.0.0-alpha10-convergence11`、Schema `v1_0014`、development。该段 SHA 为历史基线；准确 CI、工件链接及未验收边界请优先查看 [README 当前快照](../README.md) 和 [#103 实时协作板](https://github.com/ALV522/-SRW-/issues/103)，避免在多份文档重复维护测试计数。

**当前位置：Track 0 持续业务/恢复收口；Track A 的契约与路由拆分已有多批交付、前端共享 client 和两个 feature 已拆出，Application 层尚未整体完成；Track B 最新 Native 实机验收待完成；Track C 已有纯策略与 registry，但 HTTP/Host/Browser 安全接线未完成；Track D 尚未进入 RC/GA。**

历史特定工件的 WPF/业务验收保留，不迁移为当前 SHA 的 PASS。Source+Host NO_RUNTIME kit 是装配输入，不是可直接运行的完整 Native 产品。源码与合成测试完成不等于 T1–T10 双端实测完成。

## 3. 不再采用“P0 做完后才重构”的顺序

旧路线把大型 workbench/frontend 拆分放在较晚阶段。现在改为：**业务闭环、Windows 产品化、双载体和 API-first 边界收口并行推进。**

原因是新增功能如果继续进入巨型 route/frontend 聚合层，会不断增加之后的迁移成本；但反过来，也不能为了重构暂停业务验收。因此采用“小 PR、行为保真、边开发边收口”的方式。

## 4. Track 0 · 产品不变量与业务完整性（#41，最高优先级）

持续验证并关闭：

- Job/Criteria Draft 与显式发布；
- Candidate Intake、MaterialRevision、Source provenance；
- Claim review、criterion verification、冲突/缺失证据；
- Interview、独立 Scorecard、面试证据修订；
- HumanDecision、Decision Context、stale/reaffirm；
- Offer 合法状态迁移且不自动 hired；
- 联系、Action Plan、handoff；
- Archive/restore、Backup/restore；
- Knowledge、Provider、OCR/ASR 的真实降级和边界。

退出条件不是“API 已存在”，而是 Capability Matrix 对核心流程具备可复现 Source/API、Browser 和需要的 Windows 证据；未实测保持 NOT VERIFIED/BLOCKED。

## 5. Track A · API-first 模块化 Core（#63，从现在开始）

这是横向工程约束，不是另起一个版本。

### A0 架构治理

ADR-0002、专项路线图、README/ROADMAP/ARCHITECTURE 对齐。

### A1 API inventory / contract safety net

建立 method/path/owner/use-case 清单；对关键 mutation 明确 request、response、errors、revision/CAS、human boundary、audit 和 side effects。

### A2 后端 route decomposition

按业务域渐进拆 `backend/srw/api/fullworkbench.py`，默认保留 URL/方法/错误语义；`app.py` 收敛为 composition root。禁止复制 service/repository 逻辑到新 route。

### A3 Application use cases

为跨模块业务动作建立可直接测试的应用层事务边界，使 route 变薄；Domain invariant 仍保留在核心模型/服务。

### A4 Frontend decomposition

先统一 API client，再按 dashboard/projects/candidates/evidence/interviews/decision/offers/knowledge/settings 拆 feature。保留当前技术栈，不同时换框架。

### A5 Extensibility

AI/OCR/ASR/Knowledge/Parser/Export 等通过代码级 capability/provider abstraction 扩展。动态第三方插件系统不是当前目标。

完整退出标准见 [API_FIRST_MODULAR_CORE_ROADMAP.md](API_FIRST_MODULAR_CORE_ROADMAP.md)。

## 6. Track B · Windows Native 产品化（#42）

继续独立推进，不等待 Track A 完成：

1. 当前准确源码 SHA 的 Runtime/Knowledge/Host/Source 绑定；
2. 候选 ZIP 完整成员和 SHA 审计；
3. 真实 Windows 冷启动、重启、WebView2、后端就绪、关闭/锁释放；
4. 完整招聘主链点击操作；
5. PDF/OCR、ASR、Provider 故障/降级；
6. Backup/restore、升级、回滚和故障恢复；
7. 工件 SHA、测试机器、日志证据与 known issues 固化。

退出条件：一个**具体准确工件**在目标 Windows 上重复通过规定业务与恢复验收，才进入 RC 讨论。

## 7. Track C · 一个 Core、两个正式载体（#43）

此 Track 与 Track A 的 Application/API 边界直接耦合，但不另建 Web Core。

已经完成/正在形成的基础：共享 workspace lease、Local Web 真实 C11 API、WPF Host、探索 E1–E5 的 CAS/Core owner/session 设计输入。

仍需：

- 独立 Core Supervisor；
- Windows/Browser attach/revoke；
- Origin/CSRF/local authorization；
- 事务 revision/If-Match/CAS；
- 单一 Job Engine；
- backup/restore/migration 写入互锁；
- Core 重启和客户端重连；
- 同一真实 Windows 机器 EXE + Chromium 交叉读写。

退出条件：DUAL_CARRIER_PLAN T1–T10 真实通过，而不是仅有探索分支 PASS。

## 8. Track D · 版本、发行与维护（#44 + Release）

- 当前旧格式 VERSION 不因文档/架构重构自动升级；
- 产品 SemVer、Git SHA、Schema、carrier、artifact SHA、release channel 独立记录；
- Source ZIP、Host-only、Prepared Native、Native Candidate、Local Web、RC、GA 分开；
- 下一产品版本迁移必须原子更新 release truth 文件并重新验收；
- 正式 RC 要求 P0=0、功能冻结、两载体各自达到规定门禁，负责人明确批准。

## 9. 跨 Track 的工程规则

### 9.1 新功能默认落点

```text
operator outcome
→ Domain/Application
→ API contract
→ frontend/client
→ carrier acceptance
```

不得先把业务规则写死在某一前端。

### 9.2 重构方式

- Strangler Refactoring；
- 小业务域、小 PR；
- 先测试再迁移；
- URL/Schema 默认不变；
- 新旧代码短期并存可以接受；
- 行为等价证明后再删除旧聚合代码。

### 9.3 明确禁止

当前不开展：

- `new-core` / `src2` 全面重写；
- 微服务/消息总线/容器编排；
- 两套 SQLite 同步；
- 前端框架大迁移；
- 多仓库拆分；
- SaaS、云登录、多租户；
- 因架构拆分删除成熟 Evidence/Decision/Knowledge/AI/OCR/ASR/Backup 能力。

## 10. 2026-11-09 历史执行顺序（不代表最新队列）

1. **#235 / PR #237：先收口第一结构切片，不再无限增补。** 精确 HEAD CI、真实异步候选人/事件/Scorecard 负例与同 fixture 视觉证据必须绑定同一 SHA；B/C 暂不可用期间保持 OPEN/HOLD，不以 A 同账号自审代替独立工作轨结论。正式集成后再创建 #240 分支。
2. **#240：把首页到可验证人力动作的纯导航中转压缩。** 目标是把可比较场景的首页 9 次显式点击降到 ≤6；Core target、project/candidate/event ownership、旧 Published revision、人工核实/提交/审计必须保留，不能用前端缓存猜对象。
3. **#159：继续做可判别的 Windows 退出诊断，而不是放宽 15/25 秒门槛或强杀进程。** 保留历史真实 FAIL 与通过 rerun 的区别；测试专用 Proactor/Selector 对照若未复现，只能说明该轮未复现，不能关闭根因。
4. **#63：做真正有数据依据的仓库/Native 瘦身。** 源码 Git tree 只有约 3 MB 量级，约 100 MB Native 包的主要体积不在源码；先用 #241 工具对 Runtime/Knowledge/Host/Source 的压缩字节做准确分项，再在 #124 许可/保管边界内决定可裁剪项。README/ROADMAP/DEVELOPMENT_STATE 只保留一个“当前”事实入口，旧 SHA 保留为历史证据，不再让旧快照冒充现状。
5. **#43/#124/#130：作为发行阻断并行保留。** 一个 Core 两载体真实交叉写入、私有 Runtime/Knowledge 合法保管、物理断电恢复均需独立 Windows/工件证据；Source/Chromium 绿灯不能替代。

以上按“操作者结果 → Core/API 不变量 → 客户端 → 真实载体验收”的顺序推进；不以 PR 数、文档数量或目录移动量作为完成度。版本迁移 #44 和 RC/GA 仍须独立门禁及负责人裁决。

## 11. 最终 1.0.0 判定

1.0.0 不是“重构完成”的别名。至少要求：

- 核心招聘业务与关键异常路径真实可完成；
- Windows 与 Local Web 有各自可发布工件和明确安装/恢复说明；
- 同一 Core 的双端一致性、安全、并发和任务所有权有实测；
- Evidence/Decision/Offer/AI/OCR/ASR/Knowledge/Backup 等能力达到已声明范围；
- API/Schema/版本和工件身份可追溯；
- P0 为 0，重大 P1 有明确处理或发布阻断；
- 产品负责人批准 RC/GA。
