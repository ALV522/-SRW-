# SRW G1：暂不启用 GitHub main 分支保护时的替代流程

状态：**ACTIVE, TEMPORARY**（经负责人授权，2026-10-20）

## 原因与边界

仓库当前暂不启用 GitHub Rulesets / Branch Protection。本制度通过显式任务分支、预编辑检查、PR/CI、合并前二次校验、main 推送后审计**降低**误操作概率；它不能与服务器端权限规则等价：任何具有 main 写权限的主体仍可绕过它，GitHub Actions 的失败只能事后发现，不能阻止那次 push。

本临时制度在项目负责人明确表示可开启主线保护时再迁移，未获授权不得私自变更仓库规则。

## 强制操作顺序（所有 Agent）

1. **先读** AGENTS.md → 全部必读 G1 文件、现有 CI/目标 SHA，检查 Issue 和该变更的 Windows/Web/证据风险。
2. 从最新 main 创建一个**专用任务分支**。禁止任何 Agent 直接修改或 push main；禁止 force push、重写/tag 移动。工作树初始必须干净。
3. 在第一次代码或文档编辑前运行 `python scripts/agent_preflight.py --issue 41 --acknowledge-reading`（根据实际 Issue 编号修改）。若 FAIL，停止修改并先解决阻断。此动作仅证明文件/版本等机器条件，不证明 Agent 真读了文档。
4. 在分支完成最小改动、回归、当前源 SHA 清单更新、准确身份检查；为用户提供 PR、风险与证据。
5. **只能**走 PR 到 main。打开 PR 后等待相同 PR Head SHA 的 governance-contract、Ubuntu/Windows Source Gate 和 Chromium 检查完成且成功（其它受影响 Host/Runtime/安全检查亦须通过）。不能因为只有红黄状态就提前合并；必须记录手动合并前检查的 SHA 和状态。
6. 合并之前再次读取目标 main SHA 和 PR Head SHA。若 base/head 意外移动，重新评估差异并重新运行适当测试。不要以旧 PR 的 CI 为新头部背书。
7. 合并后重新读取 main 完整 SHA，确认是预期的 PR 合并，然后核对 main 的 CI 与必需检查。不因合并成功而声明 Windows GUI、Native ZIP 或双端生产 PASS。
8. `push main` 的 Governance audit 将调用 GitHub API 检测提交是否与已合并 PR 关联。任何直接 push 应 FAIL/报警并建立 Incident Issue；**它不能阻止已经发生的提交**。未经核实不要自动强制回滚或 force-reset main。
9. 禁止发布正式 Release，除非目标负责人明确批准且所有与载体相关的工件验收已有事实证据。不要把 PR CI 等同于发行质量。

## 无保护期“人类操作原则”

- 负责人可以只说“按 G1 继续推进”而不逐个批准 bug；Agent 必须按本文件工作。
- 如果 Agent 提议直接提交 main、跳过红色 CI、放宽哈希检验或复用旧 Windows 工件验收，请直接要求它停止。
- 如果 GitHub UI 的 “Merge” 仍可点击，只能在相关检查均成功且合并身份没有漂移时按下。可点击不等于适合合并。
- 本期 PR 允许 Agent 按授权在所有适用 CI 成功后自行合并普通 B/C 类工程变更；A 类、真实数据危险操作或 GA/RC 需负责人批准。
- 当前阶段真实数据、生产 ZIP、密钥不得上传 PR 或 Actions 记录。

## 日常检查与版本分离

- Source/API、Chromium、Windows GUI、Web+EXE、Runtime/Knowledge、备份/恢复必须分别声明 PASS / FAIL / BLOCKED / NOT RUN。
- SOURCE_RECOVERY_MANIFEST.sha256 保持不可变，SOURCE_MANIFEST.sha256 只能根据**审查后的真实更改**更新。
- G1 是治理标识，不是 Product SemVer。当前旧 C11 VERSION 在单独版本迁移 PR 通过前保持原值。

## 何时终止替代方案

当项目负责人允许并实际激活主线保护后：强制 PR、必需 CI 和禁止 force-push 转由 GitHub 服务端执行。本文件保留为历史工作流程记录，仍需强制任务阅读和证据纪律。

## 复制给其他 Agent 的简短命令

> 读取 AGENTS.md 和 docs/NO_BRANCH_PROTECTION_PROTOCOL.md 及其必读文档。此仓库 main 暂无服务器端保护，你不得直接修改、push 或 force-push main。先在最新 main 的专用任务分支运行 agent_preflight.py，使用 PR，等待相同 Head SHA 的全部适用 CI 成功，再核对 main 和 PR Head 未漂移后合并；合并后检查 main CI。没有测试证据绝不声称已验收。执行 Issue 优先级而不是创造新功能。
