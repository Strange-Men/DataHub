# P3-M5 Manual Revision and Human Review Release Report

## 1. M5 目标与发布结论

P3-M5 为 M3/M4 生成的受治理草稿增加不可原地覆盖的人工修订、提交审核和最终人工 Decision，使 `generated` 草稿能够在不回写 P1/P2、不改变来源快照的前提下进入明确的人工治理流程。

**Release decision: PASS.**

- `manual_revision`、父子版本、`reuse_reviews`、Repository、Service、API 和集中式 RBAC 已完成。
- 生成结果仍不是正式资产；`approved` 不等于 `published`。
- 未实现发布、检索、导出、前端或 P4 能力。
- 未调用真实 Provider，未修改 P1/P2 业务逻辑、表或治理数据。
- 本 Goal 只新增 `reuse_reviews`；未创建 `export_jobs`、`export_artifacts`。

## 2. `manual_revision`

`ReuseGenerationMode` 当前包含：

- `deterministic_template`
- `llm_draft`
- `manual_revision`

人工修订必须创建新 `ReuseAssetVersion`，状态从 `generated` 开始，并保存新的 Canonical Content Payload 和 Content Hash。它不会伪装成模板或 LLM 生成，也不能原地修改父版本。

SQLite/PostgreSQL 兼容迁移为前向、幂等、非破坏式：旧 deterministic/LLM 记录、版本号、Content Hash、Manifest Hash 和 Source Snapshot 保持不变；应用回退时保留新增列、约束和表。

## 3. Parent/Child Version

`reuse_asset_versions.parent_asset_version_id`：

- 可空，自引用 `reuse_asset_versions.id`；
- `ON DELETE RESTRICT`；
- `manual_revision` 必填，原始 deterministic/LLM 版本可空；
- 禁止直接自引用；
- Service 保证父子属于同一 active Project、同一资产类型，并拒绝明显循环。

父版本状态不因子版本创建而改变。`needs_revision` 父版本会永久保留其状态、正文、Hash、Source Snapshot 和 Review；后续修订以新子版本继续。

## 4. `reuse_reviews`

M5 新增且只新增一张表 `reuse_reviews`，字段为：

- `id`
- `asset_version_id`
- `decision`
- `comments`
- `checklist_payload`
- `review_policy_version`
- `reviewed_content_hash`
- `reviewed_source_manifest_hash`
- `reviewer_role`
- `request_id`
- `idempotency_key`
- `created_at`

关键约束：

- `asset_version_id -> reuse_asset_versions.id ON DELETE RESTRICT`；
- 每个 Asset Version 最多一个最终 Review；
- `asset_version_id`、`idempotency_key` 分别唯一；
- Decision 仅允许 `approved`、`needs_revision`、`rejected`；
- reviewed Content/Manifest Hash 和 Policy Version 非空；
- `needs_revision`、`rejected` 必须有非空 comments；
- Review 是不可变审计记录，正常业务不更新、不物理删除。

`pending_review` 由 Asset Version 状态表达，不创建空 Review 行。

## 5. Review Policy v1

冻结 Policy Version：

```text
p3-review-v1
```

人工 checklist 固定包含：

- `structure_complete`
- `source_refs_valid`
- `no_unsupported_claims_confirmed`
- `safe_for_reuse`

`approved` 要求四项全部为 `true`；`needs_revision`、`rejected` 允许存在 `false`，但必须填写 comments。

这些字段记录人工审核结论，不代表系统已从数学上证明所有事实绝对正确、完全没有幻觉或已经适合发布。

## 6. 人工修订不可原地覆盖

API 不提供正文原地 PATCH。Service 只允许从 `generated` 或 `needs_revision` 创建新的 `manual_revision`：

1. 校验 active Project、父状态和资产类型；
2. 重新验证当前 Project 来源；
3. 校验新 Payload Schema、引用和 Grounding；
4. 计算 Canonical Content Hash；
5. 原子分配新 version number；
6. 创建子版本并复制父版本 Source Snapshots。

`pending_review`、`approved`、`rejected`、`failed` 不能被原地修订。

## 7. Source Snapshot 继承

人工修订从父版本复制 `reuse_asset_version_sources`，不重新读取或覆盖 P1/P2：

- 来源身份、版本、Fingerprint；
- Review/Snapshot/Knowledge Asset ID；
- Lineage Manifest Hash；
- Source Trace Snapshot；
- Source Manifest Hash。

子版本创建和全部 Snapshot 复制在一个事务中完成；任何失败均 rollback，不留下半版本或半快照。后续来源 stale 只阻止新动作，不改写历史版本或 Review。

## 8. Grounding 与来源复核

M5 Service 继续复用既有治理组件，不复制第二套规则：

