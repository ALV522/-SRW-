# ADR-0002 HTTP 层分解与 API 契约显式化：不重写，只归位

状态：Accepted · 2026-10-21 · 决策角色：产品负责人（“全部按照你的建议”）

## 问题

随着业务面扩大，仓库出现三个可测量的扩展性瓶颈（均有证据，非观感）：

1. `backend/srw/api/fullworkbench.py` 1714 行、27 个路由，Provider 密钥探测、OCR/ASR 字节处理、Knowledge apply/回滚、管道与 Offer 状态机等业务逻辑内联于 HTTP 闭包，与 `modules/`（20 域）+ `surfaces/` 读模型的清晰分层形成唯一“分层破窗”；新增功能必须改这一处，闭包无法脱离应用单测。
2. `frontend/dist/app.js` 126KB 单文件承载全部 UI/渲染/API 调用；convergence03–08 六个世代文件（合计 44KB）各自重复实现 api/toast/modal 基建。
3. 约 146 个 `/api/v1` 路由的契约只存在于路由注册与前端硬编码路径：无机器可读清单、无分域契约文档，接口“存在但不可发现、不可评审、不可 CI 校验”。

同时，负责人曾提出“重构把后端和前端分离”。事实核查表明传输层早已分离（Starlette 版本化 HTTP 契约；WPF Host 经 loopback HTTP；Browser 经 `start_local_web.py` 消费同一契约），该分离是宪章 A6 / ADR-0001 的承重架构——“分离重构”要么空转，要么落入宪章非目标（全新 UI 体系、业务内核重写）。

## 决定

**不重写。在已分离的骨架上做“分解 + 契约显式化”：**

1. **HTTP 层只留 thin adapters**：每域一个路由模块，仅做参数校验、序列化、错误映射；业务逻辑归位 `modules/`、`surfaces/`、`providers/` 等域层。分解按小切片 PR 推进，禁止大爆炸重组。
2. **契约显式化**：从 Starlette 路由生成机器可读路由清单并纳入 CI 校验（新增/变更路由必须过 Governance）；配套分域契约文档；`/api/v1` 按产品契约管理，破坏性变更走 B 类跨端评审。
3. **前端合并六代基建**：`cNNapi/toast/modal/esc` 收敛为一份共享模块，`app.js` 按域拆分；**不更换 UI 框架**，vanilla 模块化即可，Chromium E2E 做行为等价兜底。
4. **切片顺序**：优先提取自包含、冲突成本高的域（Provider 探测/OCR/ASR 为首切片）；HTTP 分解与 Issue #43 的 Supervisor/CAS/会话附着改造交错推进，避免在 1714 行文件上二次返工。

**红线（与产品宪章第 5 节一致）**：不换 UI 框架、不重写业务内核、不拆双数据库/微服务、不大爆炸 PR、不借分解扩功能。

## 已考虑方案

A. 前后端分离重构 —— 否决：传输层已分离，重构等于空转且违反非目标。
B. 借机更换前端框架 —— 否决：宪章非目标；已有 Chromium E2E 覆盖的行为不值得为框架重写冒险；需 A 类负责人决策。
C. 已分离骨架上的分解 + 契约显式化 —— 采纳：直接消除三个可测量瓶颈，每步有回归兜底，风险局部化。

## 验证依据

- 行为等价安全网：约 230 项源回归 + 36 个测试文件 + Chromium 业务 E2E（分解不得降低其通过面）。
- 切片 1（本 ADR 配套首个 PR）：`backend/srw/providers/probing.py` 提取 Provider 探测/OCR/ASR/配置投影，`fullworkbench.py` 1714→1642 行且零行为变更；新增 `convergence_tests/test_provider_probing.py` 16 项（fake secrets/settings + fake httpx，无真实网络）+ 1 项 HTTP 边界集成测试。
- 探索证据：E1–E5 与 Native SOURCE Lab 证明统一 Core 双载体读取可行（不作为正式双写验收）。

## 后果与风险

- 分解期间与业务 PR 的合并冲突成本上升——以小切片、按域交错控制。
- 路由清单成为 CI 强制项后，新增路由必须有对应契约文档，否则 Governance 失败（预期行为）。
- `modules/fullworkbench.py` 与 `api/fullworkbench.py` 同名并存造成混淆，后续切片应逐步消除该命名重复（记录，不在本 ADR 范围）。
- 本 ADR 不改变任何产品不变量、Schema、版本或发行状态。

## 本轮执行方式（负责人授权，2026-10-21）

经负责人明确授权，本轮修改**仅在本地执行**：工作于专用任务分支，不 push GitHub、不建 PR、不合入。因此本变更的 GitHub CI 状态为 **NOT RUN**（非失败）；本地源回归、源码完整性、release truth、治理契约四项检查实跑通过。远端 CI 验证与合并留待负责人指令，届时按 `docs/NO_BRANCH_PROTECTION_PROTOCOL.md` 走完整 PR 门禁。

## 可重新讨论条件

有可重复证据表明统一 Core 在核心招聘业务、目标资源/性能或离线使用上不可行；或负责人批准改变目标用户/部署边界；或出现本 ADR 未覆盖的新型载体需求。
