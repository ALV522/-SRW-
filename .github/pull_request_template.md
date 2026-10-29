# SRW PR · G1 Governance / Acceptance

## 开发任务与业务增量
关联 Issue：
用户原来不能完成：
现在应当可以：
涉及的产品宪章 A/B/C 条款：

## 必读声明（必须确实阅读后勾选）
- [ ] 已阅读 AGENTS.md 及指定必读治理文件
- [ ] 已核对准确源码 SHA、版本、Schema 和工件边界
- [ ] 已给出修改影响与相应业务/双端验收范围
- [ ] 不以源代码或浏览器通过冒充 Windows/发行通过

## 更改范围与兼容性
- Core/API：
- Windows GUI/Native：
- Browser/HTML：
- Schema/Runtime/Knowledge：
- 旧版业务能力是否等价保留：
- 数据/隐私风险及回滚办法：
- VERSION_POLICY / release identity 变更：

## 实际验收（未运行填写 NOT RUN；失败填写 FAIL/BLOCKED）
| 类型 | SHA/工件 | 环境/输入 | 执行命令或人工步骤 | PASS / FAIL / BLOCKED / NOT RUN 与证据 |
|---|---|---|---|---|
| Source/API | | | | |
| Chromium E2E | | | | |
| Windows WPF GUI | | | | |
| Web+EXE 双端 | | | | |
| 恢复 / Provider | | | | |

## 残余问题与下一步
P0/P1：
建议下一个最小闭环：
需要产品负责人决定的事情：

## P4 处置（必填，恰选一；由 `check_governance_contract.py --check-pr-body` 校验结构）

- P4 处置：<已修（PR/提交）| 已登记（#155/具体 Issue）| 明确接受风险（理由）>

> 只写一个标记并在其后给出具体指向或理由；不要把三个标记都留着（那样等于没处置）。
> 该门禁只证明"处置被明确写下且可检索"，不证明修复真实或风险已被他人接受——语义仍由人工审查。

## G1.1 独立审查与队列元数据（实际证据，不是勾选证明）
- 干净任务分支 / pre-edit preflight 真实输出、执行时间与证据链接（未做填 `NOT RUN → BLOCKED`）：
- 准确 main/base/head SHA、自动 bot 的 exact-HEAD CI 证据评论 URL（若无则 NOT AVAILABLE；bot 不是合并许可）：
- 不同工作轨审查是否有独立 GitHub 审批身份：`YES / NO（共用账号） / NOT RUN`：
- SOURCE_MANIFEST 新增/删减/修改项、实际源码 diff、历史清单核查：
- 非作者轨道 reviewer、正式 Review URL、审查的 HEAD、结论 `ACCEPT/NEEDS_CHANGES/BLOCK`：
- Windows/POSIX 文件系统、Host/Browser 或安全权限差异负例：
- RED → GREEN 的用例与实际环境；若没有负例原因：
- 冲突域 / 队列位置 / 适用的人工验收和最后复核：