- M2 来源重新验证；
- M3 Canonical Hash、Manifest 和 Source Snapshot；
- M4 Grounding Guard。

人工修订、提交审核和 Decision 前均复核 active Project、当前非 removed 来源、`source_stale=false`、资格和证据一致性。正文 Source Refs 必须来自版本绑定的白名单且满足既有结构性 Grounding 门禁。

结构性 Grounding 不能替代人工事实判断，也不能证明自然语言不存在所有幻觉。

## 9. 提交审核门禁

只允许：

```text
generated -> pending_review
```

提交前必须满足：

- Project 为 active；
- 来源仍 eligible、非 stale 且证据未漂移；
- Content Hash 与 Canonical Payload 一致；
- Source Manifest Hash 与冻结 Snapshot 一致；
- Payload、Source Refs 和 Grounding 继续有效。

重复同一请求幂等；失败保持原 `generated`，不创建 Review，不改变正文或 Hash。

## 10. Decision 行为

| Decision | Asset 状态 | 额外行为 |
|---|---|---|
| `approved` | `approved` | checklist 全 true，设置 `approved_at` |
| `needs_revision` | `needs_revision` | comments 必填，可另建 manual child |
| `rejected` | `rejected` | comments 必填，该版本终止 |

Decision 只允许从 `pending_review` 进入。创建 Review、保存当时的 Content/Manifest Hash 和更新 Asset 状态为单一事务；失败时 Asset 仍为 `pending_review`。

## 11. Review 不可变性

- 每个版本只允许一个最终 Review；
- 第二次 Decision 被稳定拒绝；
- 同一 idempotency key 与同一请求返回原 Review；
- 同一 key 与不同 Decision、comments 或 checklist 返回 Conflict；
- Review 后不能覆盖 checklist、comments、Hash、Role 或 request ID；
- Review 和历史版本不会因来源后续 stale、归档或替换而被改写。

## 12. 幂等、并发与事务

- 人工修订幂等指纹绑定 Project、Parent、Asset Type、Content Hash 和 Manifest Hash。
- 相同 key/相同请求返回同一子版本；不同请求稳定冲突。
- PostgreSQL 并发 version allocation 保证同一 Project/type 的版本号唯一。
- 并发两个 Decision 最多一个成功，数据库唯一约束和原子状态转换共同保护。
- Snapshot 复制、submit 状态转换、Review + Asset Decision 都是原子操作。
- Repository/Service 只转换已知稳定错误，不吞掉未知异常，不泄露连接串、Token、正文或堆栈。

## 13. API

新增：

```text
POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/revisions
POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/submit-review
POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/review
GET  /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/reviews
GET  /api/p3/reuse-projects/{project_id}/reviews
```

Revision 请求只接受 `content_payload`、`idempotency_key`；Review 请求只接受 `decision`、`comments`、`checklist`、`idempotency_key`。Role、request ID、Hash、状态、Policy Version、数据库 ID 和 Source Snapshot 均不能由调用方伪造。

Route 仅做 Schema 校验、Principal/request ID 提取、Service 调用、稳定错误映射和响应序列化；不直接访问 ORM/Repository、P1/P2 或 Provider。

## 14. RBAC

集中新增：

- `p3.asset.edit`
- `p3.asset.submit_review`
- `p3.review.read`
- `p3.review.decide`

| 角色 | edit | submit | review read | decide |
|---|---:|---:|---:|---:|
| admin | 是 | 是 | 是 | 是 |
| cleaner | 是 | 是 | 是 | 否 |
| reviewer | 否 | 否 | 是 | 是 |
| viewer | 否 | 否 | 是 | 否 |
| service | 否 | 否 | 是 | 否 |

Token 模式无 Token/错误 Token 为 401，有效 Token 但缺权限为 403；Auth disabled 保持兼容。

## 15. Docker Smoke

在既有开发 Docker 数据和 volumes 上完成真实 HTTP Smoke：

- `deterministic draft -> manual revision -> pending_review -> approved`：PASS；
- `draft -> needs_revision -> child revision -> pending_review -> approved`：PASS；
- `draft -> rejected -> second review rejected`：PASS；
- Parent/Child、Content Hash、Review Hash、Source Snapshot：PASS；
- stale 来源阻止 submit 和 Decision：PASS；
- token 模式五角色 401/403/200：PASS；
- disabled Auth 兼容：PASS；
- LLM Flag false 时返回安全禁用且零写入：PASS；
- Provider calls：`0`。

Smoke 使用唯一临时 Project，结束后按 Review -> Snapshot -> Child -> Parent -> Source -> Project 精确清理。五张 P3 表计数从 `0|0|0|0|0` 恢复为 `0|0|0|0|0`，未清空开发数据库或删除 volumes。

