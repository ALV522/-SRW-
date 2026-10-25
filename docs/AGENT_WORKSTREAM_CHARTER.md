# SRW · 多 Agent 开发分工与执行宪章（2026-10-25）

状态：ACTIVE collaboration policy，受 `AGENTS.md`、G1、ADR-0001/0002、版本政策和发布门禁约束；**不是新产品版本或放宽审批**。关联 #41/#42/#43/#44/#63、PR #98/#101。

## 1. 现状与边界

- 编写时 main=`8c59a233c62d382de2f4823074fc70e1bee4edef`；VERSION `1.0.0-alpha10-convergence11`，Schema `v1_0014`，377 个 SHA 文件。最近准确 SHA 跨平台 Source Gate 各 369 tests / 2 skipped PASS；开发通道，不是 RC。
- 真实 Windows **c325** 候选 ZIP（SHA256 `7a60e67e9dce873cb370b9eba0e30747080e9937d33a4fc848655f73ec457607`）已通过嵌入式后端、WPF/WebView2 两次启动/正常退出；产品负责人还报告在**合成工作区**成功完成建岗、招聘标准、候选人创建、PDF 简历上传四项。这是人工报告的基础业务结果，尚非其余招聘、OCR/ASR/Provider、恢复或双载体验收；不能外推到新 Git SHA。
- PR #101（旧 head `dc394e9e9488ef54b3c19be4fa70bec23ac46bbf`，基于旧 `45abc4c`）将 HTTP 迁移、前端、Supervisor、Schema 与版本混合，存在覆盖主线 R2 路由及回归的风险；**禁止整包合并或用旧文件覆盖 main**。PR #98 是另一开放的业务变更，应先解决文件重叠。
- 开工前一律重新查询 live main/PR/Issues/工件，以上是带时间与 SHA 的历史证据，禁止当作未来实时事实。

## 2. 目标排序

**P0 数据/人工决定/证据安全 > P0 #41 完整招聘业务 > P0 #42 Native 实机业务验收与恢复 > P1 #43 一个 Core 双端的并发、权限与工作区所有权 > 有可证明收益的 R2/R4 渐进重构。** 不以目录行数、路由迁移百分比替代产品交付。并行主要 WIP ≤3；普通工程问题由 Agent 自主处理。

## 3. 分工和默认文件归属

| 工作轨 | 责任人 | 默认范围 | 应交付成果 |
|---|---|---|---|
| A 产品化 / 正确性 | **主线集成 Agent** | `backend/srw/api/{app.py,fullworkbench.py,routes/*}`、Domain/Application、#41 业务测试、Native 构建和 Windows 实机验收工具、#42 | A1–A8 与 v0.8.12-R2 功能保真；逐项合成招聘闭环、异常路径、备份恢复；最新工件独立验证 |
| B R4 前端模块化 | **dev/43 外部协作者** | `frontend/dist/*`、`scripts/check_frontend_contract.py` 及明确的前端专用测试 | **每 PR 只拆一个有界 feature/API-client 责任**；UI/DOM、API、使用体验和业务语义保持，原 Chromium 场景全部通过 |
| C #43 Supervisor / 双载体 | **dev/43 主笔，主线集成 Agent 复核 Core/Windows 合同** | `backend/srw/supervisor/*` 和专用 T1–T10 验收；涉及 lease、API/Schema 必须先评审并约定唯一集成人 | 先 ADR/协议和测试，再独立拆分生命周期、附着会话、CSRF/CAS、备份互锁；本地 PASS ≠ Windows 双端 PASS |
| 产品负责人 | **用户** | 真实 Windows 合成验收、A 类产品取舍、危险数据操作、正式发行与 Public→Private 设置 | 只有需要高风险决策才征询；普通 PR 自治执行 |

文件归属是冲突管理约定，不是无限期独占。如果确需改别人的域：先写下 operator use case、准确函数/API 合同、受影响文件、预期测试；明确一个集成人和 PR。**禁止两个 Agent 同时整文件覆盖 `app.js`/`fullworkbench.py`/`routes/*`**。`SOURCE_MANIFEST.sha256` 由每个独立 PR 在编辑和行尾固定后更新，主线集成 Agent 最终核验；`SOURCE_RECOVERY_MANIFEST.sha256` 不可变。

