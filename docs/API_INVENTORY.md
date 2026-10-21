# SRW API 库存（R1 冻结基线）

> 由 `python scripts/api_inventory.py --write` 生成，请勿手工编辑。
> 本文件是 ADR-0002 / Issue #63 的 R1 产物：先冻结现有对外表面，再允许搬代码。
> 它记录的是**路由与签名信号**，不是业务不变量已经验证的证明。

## 规模

- 路由条目：**146**
- 写操作（POST/PATCH/PUT/DELETE）：**73**
- 前端硬编码 `/api/v1` 字面量：**104**

## 按业务域

| 域 | 路由数 |
|---|---|
| candidates | 27 |
| decisions | 15 |
| evidence | 9 |
| interviews | 5 |
| knowledge | 12 |
| offers | 3 |
| operations | 15 |
| projects | 33 |
| providers | 7 |
| static | 3 |
| system | 17 |

## 前端字面量与路由对账

- 已解析到路由模板：104
- 未解析：0

## 路由清单

| 方法 | 路径 | 域 | 归属模块 | 并发信号 | 审计信号 | 人工信号 |
|---|---|---|---|---|---|---|
| GET | `/` | static | `srw.api.app` | — | — | — |
| GET | `/api/v1/ai-runs/{run_id:str}` | providers | `srw.api.operations` | — | — | — |
| POST | `/api/v1/calibration/anchors/{anchor_id:str}/promote` | decisions | `srw.api.governance` | · | · | yes |
| POST | `/api/v1/calibration/reviews/{review_id:str}/resolve` | decisions | `srw.api.governance` | · | · | yes |
| GET | `/api/v1/candidates/compare` | candidates | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/action-plan` | candidates | `srw.api.fullworkbench` | — | — | — |
| PATCH | `/api/v1/candidates/{candidate_id:str}/action-plan` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/ai-runs` | providers | `srw.api.operations` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/archive` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/assessment` | decisions | `srw.api.app` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/brief` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/contact` | candidates | `srw.api.fullworkbench` | — | — | — |
| PATCH | `/api/v1/candidates/{candidate_id:str}/contact` | candidates | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/decision` | decisions | `srw.api.app` | yes | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/decision-history` | candidates | `srw.api.operations` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/decisions/reaffirm` | decisions | `srw.api.operations` | yes | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/events` | interviews | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/events` | interviews | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/evidence/extract` | evidence | `srw.api.app` | · | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/evidence/extract-task` | evidence | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/files` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/identity-history` | candidates | `srw.api.governance` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/offers` | offers | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/offers` | offers | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/phone-script` | candidates | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/pipeline` | candidates | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/candidates/{candidate_id:str}/reevaluations` | decisions | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/reevaluations` | decisions | `srw.api.fullworkbench` | yes | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/restore` | candidates | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/sources/text` | evidence | `srw.api.app` | yes | · | yes |
| POST | `/api/v1/candidates/{candidate_id:str}/stage` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/summary` | candidates | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/candidates/{candidate_id:str}/verifications` | candidates | `srw.api.app` | yes | · | yes |
| GET | `/api/v1/candidates/{candidate_id:str}/workspace` | candidates | `srw.api.app` | — | — | — |
| GET | `/api/v1/claims/{claim_id:str}/grounding` | evidence | `srw.api.app` | — | — | — |
| POST | `/api/v1/claims/{claim_id:str}/review` | evidence | `srw.api.app` | · | · | yes |
| GET | `/api/v1/dashboard` | operations | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/decision-actions/{action_id:str}/knowledge-feedback` | knowledge | `srw.api.capability_recovery` | · | · | yes |
| POST | `/api/v1/decision-actions/{action_id:str}/transition` | decisions | `srw.api.capability_recovery` | · | · | yes |
| PATCH | `/api/v1/events/{event_id:str}` | interviews | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/events/{event_id:str}/scorecards` | interviews | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/events/{event_id:str}/scorecards` | interviews | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/feedback/{feedback_id:str}/review` | operations | `srw.api.capability_recovery` | yes | · | yes |
| POST | `/api/v1/identity-reviews/{review_id:str}/merge` | candidates | `srw.api.governance` | · | · | yes |
| GET | `/api/v1/identity-reviews/{review_id:str}/merge-preview` | candidates | `srw.api.governance` | — | — | — |
| POST | `/api/v1/identity-reviews/{review_id:str}/resolve` | candidates | `srw.api.governance` | · | · | yes |
| GET | `/api/v1/info` | system | `srw.api.app` | — | — | — |
| POST | `/api/v1/knowledge-curation/{proposal_id:str}/export` | knowledge | `srw.api.capability_recovery` | · | · | yes |
| POST | `/api/v1/knowledge-curation/{proposal_id:str}/prepare-apply` | knowledge | `srw.api.capability_recovery06` | · | · | yes |
| POST | `/api/v1/knowledge-curation/{proposal_id:str}/review` | knowledge | `srw.api.capability_recovery` | · | · | yes |
| POST | `/api/v1/knowledge-feedback/{feedback_id:str}/promote` | knowledge | `srw.api.capability_recovery` | · | · | yes |
| GET | `/api/v1/knowledge-packages` | knowledge | `srw.api.capability_recovery06` | — | — | — |
| POST | `/api/v1/knowledge-packages/rollback` | knowledge | `srw.api.capability_recovery06` | · | · | yes |
| POST | `/api/v1/knowledge-packages/{package_id:str}/activate` | knowledge | `srw.api.capability_recovery06` | · | · | yes |
| GET | `/api/v1/knowledge/search` | knowledge | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/knowledge/status` | knowledge | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/offers/{offer_id:str}/status` | offers | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/projects` | projects | `srw.api.app` | — | — | — |
| POST | `/api/v1/projects` | projects | `srw.api.app` | · | · | yes |
| POST | `/api/v1/projects/import-package` | projects | `srw.api.project_portability` | · | · | yes |
| POST | `/api/v1/projects/import-package/preview` | projects | `srw.api.project_portability` | · | · | · |
| GET | `/api/v1/projects/{project_id:str}/ai-runs` | providers | `srw.api.operations` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/archive` | projects | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/audit` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/calibration/anchors` | decisions | `srw.api.governance` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/calibration/anchors` | decisions | `srw.api.governance` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/calibration/reviews` | decisions | `srw.api.governance` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/calibration/reviews` | decisions | `srw.api.governance` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/candidate-search` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/candidates` | candidates | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/candidates` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/candidates.csv` | projects | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/candidates/batch-intake` | candidates | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/candidates/stage` | candidates | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/cockpit` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/contact-list.csv` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/contact-queue` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/decision-actions` | decisions | `srw.api.capability_recovery` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/decision-actions/recommend` | decisions | `srw.api.capability_recovery` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/export-package` | projects | `srw.api.project_portability` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/feedback` | operations | `srw.api.capability_recovery` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/feedback` | operations | `srw.api.capability_recovery` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/handoff` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/identity-reviews` | candidates | `srw.api.governance` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/identity-reviews/scan` | candidates | `srw.api.governance` | · | · | yes |
| PATCH | `/api/v1/projects/{project_id:str}/job-setup` | projects | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/job-setup/suggest` | projects | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/projects/{project_id:str}/knowledge-curation` | knowledge | `srw.api.capability_recovery` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/knowledge/apply` | knowledge | `srw.api.fullworkbench` | yes | · | yes |
| GET | `/api/v1/projects/{project_id:str}/operations-learning` | projects | `srw.api.capability_recovery` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/pipeline` | projects | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/planning` | projects | `srw.api.capability_recovery` | — | — | — |
| PUT | `/api/v1/projects/{project_id:str}/planning` | projects | `srw.api.capability_recovery` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/protocol-drafts` | projects | `srw.api.app` | yes | · | yes |
| GET | `/api/v1/projects/{project_id:str}/protocol-workspace` | projects | `srw.api.app` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/ranked-shortlist` | projects | `srw.api.ranking` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/ranked-shortlist` | projects | `srw.api.ranking` | yes | · | yes |
| GET | `/api/v1/projects/{project_id:str}/ranked-shortlists` | candidates | `srw.api.ranking` | — | — | — |
| GET | `/api/v1/projects/{project_id:str}/recruitment-intelligence` | projects | `srw.api.capability_recovery06` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/restore` | projects | `srw.api.fullworkbench` | yes | · | yes |
| GET | `/api/v1/projects/{project_id:str}/sourcing-observations` | projects | `srw.api.capability_recovery06` | — | — | — |
| POST | `/api/v1/projects/{project_id:str}/sourcing-observations` | projects | `srw.api.capability_recovery06` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/sourcing-observations/import-commit` | projects | `srw.api.capability_recovery07` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/sourcing-observations/import-preview` | projects | `srw.api.capability_recovery07` | · | · | · |
| POST | `/api/v1/projects/{project_id:str}/status` | projects | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/projects/{project_id:str}/templates/from-current` | operations | `srw.api.fullworkbench` | yes | · | yes |
| PATCH | `/api/v1/protocol-revisions/{revision_id:str}` | projects | `srw.api.app` | yes | · | yes |
| POST | `/api/v1/protocol-revisions/{revision_id:str}/publish` | projects | `srw.api.app` | yes | · | yes |
| GET | `/api/v1/ranked-shortlists/{publication_id:str}` | candidates | `srw.api.ranking` | — | — | — |
| POST | `/api/v1/reevaluations/{draft_id:str}/apply` | decisions | `srw.api.fullworkbench` | yes | · | yes |
| GET | `/api/v1/runtime/capabilities` | system | `srw.api.app` | — | — | — |
| GET | `/api/v1/runtime/info` | system | `srw.api.app` | — | — | — |
| GET | `/api/v1/runtime/live` | system | `srw.api.app` | — | — | — |
| GET | `/api/v1/runtime/ready` | system | `srw.api.app` | — | — | — |
| POST | `/api/v1/runtime/shutdown` | system | `srw.api.app` | · | · | · |
| GET | `/api/v1/settings` | system | `srw.api.app` | — | — | — |
| PATCH | `/api/v1/settings/capabilities/{name:str}` | system | `srw.api.app` | · | · | yes |
| PATCH | `/api/v1/settings/provider` | providers | `srw.api.app` | · | · | yes |
| GET | `/api/v1/settings/providers` | providers | `srw.api.fullworkbench` | — | — | — |
| PATCH | `/api/v1/settings/providers/{name:str}` | providers | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/settings/providers/{name:str}/test` | providers | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/sources/{source_id:str}/content` | evidence | `srw.api.app` | — | — | — |
| GET | `/api/v1/sources/{source_id:str}/file` | evidence | `srw.api.app` | — | — | — |
| GET | `/api/v1/sources/{source_id:str}/page/{page_number:int}` | evidence | `srw.api.app` | — | — | — |
| GET | `/api/v1/sources/{source_id:str}/scoring-view` | evidence | `srw.api.app` | — | — | — |
| GET | `/api/v1/system/backups` | system | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/system/backups` | system | `srw.api.fullworkbench` | · | · | · |
| GET | `/api/v1/system/backups/{filename:str}` | system | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/system/backups/{filename:str}/restore` | system | `srw.api.fullworkbench` | yes | · | · |
| GET | `/api/v1/system/diagnostics` | system | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/system/diagnostics/export` | system | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/system/restore/cancel` | system | `srw.api.fullworkbench` | · | · | · |
| GET | `/api/v1/tasks` | operations | `srw.api.fullworkbench` | — | — | — |
| GET | `/api/v1/tasks/{task_id:str}` | operations | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/tasks/{task_id:str}/cancel` | operations | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/tasks/{task_id:str}/retry` | operations | `srw.api.fullworkbench` | · | · | yes |
| GET | `/api/v1/templates` | operations | `srw.api.fullworkbench` | — | — | — |
| POST | `/api/v1/templates` | operations | `srw.api.fullworkbench` | · | · | yes |
| DELETE | `/api/v1/templates/{template_id:str}` | operations | `srw.api.fullworkbench` | · | · | yes |
| PATCH | `/api/v1/templates/{template_id:str}` | operations | `srw.api.fullworkbench` | · | · | yes |
| POST | `/api/v1/templates/{template_id:str}/apply/{project_id:str}` | operations | `srw.api.fullworkbench` | yes | · | yes |
| GET | `/api/v1/workbench` | operations | `srw.api.app` | — | — | — |
| GET | `/health/live` | system | `srw.api.app` | — | — | — |
| GET | `/health/ready` | system | `srw.api.app` | — | — | — |
| GET | `/v1` | static | `srw.api.app` | — | — | — |
| GET | `/v1/{asset_path:path}` | static | `srw.api.app` | — | — | — |

## 边界说明

- 归属模块取自运行中端点对象的 `__module__`，不是文本匹配，因此不会与真实注册表漂移。
- 并发/审计/人工三列是**端点源码静态标记**（`if_match`、`record_audit`、`actor` 等），标记为 `·` 不代表该能力不存在，只代表处理器自身没有出现该标记；也可能由下游 service 实现。
- 路径冻结以 `verification/api_contract/inventory.json` 为准；`test_api_contract.py` 会在路由增删时失败。
