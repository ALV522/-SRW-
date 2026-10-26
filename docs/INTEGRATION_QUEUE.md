# SRW 主线集成队列与交接规程

状态：G1.1 工程规范，初版 2026-10-26 13:20 +08；以下 PR SHA 是**历史快照**，请先查询 live GitHub 和 #103/#132 最新回复。

1. **风险优先、就绪优先，而非机械 FIFO。** P0 数据/决策/恢复最高；相同严重性再按实质独立 Review 完成时间排序。红灯/缺 preflight 的 PR 阻断其自身，但不能冻结不相交工作。
2. **同一个冲突域只允许一位集成人。** 合并阶段串行占有实际重叠路径和 SOURCE_MANIFEST、VERSION/Schema、API/Host contract；其他独立代码开发可并行，禁止旧 branch 整文件覆盖 main。
3. **机器门禁 vs 人工门禁分开。** CI 可验证源码/版本/跨端测试，不能证明 preflight 在首次编辑前运行、Review 真正独立、真实 Windows GUI 和 A 类用户批准。无证据就是 BLOCKED；无 GitHub Ruleset 意味着这些属于人为纪律而非平台权限。
4. 合并前审查实时 main/head SHA、CI 所属 SHA、Review、unresolved threads、SOURCE_MANIFEST、PR diff；任何头部变化都重审受影响范围。合并后重读 main SHA、关联 PR 和 push CI。
5. 午晚可安排**队列巡检**而非每日两次固定“只能合并”窗口；紧急 P0 不因时钟拖延。无自动或后台工作承诺，评论使用真实系统时间，六字段少于 300 字。

| 候选 | 冲突域 | 初版客观状态 | 下一条件 |
|---|---|---|---|
| [#129](https://github.com/ALV522/-SRW-/pull/129) 原子备份 | backup_truth/system/API tests/manifest | HEAD `0015471d` 双平台 Source 413 PASS；尚未合并 | B 对新 HEAD 复审；在真正 preflight PASS 的干净分支移植 A patch、再 CI |
| [#128](https://github.com/ALV522/-SRW-/pull/128) 中断 RED | tests/manifest | HEAD `2a60299f` 两条 Source RED（预期），尚未合并 | 生产修复入 main 后重新集成并证实 RED→GREEN |
| [#132](https://github.com/ALV522/-SRW-/issues/132) 文档/治理/诊断 | docs/README/scripts/manifest | 可独立验证但与清单冲突 | preflight、独立 Review、真实 CI 全部符合后才并入 |
| [#101](https://github.com/ALV522/-SRW-/pull/101) | Core/Frontend/Host/Schema | 旧聚合历史 PR，不是可合并队列 | 从新 main 独立抽取有净增量小切片，禁止整包 merge |

**当 B/C 暂不可用：** A 做风险图、README、只读清单工具、合成断电 test contract 等非冲突事项，**不得 A 自己审核并合并高风险 PR**。恢复后各方优先查询最新 PR/Issue 状态和真实系统时间，历史状态卡不是实时权限。
