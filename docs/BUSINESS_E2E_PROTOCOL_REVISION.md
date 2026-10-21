# C11 E2E-07：招聘标准版本变更后的人工决定失效

## 目的

对现有 E2E-06（**候选人材料变更**）进行独立补充：当招聘项目**重新发布评价标准**时，即使候选人原始 Source/材料字节没有变化，旧 HumanDecision 也不能继续作为当前决策。特别是新增一个 `decision_critical` 且 `verification_required` 的 Criterion，任何确认“推进”的动作都必须满足新标准。

该场景必须运行于 **真实 Chromium 浏览器 → C11 API → 临时合成 SQLite**，不模拟业务 HTTP，也不引入 AI Provider 或真实候选人数据。

## 自动验收步骤

1. 浏览器新建项目，编辑并显式发布第一版需要人工核实的 Criterion。
2. 浏览器新建候选人、发布合成文本 Source、执行人工核实，生成真实 verification_note/Claim/Judgment，再显式做出 `advance` HumanDecision。
3. 确认该决定属于当前 `decision_context_hash`，保存当前全部 Source ID。
4. 退出候选人工作区，在项目“建岗与标准”中从正式发布的第一版**创建新的 Draft**；新增另一项具有决策关键性和强制核实要求的 Criterion；人工保存并发布第二版标准。
5. 验证 **当前招聘标准 revision ID 已更新，但候选人 Source ID 集合完全不变**。
6. 读取候选人工作区：决策上下文哈希必须改变；旧 `advance` 被标记 stale；新标准未满足时 `decision_ready=false`，必须有阻塞 Criterion。
7. 直接绕过 UI 调用 `/decisions/reaffirm` 不得成功，不能生成新决定/假审计；在 UI 的“按当前证据重申”按钮也必须禁用。

## 与已通过场景的关系

E2E-06 覆盖 **Source/MaterialRevision 改变导致失效以及重新核实后人工重申**；E2E-07 覆盖 **ProtocolRevision 改变（材料不变）导致失效和阻断未经核实的重申**。两者相互独立，不能以“材料变化路径已通过”替代标准版本变化验收。

该实验仍然不代表 WPF/WebView2 真实 Windows 业务场景、生产 Knowledge DB、OCR/ASR 或 AI Provider 已完成验收。最终是否 PASS 以精确提交 SHA 对应的 GitHub Actions 为准。

## 保存请求同步回归

E2E-06/07 点击“保存草案”后，必须等待当前 Draft revision 的真实 `PATCH` 返回 HTTP 200，再读取已保存标准或继续发布。页面上已有的“发布当前标准”按钮可见，不代表异步保存已经完成。

E2E-07 在第二次保存时，将一次真实浏览器 PATCH 的发出延迟 300 ms；不替换响应，不模拟 Core，也不改变业务断言。此延迟用于暴露旧同步方式读取旧 Draft 的竞态，不能作为等待保存完成的方法。保存完成仍由对应请求的成功响应确定。
