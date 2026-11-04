# IA-1 navigation map (issue #215)

This slice only changes navigation and information presentation. No Core, API,
Schema, worker or storage behaviour is touched. Every former page stays
reachable; where a page could not be truly merged it is kept as an in-page view
instead of being hidden.

## 1. Sidebar: 6 → 3

| 旧入口 (page key) | 新位置 | 说明 |
|---|---|---|
| 工作台总览 (`dashboard`) | **今日待办** (`dashboard`) | 同一页面，改名并重写标题文案；KPI、今日业务队列、运营执行队列全部保留 |
| 招聘项目 (`projects`) | **招聘项目** (`projects`) | 不变 |
| 系统设置 (`settings`) | **设置** (`settings`) | 同一页面，新增「工作台设置」四张入口卡 |
| 岗位模板 (`templates`) | 设置 → 岗位模板 | 页面未改；`go('templates')` 仍直达，侧栏高亮「设置」，标题显示「设置 · 岗位模板」 |
| 知识库 (`knowledge`) | 设置 → 知识库 | 同上 |
| 后台任务 (`tasks`) | 设置 → 后台任务 | 同上 |

## 2. Project workspace: 8 tabs → 3

| 旧页签 (tab key) | 新位置 | 是否真正合并 |
|---|---|---|
| 项目首页 (`overview`) | **概览** | 改名 |
| 建岗与标准 (`criteria`) | **岗位与标准** | 改名，页面不变（jobsetup 全流程保留） |
| 候选人收件 (`candidates`) | **候选人** → 视图「全部」 | 合并 |
| 筛选与决策 (`cockpit`) | **概览** 内「决策漏斗与候选池」区块 | 是：`cockpitTab` 直接渲染进概览，含分页与「生成证据短名单」 |
| 版本与审计 (`audit`) | **概览** 内「版本与审计」区块 | 是：`auditTab` 直接渲染进概览，含分页 |
| 面试流程 (`flow`) | **候选人** → 视图「面试」 | 是：`flowTab` 渲染在同一页签内，含搜索、排期、Scorecard、复评 |
| 跟进运营 (`ops`) | **候选人** → 视图「待办」 | 是：`operationsLearningTab` 渲染在同一页签内 |
| 质量复核 (`quality`) | **候选人** → 视图「数据质量」 | 是：`qualityTab` 渲染在同一页签内（身份复核 / 校准锚点 / 纠错） |

旧 key 全部由 `projectWorkspace()` 顶部归一化处理，任何调用方（含深链、
`openOperationalItem`、`openWorkbenchItem`、`openCandidateProjectFlow`）无需修改：

```
cockpit -> overview + overlay section ov-cockpit
audit   -> overview + overlay section ov-audit
flow    -> candidates, view=flow
ops     -> candidates, view=ops
quality -> candidates, view=quality
```

## 3. Deep-link callers verified

| 调用点 | 传入 tab | 落点 |
|---|---|---|
| `openOperationalItem('pending_interview_feedback', …)` | `flow` | 候选人 → 面试视图，随后打开 Scorecard |
| `openOperationalItem('overdue_contact' / 'today_contact', …)` | `overview` | 概览，随后打开行动计划 |
| `openWorkbenchItem(…, 'PREPARE_INTERVIEW')` | `flow` | 候选人 → 面试视图 |
| `openWorkbenchItem(…, 其它)` | `cockpit` | 概览 → 决策漏斗区块 |
| `openReviewItem(…, 'identity'/'judgment'/'claim')` | `quality` | 候选人 → 数据质量视图 |
| `openCandidateProjectFlow()` | `flow` | 候选人 → 面试视图 |
| 候选人工作台「返回」 | `candidateReturnTab` | 归一化后回到 3 页签之一 |

## 4. Measured numbers (synthetic Chromium workspace)

| 指标 | 改动前 | 改动后 |
|---|---|---|
| 侧栏一级导航 | 6 | **3** |
| 项目页签 | 8 | **3** |
| 一级 + 项目页签合计 | 14 | **6** |
| 可达界面（含候选人页内 4 个视图） | 14 | **10** |
| 「候选人列表 → 面试保存」点击数 | 4 | 4（本切片不改，IA-2 负责内联表单） |
| 候选人工作台 `btn.primary` 数量 | 5 | 5（IA-2 收敛为 1 个主动作） |
| 旧 key 落点为空/报错 | 0 | **0** |

复现：`python browser_acceptance/test_ia1_navigation.py -v`（5 条真实 Chromium 用例，
含点击数断言与 5 个旧 key 的可达性断言），以及 `test_flows.py` 的 17 条既有流程。

## 5. Not converged in this slice

- 候选人仍是「抽屉 + 3 个步骤」，没有变成单页五段 → IA-2。
- 面试排期、Scorecard、人工核实、电话筛选仍是 30 个 modal 中的成员 → IA-3。
- 候选人工作台仍有 5 个 `btn.primary`，每屏唯一主动作尚未落地 → IA-2。
- 「概览」现在串联 3 组请求（overview + cockpit + audit），首屏比之前多两次读取；
  若后续出现性能反馈，可改为按需加载（折叠区块）。

## 6. Rollback

单 PR 可整支回退：`git revert <merge commit>` 即恢复 6/8 导航；旧路由未删除，
因此回退不会留下死链。
