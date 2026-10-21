# SRW 版本与发布身份规范 · G1 (2026-10-20)

**本规范立即生效。版本改革与真实软件升级分离：本轮不把现行历史版本重命名成未验收的新版本。**

## 1. 为什么改革

历史把产品版本、alpha 次序、业务工程阶段（Convergence C11）、数据 Schema、Native ZIP 身份混在一个文本里，如 1.0.0-alpha10-convergence11，容易引起混淆：新 commit 不代表新 release；同版不同 SHA 不代表同一个可验收工件；浏览器 CI PASS 不代表 WPF PASS。

## 2. 五个独立维度

| 维度 | 格式/举例 | 表达什么 | 不得表达什么 |
|---|---|---|---|
| **Product version** | 1.0.0-alpha.11 → 1.0.0-beta.1 → 1.0.0-rc.1 → 1.0.0 | 面向使用者的 SemVer 版本 | 单次提交、Convergence、Schema |
| **Source revision** | 完整 Git SHA: 40 hex | 可回溯的准确代码身份 | 产品成熟度 |
| **Schema revision** | v1_0014，后续 v1_0015 | 数据格式/迁移版本 | 软件或业务功能版号 |
| **Build/artifact identity** | windows-native / local-web + artifact SHA-256 | 工件字节与载体 | 不经测试的发布资格 |
| **Release channel/status** | development / candidate / rc / stable + separate gates | 发行状态和可用性证据 | 代码已存在不等于 PASS |

Convergence11/C11 是工程历史**里程碑代号**；G1 是治理制度版本；E1–E5 是探索实验编号。三者都不作为正式 Product version 后缀。

## 3. SemVer 规则

- 首个完整可交付目标为 **1.0.0**，并不是现已达到 1.0.0。
- 下一次由工程变更承载的统一命名候选建议从 **1.0.0-alpha.11** 开始；仅当执行独立的版本迁移 PR、统一现有全部 release identity 文件并经 CI 校验后生效。
- 之后 alpha.12、beta.1、rc.1、1.0.0；不要跳号假装成熟。alpha 是未承诺兼容/非生产，beta 是广泛功能完整候选，rc 是冻结并通过规定发行门禁的候选，stable 是负责人批准的正式发行。
- 正式稳定发行后：PATCH 只包含兼容修复，MINOR 为向后兼容新能力，MAJOR 为不兼容的产品/API 行为。每次都明确数据迁移兼容和回滚说明。
- Git SHA 不放进 VERSION 的必需文本。展示或诊断可以另用 **1.0.0-alpha.11+g<sha>** 构建元数据；+后缀只作标识，不影响语义版本排序。
- Windows 和 local-web **共享同一个产品版本与源 SHA**，但分别记录 carrier 状态、工件哈希、运行环境与验收。允许仅某一载体验收通过；不得用共同版本号假装两端都已经 PASS。
- 每个候选工件发布时冻结 manifest 和 hash；工件字节变更即成为新构建，不能用原有验收凭证。

## 4. 当前迁移边界

目前 VERSION、BUILD_INFO.json、backend/srw/release_state.json、PORTABLE_MANIFEST.json、VERIFICATION_TRUTH.json、VERIFICATION_INVENTORY.json、WINDOWS_NATIVE_HOST_STATUS.json 等多处必须严格相等。**版本迁移已于 2026-10-21 执行**（本地任务分支，负责人授权仅本地执行，未同步 GitHub）：运行产品版本由旧格式 `1.0.0-alpha10-convergence11` 迁至 SemVer **`1.0.0-alpha.11`**，仍属 source-development 通道；`BUILD_INFO.source_revision` 记录代码基线完整 Git SHA，工程里程碑代号 C11 保留于 `artifact_profile`/`engineering_milestone`，不进入产品版号；历史 alpha10 工件引用与证据快照（verification/、docs/history/、历史交付日志）一律不改。执行记录见下文；`check_release_truth` 与 `check_governance_contract` 对八处身份与政策字段强制一致。

### 迁移执行记录（2026-10-21）

