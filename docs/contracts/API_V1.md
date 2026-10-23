# SRW `/api/v1` 产品契约（G1 首版）

> 本文件是 Windows EXE 与本地 HTML/Browser **共同消费**的 HTTP 产品契约说明。机器可读的精确路由清单以 [`api-v1-inventory.txt`](api-v1-inventory.txt) 为准，由 `scripts/check_api_contract.py` 在 CI 中校验：任何路由新增、删除或方法变更必须**在同一变更中刻意更新基线**，否则 Source Gate 失败。本文件不替代该清单，只说明分域语义与共同规则。

## 1. 版本与兼容规则

- 契约版本即路径前缀 `/api/v1`。破坏性变更（删除路由、改变必需字段、改变状态机合法性）属于宪章 B 类，需跨端影响评审；纯增量（新路由、新可选字段）可在回归覆盖下直接合入。
- Windows 与 Local Web 消费**同一份**契约与同一个权威 Core；不允许任何载体私自定义端点或第二套业务语义（宪章 A6）。
- 错误码全局一致：`404` 资源不存在；`409` 业务不变量冲突（含 `invariant_conflict`、`provider_not_ready`）；`422` 请求校验失败；`403` 会话/授权失败。错误体形如 `{"detail": ..., "error": {"code": ...}}`。

## 2. 分域索引与关键不变量

| 域 | 代表路由 | 不变量（摘要） |
|---|---|---|
| 运行时 | `runtime/ready`、`runtime/info`、`runtime/shutdown` | 健康/身份可观测；shutdown 仅 Host 模式可用 |
| 项目与标准 | `projects`、`protocol-workspace`、`protocol-revisions/{id}/publish` | Draft 不自动发布；发布必须人工显式触发 |
| 候选人与材料 | `candidates/{id}/sources/text`、`workspace` | 材料版本单调递增；Source 不可变，修订发布新版本 |
| 证据与判断 | `claims/{id}/review`、`candidates/{id}/verifications`、`decision` | 缺失证据≠零能力；冲突不自动取舍；HumanDecision 只能人工显式产生 |
| 面试与评分 | `events`、`scorecards` | 独立评分不可覆盖；分歧不自动平均 |
| Offer | `candidates/{id}/offers`、`offers/{id}/status` | 状态链人工推进；Accepted 不自动 Hired |
| 知识与治理 | `knowledge/status`、`knowledge/search`、`projects/{id}/knowledge/apply` | 知识建议只进 Draft；携带来源溯源；不自动发布 |
| 设置与 Provider | `settings/providers`、`settings/providers/{name}/test` | 探测用合成载荷，不带候选内容；密钥只存本地 SecretStore |
| 运维与导出 | `pipeline`、`candidates.csv`、`contact-list.csv`、`audit`、`backups` | 导出带公式注入防护；审计只读投影 |
| Supervisor（ADR-0003） | `supervisor/attach`、`supervisor/heartbeat`、`supervisor/detach`、`supervisor/status` | 仅 Supervisor 进程注册；附着令牌每次附着独立、仅存内存；未知附着 404、令牌不符 403；最后一个载体 detach 后按空闲宽限期自退 |

## 3. 双载体一致性要求

- 同一工作区任意时刻只有一个权威 Core 写入者（`data/app.lock` 租约，见 [工作区租约合同](../WORKSPACE_LEASE_CONTRACT.md)）。
- 所有重要写入走事务级 revision/If-Match 校验；过期写入明确拒绝且不产生虚假审计（DUAL_CARRIER_PLAN D3；正式 CAS 属 Issue #43 范围）。
- 本地 HTTP 仅绑定 loopback；远程访问、云端登录不在本期范围。
- Supervisor 模式下 Core 与载体分离：Supervisor 是唯一租约持有者（`app.lock` 的 `edition="supervisor"`），
  载体经附着协议接入；关闭任一载体不影响其他载体（ADR-0003 S1/S5，特性开关默认关）。
- 会话强制开启时（Supervisor `--enforce-sessions`，相位 2 开关）：仅 loopback Origin/Referer 可访问；
  所有变更请求须携带一次性会话 `X-SRW-Session` + `X-SRW-Token` 与匹配的 `X-SRW-CSRF`（附着时下发，
  detach/静默/Supervisor 退出即撤销）；attach/heartbeat/detach 与健康探针以附着令牌自主认证，豁免会话规则。

## 4. 变更流程

1. 新增/修改路由 → 同步更新本文件分域表（语义变化时）与契约测试。
2. 运行 `python scripts/check_api_contract.py --write` 重新生成基线，并在 PR 中逐行审查 diff。
3. 破坏性变更附跨端影响说明与回归证据；Source Gate 的清单校验必须通过。