## 16. PostgreSQL 验收

一次性独立数据库 `datahub_p3_m55_test_20260728` 通过 3 个 integration tests，覆盖：

- `manual_revision`/parent/review 前向迁移、重复执行与旧数据保留；
- parent FK、唯一约束、Source Snapshot 原子复制；
- 并发 version number；
- submit 与 Review Decision 原子转换；
- 每版本一个 Review、幂等和并发 Decision；
- rollback 后状态保持；
- stale 后历史版本/Review 不改写。

结果：**3 passed，58 deselected**。测试数据库已精确 drop；未创建或删除开发 volume。

## 17. 权威测试结果

| 门禁 | 结果 |
|---|---:|
| M5.1 Schema 聚焦 | 69 passed，另有 PostgreSQL 1 passed |
| M5.2 Repository 聚焦 | 54 passed，另有 PostgreSQL 1 passed |
| M5.3 Service 聚焦 | 110 passed，另有 PostgreSQL 1 passed |
| M5.4 API/RBAC 聚焦 | 40 passed，2 warnings |
| M5.4 + Service/Auth/Asset/OpenAPI | 169 passed，1 deselected，2 warnings |
| M1～M5/Auth/OpenAPI 最终矩阵 | **522 passed，11 deselected，2 warnings** |
| M5.5 独立 PostgreSQL | **3 passed，58 deselected** |
| 权威 clean-export backend | **962 passed，16 skipped，44 warnings，108.28s** |

Release Closure 发现 3 个旧阶段测试仍将现已合法的 `reuse_reviews` 视为未来表。仅修订这三个过时测试契约；4 个直接失败项和完整阶段矩阵随后通过。产品代码未因该问题变更。

16 个 skip 均为显式环境依赖 integration gates。44 个 warnings 为既有 FastAPI lifecycle deprecation 和两个预期 mock embedding fallback warning。

## 18. P1/P2 冻结保护

- M5 未修改 P1/P2 repository、service、route、model、表或治理数据。
- M1 Eligibility、M2 Project lifecycle、M3 deterministic semantics 和 M4 Provider/Grounding 语义未复制或改写。
- 人工修订不回写 P1/P2；只继承已经冻结在父版本中的 Source Snapshots。
- Docker Smoke 只创建和精确清理 P3 临时数据。
- CustomerOpsAgent 默认 P1-only、Unified 显式 opt-in、Retrieval/RRF、Embedding 和 No-answer 均未变更。

## 19. LLM 草稿仍需人工审核

`llm_draft` 与 `deterministic_template` 一样只产生 `generated` 草稿。LLM 不能自动提交、自动批准或通过自评绕过 Review Policy；任何正式发布前都必须经过独立的人工修订/审核流程。

本 Release 未启用或调用真实 Provider，默认仍为：

```text
P3_LLM_DRAFT_ENABLED=false
```

## 20. `approved` 不等于 `published`

M5 的终点是人工 `approved`：

- `published_at` 仍为空；
- 不进入检索；
- 不成为 P3 新来源；
- 不能导出；
- 不对 P4 暴露为 published 资产。

发布、current published、supersede 和 archive 必须等待 P3-M6 独立实现与验收。

## 21. 当前身份审计限制

当前认证系统没有稳定个人账户。M5 只记录：

- `reviewer_role`
- `request_id`
- `created_at`

不存储用户 ID、Email、员工姓名、Token 或 Token Hash。因此当前只能实施角色级职责分离，不能可靠证明“提交者与审核者不是同一个自然人”。稳定个人身份和生产级双人复核仍为 Deferred。

## 22. 已知限制

- 未实现 `published`、`superseded`、新业务 archive 流程。
- 未实现 JSONL/CSV 导出、Artifact、撤回或 Manifest 下载。
- 未实现 P3 中文前端任务流。
- 未实现后台自动 stale 扫描。
- 未执行真实 Provider 联调或事实级自动证明。
- Review 是人工治理结论，不是数学事实证明。
- P3 资产仍不能作为 P3 来源，链式复用继续禁止。

## 23. P3-M6 开始条件

P3-M6 必须等待独立人工指令，并至少满足：

1. 本报告、M5 release commit 和 annotated tag 已推送；
2. main/origin 同步，working tree clean；
3. 默认 Auth disabled、P3 LLM Flag false、三个开发服务 healthy；
4. M1～M5 冻结边界、Source Snapshot 和 Review 不可变性保持；
5. 发布只接受 `approved`、非 stale、证据未漂移的版本；
6. `approved` 与 `published`、current published、superseded/archived 必须保持独立事务状态；
7. 不创建 M7 导出捷径，不修改 P1/P2，不进入前端或 P4。

本报告完成后立即停止，P3-M6 尚未开始。
