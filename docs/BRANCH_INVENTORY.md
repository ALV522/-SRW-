# GitHub 分支盘点快照（2026-10-19）

GitHub API 返回 **36 条分支（含 `main`）**。创建本次文档工作分支前为 35 条；当前多出 `docs/repository-status-readme-20261019`。此文件是**时点快照**，各分支 HEAD 会随未来的提交发生变化。

分类：`dev/` 23，`fix/` 7，`docs/` 2，`explore/` 1，`integration/` 1，`repair/` 1，`main` 1。

| 分支 | 审计 Head（短 SHA） | 性质 |
|---|---|---|
| `main` | `c9d70cd48d03` | 当前唯一整合源码主线 |
| `dev/c11-backup-integrity-restore` | `e669c5301bbd` | 历史业务/交付专项开发现场 |
| `dev/c11-browser-e2e-business` | `9cb1294bd996` | 历史业务/交付专项开发现场 |
| `dev/c11-isolated-runtime-overlay` | `5384da1354c3` | 历史业务/交付专项开发现场 |
| `dev/c11-native-payload-closure` | `8c899ff0cc2b` | 历史业务/交付专项开发现场 |
| `dev/c11-offer-scorecard-browser-closure` | `5e6a1a23731a` | 历史业务/交付专项开发现场 |
| `dev/c11-prepared-native-smoke` | `d7e4ba72a9e3` | 历史业务/交付专项开发现场 |
| `dev/c11-recover-external-dependencies` | `b4d9feb49bda` | 历史业务/交付专项开发现场 |
| `dev/c11-source-host-native-assembly` | `94933655a4eb` | 历史业务/交付专项开发现场 |
| `dev/c11-windows-gui-log-acceptance` | `328cf65094a0` | 历史业务/交付专项开发现场 |
| `dev/candidate-workspace-continuity` | `2c5f940cb9d0` | 历史业务/交付专项开发现场 |
| `dev/convergence09` | `bc1d3ca04f21` | 历史业务/交付专项开发现场 |
| `dev/convergence10-system-integrity` | `c68249c397ab` | 历史业务/交付专项开发现场 |
| `dev/convergence11-backup-truth` | `d1f9fdbff59a` | 历史业务/交付专项开发现场 |
| `dev/convergence11-business-workflow-closure` | `2ae639dccb3a` | 历史业务/交付专项开发现场 |
| `dev/convergence11-candidate-interview-workspace` | `160100ffee76` | 历史业务/交付专项开发现场 |
| `dev/convergence11-candidate-workspace-page` | `d149a4af9631` | 历史业务/交付专项开发现场 |
| `dev/convergence11-criteria-editor-preservation` | `88baeec303f5` | 历史业务/交付专项开发现场 |
| `dev/convergence11-job-setup-wizard` | `d063b8277142` | 历史业务/交付专项开发现场 |
| `dev/convergence11-operational-action-center` | `21cb3d826b5a` | 历史业务/交付专项开发现场 |
| `dev/convergence11-operator-briefing-ui` | `742fcc6965da` | 历史业务/交付专项开发现场 |
| `dev/convergence11-project-guidance` | `ca08283bb306` | 历史业务/交付专项开发现场 |
| `dev/convergence11-review-center` | `df64b44dd107` | 历史业务/交付专项开发现场 |
| `dev/convergence11-review-resolution` | `08dd6b76088d` | 历史业务/交付专项开发现场 |
| `fix/c09-windows-sqlite-lifecycle` | `f3dc42b44a5a` | 历史缺陷/修复工作现场 |
| `fix/c11-active-queue-and-local-day` | `24cf90101a6b` | 历史缺陷/修复工作现场 |
| `fix/c11-exact-review-deeplinks` | `4addee785948` | 历史缺陷/修复工作现场 |
| `fix/c11-native-package-allowlist` | `4ea2788d87f0` | 历史缺陷/修复工作现场 |
| `fix/c11-portable-input-preflight` | `41ff247e3b75` | 历史缺陷/修复工作现场 |
| `fix/c11-windows-smoke-repeatability` | `dbe0e505c70b` | 历史缺陷/修复工作现场 |
| `fix/ci-notification-noise` | `dcc44921d7aa` | 历史缺陷/修复工作现场 |
| `docs/repository-governance-legacy-20261018` | `a1d256ceb6fb` | 文档、历史治理或本轮 README PR |
| `docs/repository-status-readme-20261019` | `deed1fe0a9a0` | 文档、历史治理或本轮 README PR |
| `explore/html-site-prototype` | `2c366e5941c1` | E1–E5/Native SOURCE Lab 隔离实验 |
| `integration/c09-stable` | `63c8ac6d7183` | 历史 C09 整合 |
| `repair/c08-source-and-ci` | `6072d74b1883` | 历史 C08 恢复 |

## 管理结论

1. **只有 `main` 是整合产品源码主线**。历史 `dev/` / `fix/` 不等同于正在维护的发行版本，也不能直接作为 Portable 的基础。
2. `explore/html-site-prototype` 保留 E1–E5 和 Native SOURCE Lab 的大量试验与特定 CI 证据。不得直接与 `main` 整体合并；应按业务依赖逐项审查、重新实现安全权限/数据库迁移并附测试。
3. 新增的本次 `docs/repository-status-readme-20261019` 是文档治理工作分支，审查后由 PR 合入主线，不单独发布软件版本。
4. **不根据分支前缀、是否已合并 PR 或是否过时自动删除**。清理前必须 compare `main...branch`、核对唯一文件、已合并历史、业务证据、下载工件与 SHA。此列表**不对任何分支作“可以安全删除”判断**。
5. 只有经过对应 CI + 实机工件验证的明确 SHA 才能提升交付状态；历史 `v0.8` Release 仅是历史 Web Portable。

入口：[主 README](../README.md) · [仓库治理](REPOSITORY_GOVERNANCE.md) · [正式路线图](ROADMAP.md) · [发布规程](RELEASE_PROCESS.md)。
