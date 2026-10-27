# SRW 主线集成队列与交接规程

状态：G1.1 工程规范，**2026-10-27 10:40 +08 刷新**；表中的 SHA 是**历史快照**，引用前必须重新查询 live GitHub 与 #103/#132 的最新回复。

1. **风险优先、就绪优先，而不是机械 FIFO。** P0 数据/决策/恢复优先；同级再按"实质独立 Review 完成时间"排序。红灯或没有真实 preflight 的 PR 只阻断它自己，不冻结不相交的工作。
2. **同一冲突域只允许一位集成人。** 合并阶段串行占有实际重叠路径，以及 `SOURCE_MANIFEST.sha256`、VERSION/Schema、API/Host contract；其他独立开发可并行，禁止用旧分支整文件覆盖 main。
3. **机器门禁与人工门禁分开。** CI 能证明源码、版本与跨端测试；它不能证明 preflight 在首次编辑前运行、Review 真的独立、Windows GUI 真机通过、或负责人批准了 A 类决策。没有证据就是 `BLOCKED`，没有 Ruleset 就意味着这些是人为纪律而不是平台权限。
4. **合并前**重读 main/head SHA、CI 所属 SHA、Review、未解决 thread、清单与 diff；头部一变就重审受影响范围。**合并后**重读 main SHA、关联 PR 与 push CI。
5. 队列巡检按事件驱动，不设"每天只能合并两次"的窗口；紧急 P0 不因时钟拖延。交接六字段（main/head｜变更｜实证｜下一件｜决策｜阻断）尽量少于 300 字，使用系统真实时间。

## 2026-10-28 01:10 快照（只能用于交接，非实时授权）

| 候选 / 事项 | 冲突域与现状 | 下一动作 |
|---|---|---|
| **本 PR** #132 效率治理 pilot | `docs/`, `.github/workflows/`, `scripts/`, tests、根 Manifest；从 `b95d3359` 干净分支执行 pre-edit G1 | 自动 CI 证据链接、分域只读等价证明，完整 Source/Chromium/Governance、另一轨 Review 后才可合入 |
| [#148](https://github.com/ALV522/-SRW-/pull/148) | #43 session policy + HTTP/root 测试 **test-only 故意 RED**，当前基线 `6adfcf39`（已过期） | 仅作生产 atomic RED→GREEN oracle；不能单独合并或把旧 Manifest 406 覆盖 main |
| [#137](https://github.com/ALV522/-SRW-/pull/137) | #135 advisory PR readiness 报告器，旧分支基线 | 先比对与本 PR 的 CI 证据 bot/现有 delta 工具；仅转移不重叠的独有代码，不能直接合并 |
| [#101](https://github.com/ALV522/-SRW-/pull/101) | 85 文件规模的旧 Core/Frontend/Host 聚合 PR；非活跃可合并候选 | 差异与唯一行为证据审计后拆小 PR；**不删除**有历史价值的分支 |
| #130、#43、#124、#42 | 恢复交易终态、会话双端合同、Native 外部工件、目标机 WPF 验收 | 根据 P0/P1 门禁与真实测试逐项收敛 |

**已合并（不得重复排队）：** #139、#140、#144、#145、#147、**#149（main `b95d3359`，有界完整性校验备份下载）**。#133/#146 等旧治理候选已关闭、未合并；不删分支。#145 policy 只是源码能力，HTTP gate 仍 OFF。

**资源冲突减量实验：** 根 Manifest 仍必改且必校验，Pilot 仅收集分域摘要，不能声称已经让并行 PR 无冲突。来源与真实链接由 bot 写在各自 PR 上，#103 只保留 main/head、业务结论与阻断，不重复大段 CI 数字。

## 当某一轨暂时缺席

- 不授权任何人代签"独立 Review"：A 不能替 B/C 审自己的高风险 PR，B/C 也不能替 A 签 Core。
- 缺席期间可做非重叠工作：风险评估、只读工具、文档、确定性测试合同；**不得强合因审查缺席而 BLOCKED 的 PR**。
- 恢复协作后第一件事是重新查询 PR/Issue 的实时状态与时间，而不是沿用上一张状态卡。
