# SRW 仓库治理与主线规则（2026-10-18）

## 1. 唯一研发主线

**GitHub \`main\` 是当前唯一可交付的整合源码主线**。目前主线位于 Convergence 11，产品/源码版本为 \`1.0.0-alpha10-convergence11\`，数据库 schema 为 \`v1_0014\`。该版本不是旧 v0.8.x 的简单更名，也不意味着历史 0.8.x 的全部业务能力已有可证明的等价实现。

项目的研发策略是“**0.8.x 成熟业务能力作为保留/对标对象，C08–C11 源码作为目前实际可持续开发基线**”。尤其是 \`v0.8.12-R2\` 代表历史能力完整性参考，并非目前打包发布的 Windows 原生可执行版本。任何以 UI 改造为由删除成熟证据链、隐私、知识治理、招聘运营、提供商、OCR/ASR 等能力的做法，都需要经实际业务回归审查。

## 2. 分支如何使用

本次审计在仓库中观察到 **26 条分支（含 main）**。大量旧 \`dev/\`、\`fix/\`、\`integration/\` 和 \`repair/\` 分支是已合并 PR 的工作保留现场，并不是并行维护的产品发行版。不要因分支存在就认定相关功能仍在维护，更不能从历史分支直接形成当前发布包。

- \`main\`：PR 审核、验证完成后的唯一集成主线；**禁止强制重写历史**。
- \`dev/\`：较完整的业务功能或开发任务分支；每项任务从当时最新 \`main\` 分出。
- \`fix/\`：可定位缺陷及其回归测试；通过 PR 合并。
- \`docs/\`：文档、历史证据、版本治理以及相关验证脚本；照常要求 CI。
- \`integration/\`、\`repair/\`：历史集成/恢复记录；不作为当前发行主线。

旧分支不能仅凭“名称过时”就删除。先核对 PR 是否合并、当前分支是否比 \`main\` 有未合并提交，以及是否包含唯一审计/恢复材料，再考虑清理。本轮不批量删除历史分支，以免破坏溯源。

## 3. 仓库结构

| 位置 | 责任 | 维护要求 |
|---|---|---|
| \`backend/srw/kernel/\` | 哈希、时钟、业务不变量 | 维持确定性语义 |
| \`backend/srw/modules/\` | 招聘项目、候选人、Evidence/Decision、面试、Offer、治理、任务 | 优先恢复和保护业务完整性 |
| \`backend/srw/surfaces/\` | 候选人、项目、业务队列的读模型 | 不将读模型误当自动人事决定 |
| \`backend/srw/api/\` | HTTP 路由、本地安全边界 | 新路由优先拆分小模块，避免继续扩大 \`fullworkbench.py\` |
| \`backend/srw/runtime/\` | 本地数据库、任务、运行时、设置与备份 | 强化断点恢复、资源释放与数据安全 |
| \`frontend/dist/\` | 当前浏览器/WebView2 功能界面 | 未有行为等价测试前不得以换框架删除功能 |
| \`desktop/SRW.Desktop/\` | WPF/WebView2 Host 源码 | 与最终 Windows Native 二进制验收分开 |
| \`convergence_tests/\` | Python 源码与业务回归 | 合成数据，严格隔离生产数据 |
| \`browser_acceptance/\` | 真 Chromium 浏览器操作 + API + SQLite 验收 | 不等于 WPF 实机验收 |
| \`scripts/\` | 源码/发布完整性、封包与恢复校验 | SHA 严格 fail-closed |
| \`verification/\` | 核验材料，包括明确标注的历史记录 | 旧记录不能冒充新跑的 CI |
| \`docs/history/\` | Pre-Git 历史与原始 ZIP 的目录索引 | 大包独立存储，不能导入主线 |
| \`.github/workflows/\` | 源码回归、仓库完整性及 Chromium 业务验收 | PR 与 main 的通过记录都应保留 |

## 4. 统一交付与证据

三条正式 CI：\`SRW Source Gate\`（Ubuntu/Windows）、\`SRW Repository Integrity\`（main）和 \`SRW Chromium Business Acceptance\`（Ubuntu）。2026-10-18 基线 \`69f60b9\` 已通过三类检查；当前源回归用例 109 项，Chromium 端到端场景 3 项。历史 \`v0.8.12-R2\` 的 725 条 backend 测试仅作为历史覆盖参考，不是当前版本 725/725 通过。

\`VERSION\`、\`BUILD_INFO.json\`、\`PORTABLE_MANIFEST.json\`、\`backend/srw/release_state.json\`、\`VERIFICATION_INVENTORY.json\` 和 \`SOURCE_MANIFEST.sha256\` 承担不同职责，不能用 README 中的一句“完成”替代受约束的构建证据。

交付分为 **source ZIP → Web Portable → Windows Native candidate → 实机验收的正式版** 四种状态；每次应记录 SHA、工件类型、是否包含 Runtime/五套 Knowledge DB、使用何种 Host，以及未完成的验证。源码 CI 通过只证明源码/回归能力，不证明存在 Windows 可启动安装包。

## 5. 原始历史开发包

用户提供四份历史 ZIP，已读取目录和计算完整 SHA-256，详见 [原始 ZIP 清单](history/LEGACY_ARCHIVES.json) 与 [历史包说明](history/ARCHIVE_CATALOG.md)。**这些 ZIP 的二进制字节没有提交到 GitHub**。它们包含大型 Knowledge DB 和／或可执行 Runtime，未经来源认证、隐私内容和供应链检查，不得直接当成安全发布物或当前 release。

GitHub 存储建议：建立清楚标识为 \`Historical / Unverified\` 的独立 Release，并在完成隐私/来源/完整性复核后将 ZIP 添加为 **Release assets**（不要提交进普通 Git 历史、主目录或 Git LFS 主线）。本次所用 GitHub 连接只提供文字源码写入、PR 和合并等操作，未提供 Release asset 二进制上传能力，因此仅留存可验证目录，**不虚构上传成功**。

旧 \`v0.8\` Release 内已存在的 \`SRW_v0.8.8_Web_Portable.zip\` 是历史 Web 包，不能误当成需要的 \`SRW_v0.8.8_Windows_Portable.zip\`，更不能用它绕过 Windows Host 的精确哈希门槛。

## 6. 代码更新规程

从 \`main\` 分支，先明确具体业务缺陷或验收能力；保留 0.8.x 成熟能力，附加真实业务测试；修改 \`SOURCE_MANIFEST.sha256\`；通过 PR 的 CI；使用精确 head SHA 合并；最后再次确认合并后 main 的三条适用工作流均 PASS。

发布版、历史 ZIP 和候选人数据不得直接加入 \`main\`；遇到来源不明的生产 Knowledge / Python Runtime，只允许清单和哈希比对，不能直接以“可启动”为由提升可信级别。

## 7. 后续顺序

1. **业务覆盖**：招聘标准发布、Claim 人工确认、Scorecard、Decision、Offer 流转、项目交接各建 Chromium 端到端验收；避免仅靠接口测试称作 UI 产品完成。
2. **业务架构**：沿完整招聘场景拆分庞大的 \`fullworkbench.py\` 与 \`frontend/dist/app.js\`，必须先有回归测试。
3. **Windows 工件**：取得独立审计的 Runtime、五套生产 Knowledge DB、精确的历史 Windows Host，建立 SHA 证据再试真实装配。
4. **最终验收**：在目标 Windows 上运行 WPF/WebView2，执行完整招聘场景、备份恢复、OCR/ASR/AI Provider 和数据迁移。没有实机证据不升级状态到 RC。
