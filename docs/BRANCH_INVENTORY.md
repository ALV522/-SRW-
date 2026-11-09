# GitHub 分支治理与清理快照

状态：ACTIVE · 2026-11-09  
权威产品主线：`main`。本文件记录**治理方法和带日期快照**，不再维护一张会迅速过期的几百行分支表。

## 1. 当前事实

本轮清理开始前，GitHub API 返回 **203 条分支（含 main）**；创建本任务分支后会临时再增加 1 条，因此“分支总数”本身不是交付指标。清理前的前缀分布为：

| 前缀 | 数量 |
| --- | ---: |
| `fix/` | 75 |
| `dev/` | 31 |
| `feat/` | 26 |
| `feature/` | 20 |
| `a/` | 18 |
| `docs/` | 13 |
| `test/` | 12 |
| 其他（含 main） | 8 |

同一轮读取了 191 个 CLOSED PR；其中 167 个是本仓库分支已合并 PR，且其 head branch **仍然存在**。仓库设置 `delete_branch_on_merge=false`，所以大量已合并工作分支持续累积是结构性原因，而不是当前仍有 167 个活跃开发任务。

2026-11-09 本轮快照中的真实 OPEN PR 工作分支只有：

- #230 `feature/43-m3b-wpf-business-session-20261106`：#43 Host/session，高风险，HOLD；
- #231 `a/159-browser-shutdown-timeout-evidence-20261106`：#159 Windows Chromium 退出诊断；
- #237 `feat/235-workbench-hierarchy`：当前 P0 产品路径，收口中；
- #238 `a/159-shutdown-phase-probe-20261106`：#159 shutdown phase 合成诊断。

动态状态仍以 GitHub OPEN PR、[#103](https://github.com/ALV522/-SRW-/issues/103) 和准确 SHA Actions 为准。

## 2. 分支分类

### A. 必须保留的活动引用

- `main`；
- 所有 OPEN PR 的 head branch；
- 明确承担隔离实验、且主线文档仍引用其证据的分支（当前至少包括 `explore/html-site-prototype`）；
- 产品负责人或治理文件明确标记的未完成恢复/发行工作分支。

### B. 已合并、可进入删除候选队列的引用

同时满足以下条件才列为候选：

1. 对应 PR 已 `merged_at != null`；
2. head branch 仍存在且不是 `main`；
3. 不属于任何 OPEN PR；
4. PR/Issue 已记录准确 head SHA、关键 CI/工件证据和回滚入口；
5. 删除的是**分支引用**，不是删除 main 中已合入的代码，也不得删除历史 PR、Actions、release/artifact 证据。

本轮统计有 **167 条**满足“已合并且分支仍存在”的基础条件；这只是候选集合，不能无检查批量删除。尤其 squash merge 的原分支提交与 main 提交身份不同，清理前必须确认关键证据已经以 SHA/PR/Actions 链接固化。

### C. 历史未合并分支

`dev/`、`fix/`、`feature/` 等前缀不能自动判定为垃圾。未合并分支必须先 compare `main...branch`，检查唯一文件、业务证据、恢复输入和是否被文档引用；没有等价主线/历史归档前不删。

## 3. 清理顺序

1. 先清当前产品入口与文档重复，避免开发者读错主线；
2. 再清“已合并且证据已固化”的分支引用；
3. 最后逐项审历史未合并分支，不做按前缀的一键删除；
4. 每次分支治理不得与产品 PR 的 `app.js`、Core/Host、Schema、Runtime/Knowledge 改动混在同一 PR。

本轮已经把固定在 2026-10-19 的根目录 `README_FIRST.md` 作为冗余入口退役；唯一入口保持 [README](../README.md)，状态与路线分别由 [DEVELOPMENT_STATE](../DEVELOPMENT_STATE.md) 与 [ROADMAP](ROADMAP.md) 提供。

## 4. 自动清理建议

仓库当前 `delete_branch_on_merge=false`。在确认 GitHub 的分支保护/审计策略后，可启用“合并 PR 后自动删除 head branch”，把未来增长从源头截断；历史 167 条候选仍需按上述规则单独清理。

当前连接器没有 delete-ref / repository-settings mutation，因此本文件**不声称**已经删除这些远端分支；只记录已核验的候选集合与后续安全清理合同。分支数量也不属于 SRW 产品质量或 Native 体积指标。
