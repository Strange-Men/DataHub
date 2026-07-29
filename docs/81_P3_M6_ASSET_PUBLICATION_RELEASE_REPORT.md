# P3-M6 Governed Asset Publication Release Report

## 1. M6 目标与发布结论

P3-M6 将 M5 已由人工批准的 `ReuseAssetVersion` 转换为正式、可追踪、可替换和可归档的 P3 复用资产，同时继续隔离 P1/P2、Retrieval、导出和 P4。

**Release decision: PASS.**

- M6.1 发布持久化、审计字段、数据库唯一槽位与 Repository 已固化。
- M6.2 发布、替换、归档和 Current Published 查询 Service 已固化。
- M6.3 API 与集中式 RBAC 已固化。
- M6.4 Docker、PostgreSQL、阶段矩阵和权威 clean-export 验收均通过。
- 未新增表；P3 仍只有五张表，`export_jobs`、`export_artifacts` 尚不存在。
- 未修改 P1/P2 业务逻辑、Schema 或治理数据；未写入 Retrieval；未调用真实 Provider。

## 2. `published` 的产品定义

`published` 表示某个 Asset Version：

1. 已经过 `p3-review-v1` 人工批准；
2. 发布时仍通过 Project、来源、Review、Content Hash、Manifest Hash 和 Grounding 门禁；
3. 已由 `admin` 正式确认为该 Project/Asset Type 当前可复用版本；
4. 保存了角色级发布审计和幂等证据。

`approved` 不会自动变为 `published`，发布必须显式执行。

## 3. `published` 不等于 RAG Serving

发布不会：

- 写入 P1/P2 Retrieval、RRF 或 Embedding；
- 改变 CustomerOpsAgent 默认 P1-only；
- 改变 Unified 显式 opt-in；
- 使 P3 资产成为 P1/P2 或 P3 的新来源；
- 对外公开、进入 MCP、进入 Agent 或触发训练。

P3 v1 仍不建立独立 Retrieval Index。

## 4. 发布审计字段

M6 在现有 `reuse_asset_versions` 上前向新增：

- `published_by_role`
- `publish_request_id`
- `publish_idempotency_key`
- `superseded_by_asset_version_id`
- `archived_by_role`
- `archive_request_id`
- `archive_idempotency_key`

`superseded_by_asset_version_id` 自引用 `reuse_asset_versions.id`，使用 `ON DELETE RESTRICT`。发布/归档幂等键分别唯一。审计不保存个人用户、Token、Token Hash、API Key 或凭证。

## 5. Current Published 唯一约束

SQLite 与 PostgreSQL 均使用数据库层部分唯一索引：

```text
uq_reuse_asset_versions_current_published
ON (project_id, asset_type)
WHERE status = 'published'
```

因此同一 `project_id + asset_type` 最多只有一个当前 `published` 版本。该约束不是仅靠 Service 查询声明；并发或绕过 Service 的重复槽位写入也会被数据库拒绝。

兼容迁移继续采用现有前向、幂等、非破坏式策略：

- 旧 deterministic/LLM/manual 数据、Payload、Hash、Manifest、Snapshot 和 Review 不变；
- 重复执行安全；
- 应用回退时保留新增字段和索引；
- 不设计 destructive down migration。

## 6. Approved 发布门禁

`publish_asset` 只接受：

- active Project；
- 属于该 Project 的目标版本；
- `status=approved`；
- 支持的 Asset Type 和 generation mode；
- `actor_role=admin`；
- 非空发布幂等键和 request ID。

`generated`、`pending_review`、`needs_revision`、`rejected`、`failed` 均不能发布。`superseded` 和 `archived` 不能重新发布。

## 7. Review、Hash 与 Manifest 校验

正式发布前必须存在唯一 Review，并满足：

- `decision=approved`；
- `review_policy_version=p3-review-v1`；
- 四项 checklist 全部确认；
- `reviewed_content_hash == asset.content_hash`；
- `reviewed_source_manifest_hash == asset.source_manifest_hash`；
- 当前 Payload 的 Canonical Content Hash 仍匹配；
- Source Snapshot 计算出的 Manifest 仍匹配；
- Source Reference 和 Grounding 仍有效。

M6 复用 M5 Review Service、M3 Canonical Hash/Manifest 和 M4 Grounding，不复制第二套规则。

## 8. Source Revalidation

发布使用 M2/M5 既有来源重验证：

- 来源必须仍 eligible；
- 保存的版本、指纹、Review/Snapshot/Knowledge Asset 和 lineage 必须未漂移；
- `source_stale=true` 立即阻止新发布；
- removed 或证据变化不会被静默替换。

