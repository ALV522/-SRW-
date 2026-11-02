# ADR-0003 · GitHub API-native 预编辑通道（G1.2）

状态：**Accepted / ACTIVE** · 产品负责人于 2026-11-02 授权 · 关联 #132、#174、#103。

## 问题与事实

#174 的 `scripts/agent_preflight.py` 用真实 `git ls-remote origin refs/heads/main` 保护本地 Git checkout 免受过时 main 与伪造远端污染。这一检查对**有 Git 工作树的开发者**合理，但云端 AI 环境可能只有已授权的 GitHub API/连接器，并不能解析 github.com 域名或创建本地 checkout。将一种传输方式写成所有开发的唯一必要条件，会使有能力进行 GitHub 受审计分支/PR 操作的执行者无法提交任何 README、文档或代码。

2026-11-02 A 在云端直接运行 `git ls-remote https://github.com/ALV522/-SRW-.git refs/heads/main` 得到 `Could not resolve host: github.com`；同一环境经 GitHub API 成功读取 `refs/heads/main=e6fab773127e49052aaec227b39a76f338c439ae`。这证明本次障碍是 Git transport，不是仓库状态不可核验。

## 决定：两个预编辑通道，等效的主线身份与发布约束

1. **Local-Git mode（保留原合同）**：在独立、干净的任务分支上执行当前 `python scripts/agent_preflight.py --issue N --acknowledge-reading`；真 `git ls-remote` 检查若不通过则此模式失败。不能用模拟、缓存 SHA、跳过远端的 git 命令“补绿”。
2. **GitHub-API-native mode（新正式通道）**：适用于执行者只有经过用户授权的 GitHub Connector/API、没有可信本地 Git checkout 或 Git transport 不可用的情况。无需运行**不适用的本地** `agent_preflight.py`，但必须在首次变更前按下述流程采集并报告**真实 API pre-edit** 证据。不要宣称 `agent_preflight PASS`。
3. **本通道不是直接 push main 的许可**。分支、PR、Source Manifest、应用 CI、合并后 main push 检查、风险审查、Windows/Browser 验收分级保持原制度。产品 A1–A8、旧版功能保真和敏感数据禁入 Git/CI 保持不可变。

### API-native pre-edit 事实与执行序列

- 用已授权 GitHub API 读取当前仓库 `GET /repos/ALV522/-SRW-/git/ref/heads/main`，记录**完整 commit SHA**、任务 Issue、读取时间及所需的治理/业务文件；不得信任 Issue 中粘贴的 SHA、过时 README、历史 CI 或第三方仓库替代。
- 使用 GitHub API `create_branch` / `POST /git/refs` **从刚核验的确切 commit SHA** 创建独立任务分支；在**首次内容写入前**重新读取新 `ref` 验证与 source main SHA 相等。若不同或 branch 已存在，终止并调查，不覆盖。
- 编辑仅提交至该分支。允许 Git Trees/Commits 或 Contents API；使用 base tree + **确切 parent commit** 创建不可重写的新 commit，更新分支 ref 必须 fast-forward / compare-and-swap。任何状态漂移均停止或从新 main 重新设计。
- 更新 `SOURCE_MANIFEST.sha256`：对真实新文件 UTF-8 字节计算 SHA-256；不删除历史证据、不动 `SOURCE_RECOVERY_MANIFEST.sha256`，独立检查新增/改动文件和 manifest entries。写入后读回 GitHub tree/commit 与目标文件，对 Git SHA 和目录变更进行确认。
- 打开 PR 并在正文明确记 `Pre-edit mode: GitHub-API-native`、main SHA、首次分支 ref、写入前检查、相关 Issue，明确 `Local git preflight: NOT RUN (no checkout/Git transport)`，不能反向伪造 local-Git PASS。
- 只按准确 PR HEAD 的 Source Ubuntu+Windows、Chromium、Governance 和所有受影响 Host/Native/安全 checks 判断合并；非作者工作轨 Review 记录真实身份，同账号不得称不同 GitHub 账号 APPROVED。合并前后都要重新读 main/PR HEAD 与完整 CI；跨 SHAs 不继承绿灯。

### 验收与适用边界

- API 读取是 GitHub 侧的真实远端身份来源，但**不等价于本地 Git 远端的可用性**、本地可运行 Python 或 Windows WPF 实机验证。无法执行的本地测试必须写 NOT RUN；适用的 CI 失败仍禁止合并。
- 已提交但缺旧形式 preflight 的 PR **不得编造历史日志**：在负责人授权的个案例外中，可核对创建时 main/branch parent、PR commit 图、远端 Source Manifest/CI 和负例，再决定是否免于无意义重建。无独立证据或出现异常则继续 BLOCK。
- 若当前执行环境具备健康的 local-Git checkout 和远端访问，应优先走 Local-Git mode；不得以 API-native 作为绕过可执行失败用例、私有数据边界或 release gate 的理由。

## 不采纳的方案

- 放开直接 push main、去掉 exact-HEAD CI 或自称 Windows 已验：拒绝。
- 在云端生成假的本地 checkout / 虚构 `git ls-remote` 输出：拒绝。
- 每个文档修改都要求 B/C 在另一台 Windows 代跑本地预检：拒绝，属于不必要的协作串行瓶颈。

## 追溯与回滚

本 ADR 与 AGENTS、无保护协议、协作指南应在同一治理 PR 中生效；改变只涉及工作方式，不更改 VERSION/Schema、源码应用行为、Host/Runtime/Knowledge。若 API 远端状态/Manifest/CI 检查证明不充分，应以新的受审计 PR 收紧或暂停 API-native 模式，不使用 force-reset main。
