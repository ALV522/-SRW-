# SRW 主线集成队列与交接规程

状态：G1.1 工程规范，**2026-10-27 10:40 +08 刷新**；表中的 SHA 是**历史快照**，引用前必须重新查询 live GitHub 与 #103/#132 的最新回复。

1. **风险优先、就绪优先，而不是机械 FIFO。** P0 数据/决策/恢复优先；同级再按"实质独立 Review 完成时间"排序。红灯或没有真实 preflight 的 PR 只阻断它自己，不冻结不相交的工作。
2. **同一冲突域只允许一位集成人。** 合并阶段串行占有实际重叠路径，以及 `SOURCE_MANIFEST.sha256`、VERSION/Schema、API/Host contract；其他独立开发可并行，禁止用旧分支整文件覆盖 main。
3. **机器门禁与人工门禁分开。** CI 能证明源码、版本与跨端测试；它不能证明 preflight 在首次编辑前运行、Review 真的独立、Windows GUI 真机通过、或负责人批准了 A 类决策。没有证据就是 `BLOCKED`，没有 Ruleset 就意味着这些是人为纪律而不是平台权限。
4. **合并前**重读 main/head SHA、CI 所属 SHA、Review、未解决 thread、清单与 diff；头部一变就重审受影响范围。**合并后**重读 main SHA、关联 PR 与 push CI。
5. 队列巡检按事件驱动，不设"每天只能合并两次"的窗口；紧急 P0 不因时钟拖延。交接六字段（main/head｜变更｜实证｜下一件｜决策｜阻断）尽量少于 300 字，使用系统真实时间。

## 2026-10-27 22:55 快照（仅作起点，不是当前状态）

| 候选 | 冲突域 | 快照状态 | 下一条件 |
|---|---|---|---|
| **本 PR**（#132 治理刷新 v2） | `docs/`、`README.md`、`.github/pull_request_template.md`、`scripts/report_source_manifest_delta.py`、manifest | 从 `cf72d6e` 干净分支重做；取代 #133 与 #146 旧头 `dde9d794` | exact-HEAD 双平台 Source/Chromium/Governance + A 独立 Review |
| [#137](https://github.com/ALV522/-SRW-/pull/137) 合并就绪报告器 | `scripts/`、tests、docs | 只读报告器，旧头尚未在新 main 上复验 | 与本 PR 的清单差异工具确认不重复后 Review |
| [#101](https://github.com/ALV522/-SRW-/pull/101) | Core/Frontend/Host/Schema | 历史聚合 PR，不是可合并队列 | 只允许从新 main 抽净增量小切片 |

**已闭环（不要重复排队）：** #139 备份原子发布、#140 其故障注入回归、#144 journaled 恢复（含残留清理）、#145 opt-in 纯会话策略。**#145 只进源码，生产 middleware 仍 OFF/未接入。**

**已关闭：** #128、#129、#138、#141、#142、#143（superseded/unmerged）。#133 与 #146 旧头在本 PR 合并后关闭为 superseded。

**待办但不在本队列：** #131 备份下载校验（只有 A 的离线补丁：无 PR、无远端 HEAD、preflight NOT RUN）、#43 middleware 接入与 7 条 test-only RED、#124 Runtime/Knowledge 保管、#42 Native 全链。

## 当某一轨暂时缺席

- 不授权任何人代签"独立 Review"：A 不能替 B/C 审自己的高风险 PR，B/C 也不能替 A 签 Core。
- 缺席期间可做非重叠工作：风险评估、只读工具、文档、确定性测试合同；**不得强合因审查缺席而 BLOCKED 的 PR**。
- 恢复协作后第一件事是重新查询 PR/Issue 的实时状态与时间，而不是沿用上一张状态卡。
