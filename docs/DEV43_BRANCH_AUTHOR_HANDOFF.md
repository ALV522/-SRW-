# 致 dev/43 外部开发者：下一轮执行要求与移植边界

这不是合并 PR #101 的许可。先完整读 `AGENTS.md` 和 `docs/AGENT_WORKSTREAM_CHARTER.md` 及 G1 全部必读文件。你原有 `dc394e9` 工作中的前端拆分、Supervisor、访谈更正可能有价值，但**现在不能整体 rebase/merge 并覆盖当前 Core**。#101 保留为参考代码库，不删除、不强推。

## 第一轮：只交付一个 R4 前端切片（#63）

1. 重新查询 main SHA、VERSION、Schema、开放 PR #98/#101、受影响 CI/Windows c325 工件；从**当时最新 main**新建 `feature/63-r4-client-...`，在干净工作树先执行 `python scripts/agent_preflight.py --issue 63 --acknowledge-reading`。
2. 比较当前 `frontend/dist/app.js`、`index.html`、`scripts/check_frontend_contract.py` 和旧分支的精确差异。**只移植一项**当前主线没有的 API-client/error/session 或单一业务 feature。不可复制旧的整个 app.js；不得触及后端 API/routes、Supervisor、VERSION/Schema、Native Host。
3. 操作者的菜单、DOM、提交行为、错误提示、API/Source/Decision 不变量、当前真实 Chromium 场景必须保持。同步 JS/前端合同/Source SHA 清单，声明完整测试数和失败路径，切记不能仅仅以源文件行数减少宣布“完成”。
4. 打开**一个** R4 PR；以其准确 HEAD 的跨平台 Source Gate、Governance、真实 Chromium 全绿、任何适用 Host Gate 和 main SHA 未漂移为准合并。Windows WPF 没跑就写 NOT RUN。

## 第二轮：R5 合同先行，随后分 PR 代码化（#43）

先写 Supervisor 协议与 T1–T10 的失败关闭合同：唯一 Core/SQLite/Job owner、父子租约与工作区校验、attach/revoke、Origin/CSRF、If-Match/CAS 的 412 不产假审计、恢复互锁与旧会话失效。请先在 PR 中把你预计改动的 `workspace_lease.py`、`run_local.py`、Core API 或迁移文件逐一列出，等主线集成 Agent 完成 API/存储边界审查；不得放宽目前已验证的 Host parent lease。实现顺序：协议/合成 T1–T10 → Supervisor 进程生命周期 → 会话与授权 → 原子写入和恢复 → Windows/Chromium 同 Core 双端真机验收。一次只合并一个可独立回滚的子项。

## 第三轮：访谈证据更正（#41 / #58）

先核对**现有主线**和开放 PR #98 是否已有相同 UI/业务合同。如果当前仍缺失，独立移植 `test_16` 和必要 UI/证据更正，不得带回旧面试、候选人、路由代码或数据定义。更正前后必须保留 Source lineage、审计、HumanDecision 版本有效性。

## 不得触碰或擅自合并的范围

- 当前 `backend/srw/api/{app.py,fullworkbench.py,routes/*}`、Core 业务规则及 Native 打包/Windows 验收是主线集成 Agent 负责的当前产品化工作；确实缺 API 时先列 operator use-case 和请求/响应合同，由主线 Agent 集成。
- `VERSION`、`VERSION_POLICY.json`、`BUILD_INFO.json`、`PORTABLE_MANIFEST.json`、Schema v1_0015 在独立 #44 版本/迁移 PR 中审核，并在 Windows/Web **重新装配与重验**后才可能生效；不作为 R4/R5 的附赠改动。
- 不要移除已合并 14 个 R2 route 切片、端点/Chromium 用例，不要把旧 `fullworkbench.py` 或 `app.py` 当冲突解决的权威文件，不要自动清理旧候选包或真实 SQLite。
- 仓库当前 Public：不要上传应聘者、数据库、嵌入式生产 Knowledge、原始 Host 日志、API key/Token； `SOURCE_RECOVERY_MANIFEST.sha256` 不动。

## 每轮交付必有六件

**PR URL 与真实 HEAD SHA；业务动作 before/after；完整文件影响范围与旧能力映射；准确 HEAD 的 Source/Chromium/Host/Windows 分级验收；数据/迁移/安全与回滚；剩余阻断和下一轮最小任务。** 不询问用户普通工程问题，只有触及 A 类不变量、危险生产数据、重大版本迁移或 RC/GA 才请求用户决定。

目前用户在真实 c325 合成工作区已报告「建岗、标准、候选人、PDF」四步正常。**请不要为 R4 再改这四个已验证功能的业务语义**；其后 Decision/Interview/Offer/Backup 的完整 Native 验收由主线产品化轨继续进行。