# SRW 任务驱动工作台：UX-2a 至 UX-2e（执行路线）

状态：ACTIVE DESIGN / INCREMENTAL IMPLEMENTATION · 2026-11-10 · 关联 #235、#240、#63、#43。

## 决策与边界

保留现有 SRW Core、Windows WPF/WebView2、Local Browser/HTML、SQLite、Source/Claim/Judgment/HumanDecision、Interview/Scorecard、Offer、联系、Knowledge、AI/OCR/ASR 与备份恢复。不另建 UI 框架、第二套 Core、云帐号，不自动替 HR 做人工判断。历史 v0.8.12-R2 是能力保真对照，不是可以整文件覆盖的源码。

UI 的基本对象层级：**今日需要完成的操作 → 项目 → 候选人 → 具体事件/证据 → 人工核实与提交**。页面负责定位、解释、反馈和恢复上下文；对象归属、证据新鲜度、状态转移、权限、审计和 CAS 必须由 Core 决定。

## 四种界面角色

| 角色 | 操作者应一眼看到 | 禁止做的事 |
|---|---|---|
| 首页 | 由真实 Core 投影得到的业务队列、运营待办、人工复核；项目快捷入口是次级导航 | 按 UI 记忆猜测候选人或默认选择最近事件 |
| 项目工作区 | 已发布标准、下一动作及原因、候选人/面试/运营上下文 | 将候选人列表或 KPI 当成最终业务决策 |
| 候选人工作区 | 当前材料与 Source/Claim、阶段和事件、上下文版本、下一人工动作 | 用旧材料提交新决策、跨项目读写 Scorecard |
| 设置与辅助工具 | 岗位模板、Knowledge、Provider、备份恢复和任务诊断 | 把管理工具等同于每天的主任务 |

## 渐进式交付

### UX-2a：项目恢复入口（本 PR）

- 从现有 GET /api/v1/projects 只读投影拿项目列表，最多显示四项，不自造优先级；仅过滤归档/重复/无身份项。
- 在三组核心业务队列之后、KPI 之前，提供有明确项目标题的“进入工作区”；一次显式点击进入准确项目，项目内下一动作继续由 GET /api/v1/projects/{id}/pipeline 的 current next_action 决定。
- 只用 textContent/DOM API 输出外部项目名称，不把项目文本拼进 onclick、CSS 选择器或 HTML。
- 异步请求完成时若已经离开首页，则不回填旧 DOM；读取失败只隐藏这个**次级**入口，不阻断主业务队列。
- 已有操作预算的首页→项目列表→工作区是两次显式点击；该具体片段目标降为一次。**不能由此宣布首页→新建面试→提交反馈→独立面评的原 9→≤6 全链目标达成。**

### UX-2b：从首页到可信任务对象（P0 下一阶段）

- 先区分 Core 已提供明确 candidate_id/event_id 的待办和“需要 HR 自主选择对象”的探索性工作。前者可以直接定位；后者必须展示选择界面。
- 为项目 next_action 建立轻量、分页的 Core 投影或复用现有队列，不在 Browser 内复制业务优先级、跨项目授权或 CAS 检查。
- 从首页点击瞬间再次读 Core，若 candidate archived、event 非本项目、Scorecard 非 interview、Claim/Published revision 过期则 fail closed；A→B 延迟响应不得把旧对象覆盖新表单。
- 分别实测（甲）已存在待评面试事件与（乙）从未排期、需要安排→完成反馈→独立面评两套路径。全链同源合成 fixture 的首页 9→≤6 为产品目标，不通过偷去人工步骤或替换起点凑数。

#### UX-2b 首轮面试快捷目标（Core/API 实现切片）