M6 不回写 P1/P2，也不自动更新既有 Source Snapshot。

## 9. Publish/Supersede 原子事务

同类新版本发布在一个事务内完成：

1. 查询并锁定当前发布槽位；
2. 旧 current `published -> superseded`；
3. 设置旧版本 `superseded_at` 和 `superseded_by_asset_version_id`；
4. 新 `approved -> published`；
5. 保存发布角色、request ID、幂等键和时间；
6. 提交。

SQLite 的 ORM flush 顺序在 M6.1 聚焦测试中暴露过一个确认缺陷：新版本先 flush 会提前触发部分唯一索引。已改为同一事务先 flush 旧版本 supersede，再 flush 新版本 publish；没有增加中间 commit。任一步失败均 rollback，旧版本保持 published、新版本保持 approved。

## 10. Archive 行为

admin 可归档：

- `approved -> archived`
- `published -> archived`
- `superseded -> archived`

归档保存 `archived_at`、`archived_by_role`、request ID 和唯一幂等键。归档是终态，不提供 restore，也不物理删除版本、Snapshot 或 Review。

## 11. 不自动恢复历史版本

归档 current published 后：

- 该 Project/Asset Type 暂无 current published；
- 旧 superseded 版本不会恢复；
- 其他 approved 版本不会自动发布；
- Current Published 列表返回空，按类型查询返回 404。

恢复可用资产必须创建/批准/发布新的版本，不能重发 archived 或 superseded 历史版本。

## 12. Source 失效后的历史保护

来源后续 stale、归档、替换或证据漂移：

- 不改写已经 published/superseded/archived 的历史 Payload、Hash、Manifest、Snapshot、Review 或发布时间；
- Current Published 查询以 `source_stale`、`current_reuse_eligible` 告知当前可复用性；
- 阻止新的发布；
- M7 必须同样阻止新的导出；
- 不自动删除历史版本或未来 Artifact。

## 13. 幂等、并发与回滚

发布和归档均要求：

- 同一幂等键 + 同一目标返回原结果；
- replay 不更新时间、不重复 supersede；
- 同一键 + 不同目标返回稳定 409；
- 数据库错误返回安全的 503，不暴露 SQL 或连接串；
- 同类并发发布由事务和数据库唯一索引保证最多一个 current；
- 原子失败不留下半 supersede、半 publish 或半 archive。

Repository 提供：

- `get_current_published_asset`
- `list_current_published_assets`
- `get_asset_publication_state`
- `get_asset_by_publish_idempotency_key`
- `get_asset_by_archive_idempotency_key`
- `publish_approved_asset`
- `supersede_current_published_asset`
- `archive_asset`

## 14. API

M6.3 新增：

```text
POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/publish
POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/archive
GET  /api/p3/reuse-projects/{project_id}/published-assets
GET  /api/p3/reuse-projects/{project_id}/published-assets/{asset_type}
```

Publish/Archive 请求只允许 `idempotency_key`；角色和 request ID 来自认证/请求上下文。调用方不能提交 status、时间、Review、Hash、Snapshot、发布者或 superseded 关系。

列表默认 `limit=50`、最大 100，支持 `offset` 和 `asset_type`，只返回 current published 摘要，不返回完整正文、Source Trace、向量或 Secret。完整内容继续通过既有 Asset Detail API 读取。

## 15. RBAC

集中新增：

- `p3.asset.publish`
- `p3.asset.archive`
- `p3.asset.read_published`

权限矩阵：

| Role | Publish | Archive | Read Published |
|---|---:|---:|---:|
| admin | yes | yes | yes |
| cleaner | no | no | yes |
| reviewer | no | no | yes |
| viewer | no | no | yes |
| service | no | no | yes |

未新增角色。Token 模式缺少/错误 Token 为 401，权限不足为 403；disabled 模式保持兼容。Health 仍公开。

## 16. Docker Smoke

在保留既有开发 PostgreSQL volume 的前提下重建当前 backend 镜像，使用现有合格 P1 来源和唯一前缀临时 P3 数据完成：

- deterministic 首次发布：200；
- 同类第二版发布：200，旧版 superseded 且 `superseded_by` 指向新版；
- 归档 current：200，Current Published 为空，不恢复旧版；
- archived 重发：409；
- `deterministic_template`、隔离的已有 `llm_draft` 测试数据、`manual_revision` 均可发布；
- stale 来源发布：409；
- Token 缺失/错误：401；
- cleaner/reviewer/viewer/service 发布与归档：403；
- admin 发布与归档：200；
- 五角色读取 Current Published：200；
- disabled 模式恢复后无 Token 读取：200。