| 项 | 值 |
|---|---|
| 迁移前身份 | `1.0.0-alpha10-convergence11`（legacy-pre-migration） |
| 迁移后身份 | `1.0.0-alpha.11`（SemVer，source-development） |
| 前一主线 SHA | `45abc4cae766cbc1b52cb40bfe3c762e6e151a57` |
| 代码基线 SHA（BUILD_INFO.source_revision） | `4dc0c9f4491b892a1eaed8a8f5db8315ac156a56` |
| Schema | `v1_0014`（独立，未随版本迁移变动） |
| 执行方式 | 本地任务分支单一原子提交；未 push、未建 PR、未 tag |
| CI 状态 | GitHub CI = NOT RUN（负责人指令）；本地 check_release_truth / check_governance_contract / 全量源回归实跑通过 |
| 后续门槛 | alpha.12→beta.1→rc.1→1.0.0 各自门禁见上表；RC/GA 仍需负责人批准 |

根目录 VERSION_POLICY.json 明确 current_runtime_version（旧格式）、next_product_version（新 SemVer 规划值）、schema_revision 和 release state。scripts/check_governance_contract.py 检查其与真实元数据的一致性。待下一次实际版本迁移 PR：
1. 冻结准确开发 SHA 和业务能力基线，创建变更 Issue；
2. 在一个原子 PR 同时更新 VERSION、BUILD_INFO、release_state、Portable/Verification/Host 元数据及其他代码/测试中应当变动的权威标识，不覆盖历史记录；
3. 同步更新 VERSION_POLICY.json 的 current_runtime_version、last_transition 和 intended_channel，维持 Schema 与迁移文件独立；
4. 运行 check_release_truth、check_governance_contract、所有源回归、相关浏览器测试、Host 构建；
5. 新版需要重新装配并在准确 Windows 工件进行 GUI/业务验收；旧 d8d032d 验收保留为历史事实；
6. 只有达到对应产品 channel 的门槛且负责人批准后发布正式 tag/Release。

**治理版本 G1 ≠ 产品版本 1.0.0-alpha.11 已启用。** 后者当前只是下次版本迁移的目标，不是当前任何工件的标签。

## 5. Tag / 文件 / 发布规范

- Tag 建议：v1.0.0-alpha.11、v1.0.0-rc.1；tag 不得后移，不得标记实验包为稳定版。
- 文件示例：SRW_1.0.0-rc.1_windows-native_<shortsha>_<buildid>.zip / SRW_1.0.0-rc.1_local-web_<shortsha>_<buildid>.zip。
- 内容 manifest：product_version, source_sha, schema_revision, carrier, runtime/dependency identity, knowledge provenance, artifact SHA-256, build time/environment, channel, tests/evidence/known issues。
- 真实 release 只能引用确切提交/工件; Source ZIP/Host-only/Prepared Native/experiment/RC/GA 分开标注。
- 不允许把数据 Schema 迁移误写成仅仅修改产品 PATCH 号；数据迁移必须有单独验证和还原策略。

## 6. 验收矩阵与发布门禁

| 状态 | 所需最低证据 |
|---|---|
| DEVELOPMENT | 源码清单、release truth、当前源码测试 |
| CANDIDATE | 完整源/Runtime/Knowledge/Host 工件审计和相应载体构建 |
| BROWSER_ACCEPTED | 准确工件/源码的 Chromium 真实业务测试 |
| WINDOWS_ACCEPTED | 准确 Native ZIP 的真实 WPF/后端/业务和恢复验收 |
| DUAL_CARRIER_ACCEPTED | 同一 Core 双端交叉读写、CAS 冲突、会话与任务所有权验收 |
| RC | 功能冻结、P0=0、规定的完整发行门禁及清楚记录的已知问题 |
| GA/STABLE | 负责人明确批准、版本化包/文档/回滚机制齐备 |

Browser 和 Windows PASS 互不推导；DUAL_CARRIER PASS 不能由 E1–E5 探索自动推导。最新结果总以同提交 CI 与工件验收为准。

## 7. 反例

错误：“C11 已通过 7 个浏览器测试，因此 1.0 已发布。”
正确：“指定提交通过指定 7 条 Chromium 业务验收，Windows Native 当前候选仍需独立验收；产品通道仍为 development。”

错误：“修了 PowerShell 封包 bug，版本号顺手改成 1.0.0。”
正确：“修改源码并更新版本迁移记录；软件经过候选工件和业务验收后，才按 channel 发版。”