## 4. 对旧 dev/43 工作的处置

1. **保留** PR #101 和旧 head，不强推、不删除；若原作者有仅本地未提交代码，先自己保存对照清单，任何密钥/候选人数据绝不能上传。
2. 不能从旧 head 整体 rebase 再合并。**从最新 main 新开 feature 分支**，只挑存在真实净增量的功能级改动；保留所有已经迁移至 `api/routes/*` 的代码、合同和测试。
3. **第一个新 PR：R4 一个独立前端切片**（建议统一 API client/error/session 或一个招聘功能域），只触及前端和专属验证；不夹带 R2、Supervisor、Schema、VERSION、Provider 秘钥处理。任何可见 UI 或路由回退都 BLOCK。
4. R2 后端路由余量由主线集成 Agent 主导，仅按当前 live inventory 和 mutation 合同选择必要切片。迁移后不得丢路由/测试，也不得为了百分比机械拆分 `capability_recovery*`。
5. #43 R5 的租约、attach/revoke、会话/Origin/CSRF、If-Match/CAS（412 不产假审计）、Job Engine、恢复互锁分别提交有失败注入与 T1–T10 的 PR；当前真实 Host 父进程租约安全门禁不许削弱。
6. 访谈证据更正 `test_16` / #58 先对照**当前**主线是否已实现，缺失才独立补；不得把旧 `app.js` 或 `app.py` 带进来。
7. #44 版本/Schema `v1_0015` 必须**独立原子 PR**，具备迁移/恢复/真实 Windows+Browser 新工件重验；在此之前维持原有 VERSION/Schema。相关 A 类变更和正式发行需产品负责人审批。

## 5. 不可绕过的 PR / 验收线

- **开工**：读 `AGENTS.md` 全部必读文件，检查 live main SHA、VERSION、Schema、Issues/PR、Exact CI、Windows 工件。专用干净分支先运行 `python scripts/agent_preflight.py --issue N --acknowledge-reading`，**然后**改代码。
- **实现**：operator outcome → Domain/Application → API 合同 → Browser/WPF。保护 Source/Claim/Judgment/HumanDecision、人类录用、历史能力、单一 SQLite 与本地隐私。不创建 SaaS、微服务、新 Core、新前端框架。
- **文件**：不得以旧分支整文件覆盖；编辑/行尾定稿后才更新 SOURCE_MANIFEST；保持 source recovery 清单不变。合同清单和测试发现列表应与基线比较，不能只靠测试总数判断是否回退。
- **PR 证据**：四条 G1 必读声明必须逐字出现；业务前后行为、原子 diff、回滚、准确源/工件 SHA、Ubuntu/Windows Source、Chromium、Host、Windows GUI、Provider/恢复、双端各自 PASS/FAIL/BLOCKED/NOT RUN。
- **合并**：准确 PR HEAD 上适用 GitHub CI 全绿；核查 main/head 未漂移，才能经 squash PR 合入；合并后读回 main。无保护 main 不等于允许直接 push。Windows GUI 只能以真实指定工件的目标机证据主张。
- **保密**：不得向目前 Public 的 GitHub 上传生产 Runtime/Knowledge、原始简历、SQLite、Token、Provider key、未脱敏日志。负责人尚未批准 RC/GA。

## 6. 里程碑及唯一后续动作

- **当前产品线**：在原 c325 合成工作区继续 HumanDecision 失效/重申 → Interview/Scorecard → Offer → 备份恢复 → OCR/ASR/AI/Knowledge；每项保留可核验实际结果。基础四步正常≠完整闭环。
- **dev/43 首轮**：只开一个 R4 小型前端 PR，准确 HEAD Chromium/Source Gate 全绿；PR #101 保留为参考，不得直接合并。
- **之后 #43**：独立合同、Core owner、session/CAS、T1–T10；Linux 与实际 Windows 同一 Core 双端分开验收。
- **版本 / 发布**：Schema 迁移与 SemVer 独立 PR，所有新工件重新验收，重大产品取舍和正式 RC/GA 归用户决定。

本宪章是负责人已批准方向下的工程授权：**协作者应自主执行第一项 R4 小 PR，无需反复询问普通工程选择**；跨作者的 API/Schema/权限合同先留可审查的 PR 注释。