Smoke 前后 P1/P2/Retrieval 表计数一致；Source Snapshot、Review、Content Hash 和 Manifest Hash 未改变。临时 P3 数据已按唯一 Project 精确清理，没有重置 volume。

## 17. PostgreSQL 验收

独立数据库 `datahub_test_m64_publication_20260729` 通过 2 个集成测试，覆盖：

- 发布兼容迁移重复执行；
- 审计字段和旧三种 generation mode 保留；
- Current Published 部分唯一索引；
- 并发发布最多一个 current；
- 旧版 supersede/新版 publish 原子提交；
- publish rollback；
- publish/archive 幂等与冲突；
- 归档不恢复历史版本；
- Source stale 后历史发布记录、Review 和 Snapshot 不改写。

结果：**2 passed，55 deselected**。测试数据库及连接已精确清理；开发数据库和 volume 未删除。

## 18. 权威测试结果

| 门禁 | 结果 |
|---|---:|
| M6.1 SQLite Repository | 30 passed |
| M6.1 PostgreSQL | 1 passed |
| M6.2 Service | 25 passed，1 skipped |
| M6.2 PostgreSQL | 1 passed |
| M6.3 API/RBAC | 27 passed |
| M6.2 + Auth/Asset/Review Route 回归 | 25 passed + 97 passed |
| M1～M6/Auth/OpenAPI 阶段矩阵 | **604 passed，13 deselected，2 warnings** |
| M6 独立 PostgreSQL | **2 passed，55 deselected** |
| 权威 clean-export backend | **1044 passed，18 skipped，44 warnings，131.31s** |

18 个 skip 为显式环境依赖 integration gates。44 个 warnings 为既有 FastAPI lifecycle deprecation 和两个预期 mock embedding fallback warning。compileall、Secret scan、conflict marker scan 和 `git diff --check` 通过。

M6.3 组合回归发现旧 Route fixture 未处理 self-referencing Asset Version 的跨模块批量清理。只在 SQLite 测试 teardown 事务中延迟 FK 检查，产品业务删除规则未改变；组合回归随后 97 passed。

## 19. P1/P2 冻结保护

- 未修改 P1/P2 repository、service、route、model、表或治理记录。
- 发布只读取已冻结在 P3 Asset Version/Review 中的证据，并执行现有治理复核。
- Docker Smoke 前后 P1/P2 表计数一致。
- M1 Eligibility、M2 Project lifecycle、M3 deterministic、M4 LLM/Grounding 和 M5 Review Policy 语义未改写。
- CustomerOpsAgent、Unified、No-answer、RRF、Embedding 均未改动。

## 20. Retrieval 零写入

M6 未新增或调用检索写入路径。Docker Smoke 前后：

- `rag_chunks`
- `rag_embeddings`
- `p2_knowledge_chunks`
- `p2_knowledge_index_entries`
- `p2_knowledge_embeddings`
- `retrieval_logs`

计数保持一致。`published` 不会自动 Serving。

## 21. 真实 Provider 零调用

M6 的 Repository、Service、API、Smoke 和 PostgreSQL 验收均不需要真实 Provider。LLM 发布兼容性使用已经隔离成 `llm_draft` 的临时 P3 测试资产验证，没有启用或调用外部模型。

最终默认保持：

```text
P3_LLM_DRAFT_ENABLED=false
```

## 22. 已知限制

- 当前审计只有 actor role、request ID 和时间，没有稳定个人用户身份。
- 当前只有 admin 可发布/归档，尚无独立 publisher/exporter 角色或双人复核。
- P3 v1 没有独立检索索引。
- `published` 不会自动导出、撤回历史 Artifact、进入 MCP/Agent 或训练。
- P3 资产不能再次作为 P3 来源，不支持链式复用。
- Source stale 不改写历史发布资产；当前读取者必须检查 `current_reuse_eligible`。
- Render P2 持久化仍为 BLOCKED，本结论只覆盖本地权威 Docker 环境。

## 23. M7 开始条件

P3-M7 尚未开始。只有独立指令明确授权后，才可：

1. 按冻结规划新增 `export_jobs`、`export_artifacts`；
2. 只接受 current published、non-archived、非 stale 且当前可复用的资产；
3. 实现稳定 JSONL/CSV、Manifest、checksum、幂等、revoke 和人工导出门禁；
4. 保持历史 published 资产、P1/P2、Retrieval 和 Provider 零写入；
5. 独立完成实现、测试、commit、tag、push 和 Release Closure。

在该指令之前，不得把本 M6 发布动作解释为自动导出、MCP 暴露或 Agent 接入。