Dashboard 的 `operational_queue` 增加 `ready_to_schedule_interview`：只投影招聘中项目、未归档且未合并候选人、当前 Published protocol 含有效面试阶段、当前 Published material 存在、且尚无已排期/已完成结构化面试的候选人。每位候选人单独成行；多个目标由 HR 明确选择，不按最近候选人或前端缓存默认选择。该快捷入口面向首轮面试；后续轮次仍从候选人工作区创建。

点击时前端重新读取 Dashboard 并逐项比较 project/candidate/protocol/material identity；保存排期时 Core 再验证同一身份、项目状态、候选人归属、Published revision/material 及是否已有面试，并把 project/material revision identity 固化到该面试事件元数据。目标过期、归档、跨项目、版本变化或重复排期均 fail closed，不创建 event/audit。快捷入口只减少定位步骤，排期、完成反馈和独立 Scorecard 的人工点击均保留。精确 HEAD 的 CI 和真实 Chromium 结果未出之前，不记为 PASS。

### UX-2c：跨页面上下文纪律

- 所有 mutation 通过 Core API；UI 仅持有当前 project/candidate/event、表单序列和待提交 draft。导航和异步返回必须检查来源上下文身份。
- 保留可见的唯一返回入口、筛选恢复、历史深链、键盘可访问、错误提示与不可恢复状态显式提示。
- 切换候选人、归档、过期 Source、另一个项目的事件或非面试类型，必须有真实 Chromium+SQLite 负例。

### UX-2d：前端模块化（R4 小切片）

- app.js 当前聚合 dashboard、project 与 candidate；后续按 shell、dashboard task surface、project workspace、candidate workspace 拆独立 ES modules，每次只迁一项既有展示职责。
- api-client.js 为共享请求入口；禁止在展示模块复制 fetch/CSRF/错误解析或构造新的产品状态权威。
- 页面 DOM 渲染与操作 intent 解耦；按当前业务接口与点击路径保真，杜绝为拆文件引入第二路由、第二数据库或新框架。

### UX-2e：双载体与发行前验收

- Browser 在 1440×900、1366×768 做首屏、滚动、键盘导航和截图对照；精确 HEAD Source、Chromium Ubuntu/Windows、Governance 通过。
- Windows 正式 main SHA 的完整 Native ZIP 须在目标机独立实测窗口 RECT、DPI/滚动、退出/DB 独占与同一事件独立面评。源码 CI、浏览器 PASS、Host build 不是 WPF PASS。
- #43/#124/#130/#159、#230 安全会话与备份恢复的发行阻断保持原位。无外部 Runtime/Knowledge 体积/许可证据不得声称 Native 已瘦身。

## 最小可观测验收表

| 维度 | UX-2a 目标 | 当前断言形式 |
|---|---|---|
| 真实入口 | 首页指定项目→对应工作区，1 次显式点击 | 真 Chromium+合成 Core，按项目 id 读回核对 |
| 不误选对象 | 只定位 project，不自动打开 candidate/event/scorecard | 当前页无 candidate workspace、无 modal |
| 安全投影 | 不显示已归档、重复、缺 id 项 | 模块负例；不修改业务 Core 规则 |
| 页面层级 | 三组队列在项目快捷入口之前，KPI 在后 | 既有 UI235 结构测试 + 同规格截图 |
| 工件身份 | API-native 分支、SOURCE_MANIFEST、PR/CI、后续 WPF 分开标记 | 新 HEAD 才能引用新结果 |

## 协作与集成次序

B/C 暂不能响应时，A 临时拥有 #240 的 UI 开发与技术架构，B/C 的非作者工作轨和实机验收仍保留。#248 API bootstrap 的准确 HEAD 必须先收口；本 UI PR 可以独立构建和验证，但不能越过 #248 修改 main。未来 main 改变后需一次性跟进根 Manifest、重跑准确 HEAD 适用 CI；A 的 COMMENTED 不能写成独立 GitHub APPROVE。

完成标志是 HR 业务操作真实减少且不丢失原有能力，而不是页面更漂亮、文件更小或测试总数增加。
