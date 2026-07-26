# P3-M3 Deterministic Draft Asset Generation Release Report

## 1. M3 目标与结论

P3-M3 将 M1/M2 已治理、已审核且可追踪的 P1、P2 与 Bad Case 修正知识，确定性整理为可审核的 P3 草稿资产。本阶段完成 Asset Version/Source Snapshot 持久化、受治理正文读取、五类模板、同步生成 Service、只读/生成 API 与 RBAC。

**Release decision: PASS.** M3 只产生 `generated` 草稿；未进入 LLM、编辑、审核、发布、导出、前端或 P4。

## 2. 数据表

M3 继续使用 M3.1 已建立的两张表：

- `reuse_asset_versions`：保存项目内资产类型、递增版本、生成状态、模板身份、JSON 内容、Content/Manifest Hash、幂等与安全失败信息。
- `reuse_asset_version_sources`：保存每个版本绑定的不可变 Source Item 证据。

P3 当前仍只有四张表：`reuse_projects`、`reuse_source_items`、`reuse_asset_versions`、`reuse_asset_version_sources`。未创建 `reuse_reviews`、`export_jobs`、`export_artifacts`。

## 3. Repository

`backend/app/p3_asset_repositories.py` 提供：

- `create_generating_asset_version`
- `create_asset_version_with_source_snapshots`
- `get_asset_version_by_id`
- `get_asset_version_by_idempotency_key`
- `list_project_asset_versions`
- `mark_asset_generated`
- `mark_asset_failed`
- `add_asset_version_source_snapshot`
- `list_asset_version_sources`

Repository 仅持久化 `generating`、`generated`、`failed`，不判断来源资格、不调用 Provider、不实现审核/发布状态机。列表默认 50、最大 100，按 `version_number DESC, id DESC` 稳定排序。

## 4. 版本号策略

版本号在 `(project_id, asset_type)` 内从 1 递增，客户端不能指定。PostgreSQL 唯一约束是最终裁决；并发竞争使用最多三次的有限重试，仍冲突则返回稳定 Repository Conflict，不存在无限重试或静默覆盖。

## 5. 来源快照

创建 `generating` 版本和来源快照在同一事务中完成。快照冻结：

- Source Item/type/ID/version；
- 内容指纹；
- approved Review、Snapshot、Knowledge Asset ID；
- lineage manifest hash；
- Source Trace snapshot。

同一版本不能重复绑定同一 Source Item。完全相同证据重试幂等；不同证据冲突。Source Item 后续 stale 或 removed 不改写历史快照。

## 6. 受治理内容读取

`p3_source_material_reader.py` 只读转换为 `P3GenerationSourceMaterial`：

- P1/Bad Case 修正只读取 approved Review 的不可变 `snapshot_json` 中的 question/answer；
- 原始 Bad Case 的问题、错误回答不会作为生成正文；
- P2 只读取 active/current Knowledge Asset 对应 approved `AssetReviewSnapshot`；
- Review/Snapshot/Knowledge Asset/version 必须与冻结 Source Item 证据一致；
- 不读取未审核 Candidate、archived/superseded 内容、聊天全文、向量或 Secret；
- 不修改 P1/P2。

无法读取审核正文时生成被阻止，不猜测或补写事实。

## 7. Canonical Manifest

Manifest 使用固定字段、UTF-8、key 排序和 Canonical JSON。来源按：

`source_type, source_id, source_version, source_item_id`

排序，不包含 `created_at`、`request_id` 等不稳定字段。`source_manifest_hash` 为 Canonical JSON 的 SHA-256；输入顺序变化不改变 Hash。

## 8. 五类模板

模板注册表版本为 `v1`，模式固定 `deterministic_template`：

| 资产类型 | 冻结结构 |
| --- | --- |
| `training_material` | title、learning_objectives、sections、key_points、source_refs |
| `sop` | title、purpose、scope、prerequisites、steps、cautions、escalation_rules、source_refs |
| `service_script` | title、scenario、opening、response_steps、prohibited_claims、escalation、source_refs |
| `qa_bank` | title、items(question/answer/source_refs)、source_refs |
| `sft_dataset` | records(instruction/input/output/metadata/source_refs) |

模板只整理审核内容；缺少事实支撑时使用空列表或受控空值，不编造政策、承诺或升级规则。无随机数、当前时间、Prompt、LLM 或外部 Provider。

## 9. Content Hash

生成内容经结构 Schema 校验后，按 UTF-8、key 排序、稳定数组顺序生成 Canonical JSON，并计算 SHA-256 `content_hash`。相同模板版本和相同来源 Manifest 的新版本具有完全相同的 payload 与 Content Hash。

## 10. 生成生命周期

同步生成流程：

1. 查询 Project 与最多 100 条当前来源；
2. 使用 M2 Service 重新验证所有来源；
3. 读取审核正文并计算 Canonical Manifest；
4. 原子创建 `generating` 版本与来源快照；
5. 执行并校验确定性模板；
6. 保存 payload/hash 并转为 `generated`。

仅 active Project 可创建新草稿。draft/archived、无来源、超限、stale、资格失效、证据漂移均在生成前阻止。

## 11. 幂等与失败处理

幂等请求身份包含 Project、资产类型、generation mode、模板 key/version、来源 Manifest 和 actor role。

