# GitHub 分支盘点（2026-10-18）

本清单记录盘点时 Github API 返回的 **26 条分支**，用于避免将旧开发分支误当作多个正式产品版本。**只有 main 是当前受 CI 约束的整合源码主线。** 分支是否包含未合并唯一改动，需要在清理前使用 compare/PR 逐项验证；这里不把任何分支标为“安全可删除”。

| 分支 | 盘点时 Head（短 SHA） | 类型与用途 |
|---|---|---|
| `main` | `69f60b9c` | 正式整合源码基线（本次文档 PR 合并前） |
| `integration/c09-stable` | `63c8ac6d` | C09 历史集成 |
| `repair/c08-source-and-ci` | `6072d74b` | C08 源码恢复 |
| `fix/c09-windows-sqlite-lifecycle` | `f3dc42b4` | Windows SQLite 资源关闭 |
| `fix/ci-notification-noise` | `dcc44921` | CI 邮件/重复运行 |
| `dev/convergence09` | `bc1d3ca0` | C09 主开发 |
| `dev/convergence10-system-integrity` | `c68249c3` | C10 系统完整性 |
| `dev/convergence11-business-workflow-closure` | `2ae639dc` | C11 招聘业务整合 |
| `dev/convergence11-operational-action-center` | `21cb3d82` | 运营行动中心 |
| `dev/convergence11-review-center` | `df64b44d` | 审核中心 |
| `dev/convergence11-review-resolution` | `08dd6b76` | 判断复核闭环 |
| `dev/convergence11-project-guidance` | `ca08283b` | 项目下一步指引 |
| `dev/convergence11-operator-briefing-ui` | `742fcc69` | 项目摘要与交接 |
| `dev/convergence11-candidate-workspace-page` | `d149a4af` | 候选人独立页面 |
| `dev/convergence11-candidate-interview-workspace` | `160100ff` | 候选人面试工作区 |
| `dev/convergence11-job-setup-wizard` | `d063b827` | 四步建岗向导 |
| `dev/convergence11-criteria-editor-preservation` | `88baeec3` | 招聘标准编辑保真 |
| `fix/c11-active-queue-and-local-day` | `24cf9010` | 全局队列排序与本地自然日 |
| `fix/c11-exact-review-deeplinks` | `4addee78` | 精确复核跳转 |
| `dev/convergence11-backup-truth` | `d1f9fdbf` | 数据备份和启动恢复 |
| `dev/c11-backup-integrity-restore` | `e669c530` | SHA 校验备份 |
| `fix/c11-portable-input-preflight` | `41ff247e` | Portable 输入预检 |
| `fix/c11-native-package-allowlist` | `4ea2788d` | Native 白名单封包 |
| `dev/c11-native-payload-closure` | `8c899ff0` | Runtime 与最终 ZIP 校验 |
| `dev/c11-browser-e2e-business` | `9cb1294b` | Playwright 真实浏览器验收 |
| `dev/candidate-workspace-continuity` | `2c5f940c` | 候选人流程连续性试验 |

## 管理决策

1. 不删除 `main`、不 force-push、不伪造 Pre-Git 历史提交。
2. 按 [仓库治理规程](REPOSITORY_GOVERNANCE.md) 只在 `main` 集成成果，所有更新均须通过 PR。
3. 这些分支目前全部保留作为审计/回滚参照。是否清理需要逐分支 compare，不能仅依赖已合并 PR 的列表。
4. 旧 branch 和已合并 PR 都不能被当作 Release；唯一已存在的历史 GitHub Release 标签为 `v0.8`，其附件是 `SRW_v0.8.8_Web_Portable.zip`。
5. 此表为**盘点快照**，以后合并新的 PR 不要求对历史 SHA 反复回填；正式开发进度应以 `main` 的 HEAD 与 CI 为准。