- 相同 key/请求：返回同一版本；
- 相同 key/不同请求：`P3_ASSET_IDEMPOTENCY_CONFLICT`；
- 已 generated 重试：返回历史版本；
- generating 重试：稳定 in-progress conflict；
- failed 重试：返回稳定生成失败，不创建新版本。

模板或生成异常将 `generating` 原子转为 `failed`。`failure_code` 稳定，`failure_message` 截断并清除连接串、Token、Secret、密码和堆栈。

## 12. API

- `POST /api/p3/reuse-projects/{project_id}/assets/generate`
- `GET /api/p3/reuse-projects/{project_id}/assets`
- `GET /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}`
- `GET /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/sources`

生成请求仅允许 `asset_type`、可选 `template_key`、`idempotency_key`；伪造 version/status/hash/payload/mode/snapshot/failure 字段返回 422。Route 只校验、鉴权、调用 `P3AssetService`、映射错误和序列化，不访问 ORM、Repository 或 P1/P2。

## 13. RBAC

新增集中权限：

- `p3.asset.read`
- `p3.asset.generate`

admin、cleaner、service 具有 read/generate；reviewer、viewer 只有 read。未新增角色。Auth disabled 保持兼容；token 模式无/错误 Token 为 401，viewer/reviewer 生成是 403。

## 14. Docker Smoke

保留开发 PostgreSQL 和 volumes，仅重建 backend。使用现有 eligible P1 与 serving P2 治理来源，临时创建一个 P3 Project：

- P1/P2 来源添加与激活成功；
- 五类资产全部 `generated`；
- 同 key 重试返回同一版本；
- 新 key 的 training material 产生 version 2；
- 相同来源/模板的 Content Hash 一致；
- 每个版本两条来源快照完整；
- 手动标记临时 P3 Source Item stale 后，新生成返回 409 `P3_ASSET_SOURCE_STALE`，版本数仍为 6；
- token 模式：无 Token 401、错误 Token 401、viewer 生成 403、viewer/admin 读取 200；
- disabled 模式生成/读取兼容。

Smoke 后 Auth 恢复 `disabled`。精确删除临时 Project、2 条 Source Item、6 个版本和 12 条快照；P1 Candidate/Review 与 P2 Knowledge Asset/Snapshot 计数保持 `36/10/104/104`。

开发 volume 中用于 Smoke 的 P2 为 serving。ready-not-serving 未通过修改开发 P2 状态伪造；该分支由 M3.3 隔离测试权威覆盖并成功生成。

## 15. PostgreSQL

隔离 PostgreSQL 验收通过 2 个 M3 Repository integration tests：

- 并发 version allocation 得到 1/2；
- 并发相同幂等请求返回同一版本；
- Asset Version 与 Source Snapshot 原子写入；
- generated/failed 状态真实落库；
- 唯一约束失败后 rollback，Session 可继续使用；
- Source Item stale/removed 后历史快照不变。

测试行由 fixture 精确清理；`datahub-test` 容器、网络和 volume 已移除，开发资源未删除。

## 16. 测试结果

| Gate | 结果 |
| --- | --- |
| M3.2 focused | 26 passed（含 PostgreSQL） |
| M3.1/M2/M1 regression at M3.2 | 179 passed、4 skipped |
| M3.3 focused | 23 passed |
| M3.2/M2/M1 regression at M3.3 | 96 passed（含 PostgreSQL） |
| M3.4 Route/API/RBAC | 33 passed |
| M3.3/M3.2/Auth/P3 Route/OpenAPI | 118 passed（含 PostgreSQL） |
| M3.5 isolated PostgreSQL acceptance | 2 passed |
| authoritative ignored clean-export backend | **769 passed、11 skipped、44 warnings，92.08s** |
| compileall / Ruff / Secret scan / diff check | PASS |

11 个 skip 均为显式环境依赖 integration gates。44 个 warnings 为既有 FastAPI startup deprecation 和两个预期 mock Provider fallback warning。本 Goal 只执行了一次全量 backend pytest。

## 17. P1/P2 冻结保护

- 未修改 P1/P2 业务代码、Schema 或治理数据；
- 未调用真实 LLM、Embedding 或外部网络 Provider；
- 未修改 Retrieval/RRF、CustomerOpsAgent P1-only 默认、Unified opt-in 或 No-answer；
- M1.1 仍是来源资格唯一真相，M2 生命周期规则未变；
- P3 生成结果不回写 P1/P2。

## 18. 已知限制

- M3 仅支持同步、确定性 `v1` 模板和最多 100 个当前来源；
- 结构门禁证明确定性与可追踪性，不代表已完成独立业务质量校准；
- actor 仍只有 role/request ID，无稳定个人身份；
- 无后台 stale 扫描；生成入口会重新验证；
- 无 LLM 草稿、编辑、人工审核、发布、导出、独立检索索引或前端任务流；
- `generated` 不等于 approved，更不等于 published。

## 19. P3-M4 开始条件

M4 尚未开始，必须等待单独明确指令。开始前应从本 M3 release tag 的 clean/synchronized main 出发，继续保持：

- M3 确定性模式为默认且不依赖 Provider；
- LLM Provider 复用现有抽象，只能生成草稿；
- 所有事实可由来源证明并保留 Source Trace；
- 不自动审核、发布或回写 P1/P2；
- 独立实现、测试、commit/tag/push 和停止门禁。
