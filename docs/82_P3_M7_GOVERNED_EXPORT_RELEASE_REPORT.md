# P3-M7 Governed JSONL and CSV Export Release Report

## 1. M7 目标与结论

P3-M7 将仍具复用资格的 current published P3 Asset Version 确定性导出为 JSONL 或 CSV，并保存完整 Job、Artifact、Manifest、校验和与撤回审计。M7.1～M7.3 已分别实现、测试、提交、推送并创建 annotated tag；M7.4 的 Docker、PostgreSQL 与测试验收通过。

**Release Decision：PASS。**

导出不代表模型训练、RAG、MCP、Agent、公开发布或外部系统交付；M8 中文前端尚未开始。

## 2. `export_jobs`

`export_jobs` 表示一次受治理导出请求，核心字段为：

- 身份与目标：`id`、`project_id`、`asset_version_id`、`export_format`。
- 策略与审计：`export_policy_version`、`requested_by_role`、`request_id`。
- 幂等：`idempotency_key`、`request_fingerprint`。
- 生命周期：`status`、`created_at`、`started_at`、`completed_at`、`failed_at`。
- 撤回：`revoked_at`、`revoked_by_role`、`revoke_request_id`、`revoke_idempotency_key`。
- 安全失败：`failure_code`、`failure_message`。

`project_id` 与 `asset_version_id` 均为 `ON DELETE RESTRICT` 外键；创建与撤回幂等键分别唯一；策略版本和请求指纹非空。表不保存 Token、凭据、完整正文或文件内容。

## 3. `export_artifacts`

`export_artifacts` 保存不可变文件元数据，核心字段为：

- 身份：`id`、`export_job_id`、`asset_version_id`、`export_format`。
- Storage：`storage_backend`、`storage_key`、`safe_file_name`。
- 文件契约：`content_type`、`encoding`、`byte_size`、`row_count`。
- 完整性：`artifact_sha256`、`export_manifest_hash`。
- 审计：`created_at`、`revoked_at`、`revoked_by_role`、`revoke_request_id`。

`export_job_id` 与 `asset_version_id` 均为 `ON DELETE RESTRICT` 外键；每个 Job 最多一个 Artifact，`storage_key` 唯一，字节数和行数不得为负，SHA-256 与 Manifest Hash 必须非空。数据库不保存完整导出文件。

## 4. Export Policy

冻结策略与 Schema 版本均为 `p3-export-v1`。策略身份进入请求指纹和 Canonical Export Manifest，确保重放、冲突识别和可复现性。

## 5. JSONL Contract

- UTF-8、无 BOM。
- 每行一个合法 JSON 对象，固定 `\n`，文件末尾保留一个换行。
- Key 稳定排序，非 ASCII 字符不转义，禁止 NaN/Infinity。
- Content-Type：`application/x-ndjson`。

## 6. CSV Contract

- UTF-8 BOM。
- RFC4180 兼容，固定 `\r\n`。
- 每类资产使用固定列序；列表、对象等复杂字段使用 Canonical JSON 字符串。
- 正确转义逗号、双引号和换行。
- Content-Type：`text/csv; charset=utf-8`。

## 7. 五类 Asset 映射

JSONL 与 CSV 共用同一组经 Payload Schema 验证后的确定性记录：

| Asset Type | 一条导出记录 | 固定字段 |
| --- | --- | --- |
| `training_material` | 一个 section | `title`、`heading`、`content`、`learning_objectives`、`key_points`、`source_refs` |
| `sop` | 一个 step | `title`、`purpose`、`scope`、`prerequisites`、`step_order`、`instruction`、`cautions`、`escalation_rules`、`source_refs` |
| `service_script` | 一个 response step | `title`、`scenario`、`opening`、`step_order`、`response`、`prohibited_claims`、`escalation`、`source_refs` |
| `qa_bank` | 一个 Q&A item | `question`、`answer`、`source_refs` |
| `sft_dataset` | 一个 record | `instruction`、`input`、`output`、`metadata`、`source_refs` |

## 8. Canonical Export Manifest

Manifest 固定包含：

- `export_policy_version`、`schema_version`。
- `project_id`、`asset_version_id`、`asset_type`、`version_number`。
- `generation_mode`、`content_hash`、`source_manifest_hash`。
- `review_id`、`review_policy_version`。
- `export_format`、`encoding`、`row_count`。
- 排序稳定的 `source_snapshot_refs`。

Manifest 使用 Canonical JSON 后计算 SHA-256；调用方不能提交或覆盖 Manifest。

## 9. Artifact SHA-256

`artifact_sha256` 直接由最终文件字节计算。下载前重新检查实际字节数和 SHA-256；不匹配时安全返回 `P3_EXPORT_STORAGE_FAILED`，不会静默重新生成或继续下载。

## 10. 本地 Storage Contract

抽象 `P3ExportArtifactStorage` 提供 `write_atomic`、`open_read`、`exists`、`stat` 和仅供失败清理的 `cleanup_incomplete`。首个实现为 `local_filesystem`，默认根目录 `.local-data/p3-exports`，可通过配置覆盖且已被 Git 忽略。

M7 不上传云端，不提供产品级物理删除 API。

## 11. 原子文件写入

本地实现先在目标目录写入临时文件，再使用原子 `replace` 形成正式文件。失败路径只清理本次未完成文件；成功 Artifact 不由业务流程物理删除。

## 12. Path Traversal 防护

Storage Key 必须为安全相对 POSIX 路径；绝对路径、空段、`.`、`..`、反斜杠逃逸和根目录外解析均被拒绝。根目录、父目录和目标文件的符号链接逃逸受到检查，API 从不接受客户端文件路径，也不返回绝对路径。

## 13. 导出门禁

创建新导出必须同时满足：

1. actor 为 `admin`。
2. Project 为 `active`。
3. Asset Version 为 `published`。
4. 它仍是 Project + Asset Type 的 current published。
5. Review 仍为 `approved` 且 Review Policy、Review Hash 一致。
6. Content Hash、Source Manifest Hash 和 Source Snapshot 完整一致。
7. 当前来源未 stale、未 removed，且重新验证证据一致。
8. Payload Schema 与 Grounding 仍通过。

Service 复用 M2、M3、M4、M5、M6 的既有治理实现，没有复制第二套资格、Review 或 Publication 规则。

## 14. Current Published 要求

`approved` 不等于 `published`。superseded、archived、非 current、审核中、草稿和仅 approved 的版本均不能新导出。

## 15. Review / Hash / Manifest / Grounding

导出前再次验证批准 Review、Content Hash、Manifest Hash 与 Grounding。失败分别映射为稳定的 Export 错误码，既不创建合格 Artifact，也不回写 Asset、Review 或来源证据。

## 16. Source Revalidation

新导出沿用 M2 当前来源重新验证。来源失效、指纹变化、版本变化或 lineage 变化会阻止新导出。P3 不回写或覆盖 P1/P2。

## 17. Job 生命周期

状态机冻结为：

`pending -> running -> succeeded`

失败路径为 `pending|running -> failed`；只有 `succeeded -> revoked`。一个 Job 只产生一种格式的一个正式 Artifact。

## 18. 幂等与并发

创建导出使用全局唯一 `idempotency_key` 和由目标、格式、策略与治理证据构成的 `request_fingerprint`：

- 同 key、同请求返回原 Job/Artifact。
- 同 key、不同请求稳定冲突。
- PostgreSQL 并发同 key 只持久化一个 Job。
- 不同 key 的同一确定性导出产生相同文件字节、Artifact SHA 和 Manifest Hash。

撤回使用独立唯一幂等键；Job 与 Artifact 在同一事务中同步撤回。

## 19. 失败留痕

序列化或 Storage 失败会将 Job 标记为 `failed`，保存受限稳定错误码和安全消息，不保存连接串、Token、完整 Payload 或堆栈。失败不会留下正式 Artifact，数据库事务失败会 rollback。

## 20. Revoke

只有 admin 可撤回成功导出。撤回后：

- Job 与 Artifact 同时记录撤回时间和审计字段。
- 下载返回 HTTP 410 / `P3_EXPORT_ARTIFACT_REVOKED`。
- 文件、Manifest、SHA 和历史审计继续保留。
- 不执行物理删除。

## 21. 历史 Artifact 保留策略

P3 v1 不自动过期、不设置 TTL，默认不物理删除历史 Artifact。企业级对象存储、生命周期和法定保留策略 Deferred。

## 22. 来源失效后的行为

来源后续 stale 不改写既有 Artifact、Manifest 或 SHA，并阻止所有新导出。历史未 revoke Artifact 仍可下载，但 Metadata 明确返回 `source_stale=true`、`current_reuse_eligible=false`；已 revoke Artifact 继续禁止下载。

## 23. API

- `POST /api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/exports`
- `GET /api/p3/reuse-projects/{project_id}/exports`
- `GET /api/p3/exports/{export_job_id}`
- `GET /api/p3/exports/{export_job_id}/artifact`
- `GET /api/p3/export-artifacts/{artifact_id}/download`
- `POST /api/p3/exports/{export_job_id}/revoke`

创建请求只接受 `export_format`、`idempotency_key`；撤回请求只接受 `idempotency_key`。角色与 request id 来自服务端上下文。

## 24. RBAC

集中权限为：

- `p3.export.read`
- `p3.export.create`
- `p3.export.download`
- `p3.export.revoke`

admin 拥有全部权限；cleaner、reviewer、viewer、service 只有 read 与 download。Token 模式保持 401/403 分离，Auth disabled 保持现有兼容行为，没有新增角色。

## 25. Download 安全

下载只按数据库 Artifact ID 查找元数据并通过 Storage Adapter 读取，不接受路径。服务端验证 Job 为 succeeded、Artifact 未 revoke、Storage Backend/Key 合法、文件存在、大小与 SHA 一致，并只用 `safe_file_name` 生成 Content-Disposition。公开响应不暴露 `storage_key`、根目录、绝对路径、Token、完整 Source Trace 或数据库信息。

## 26. Docker Smoke

在既有开发 Docker 数据与 volumes 上完成公开 API Smoke：

- Auth disabled 兼容通过；Token 模式 401/403/200 通过。
- JSONL/CSV 创建、下载、Content-Type、BOM/换行、行数/列头、SHA 与 Manifest 通过。
- 创建幂等重放及不同 key 确定性字节一致通过。
- 五角色读取和下载通过；admin revoke 后下载 410，文件仍保留。
- 来源 stale 阻止新导出；历史未 revoke CSV 仍以相同 SHA 下载并显示 stale。
- Smoke 前后 P1 Candidate/Review、P2 Knowledge Asset 与 Retrieval Log 计数不变。
- 精确临时 P3 数据和临时 Artifact 已清理；开发 volumes 未删除或重置。
- 完成后恢复 `DATAHUB_AUTH_MODE=disabled`、`P3_LLM_DRAFT_ENABLED=false`。

## 27. PostgreSQL 验收

独立 PostgreSQL 验收为 **2 passed，58 deselected**，覆盖：

- 两表约束与前向兼容。
- 并发同幂等键单 Job。
- pending/running/succeeded、failed 与 rollback。
- Job/Artifact 原子落库及 Storage Key 唯一冲突。
- Job/Artifact 原子 revoke。
- 来源 stale 后历史 Artifact SHA/Manifest 不变。

独立测试数据库已删除，未触碰开发 PostgreSQL volume。

## 28. 测试结果

分阶段结果：

- M7.1：SQLite Schema/Storage **23 passed，1 skipped，1 deselected**；M5/M6 Schema 回归 **78 passed，3 deselected**；PostgreSQL **1 passed，24 deselected**。
- M7.2：Service **34 passed，1 deselected**；M2/M5/M6/M7 联合回归 **153 passed，1 skipped，5 deselected**；PostgreSQL 并发 **1 passed，33 deselected**。
- M7.3：API/RBAC **24 passed**；Service/Auth/RBAC/OpenAPI/M6 Route 联合回归 **109 passed，1 deselected**。
- M7.4 单次权威全量命令实际结果：**1118 passed，21 skipped，7 failed，44 warnings，2205.57s**。7 个失败全部是旧阶段仍断言 `export_jobs`/`export_artifacts` 不存在的过期测试预期，不是产品缺陷。
- 只修订上述测试边界后，7 个原失败节点定点复跑为 **7 passed**；遵守本 Goal“全量 backend pytest 只运行一次”的约束，没有伪造或再次运行第二次全量结果。
- 最终 M7 Schema/Storage/Service/API 聚焦矩阵为 **81 passed，1 skipped，2 deselected，2 warnings**；compileall、Secret diff scan、conflict marker scan 和 `git diff --check` 通过。

旧阶段测试现在兼容“仅导入本阶段模型”和“完整应用已注册七表”两种顺序，并在 Export 表存在时继续证明旧阶段零写入。

## 29. P1/P2 冻结保护

M7 未修改 P1/P2 业务逻辑、表、数据或资格规则。Export 外键仅引用 P3 Project/Asset Version；没有向 P1/P2 增加字段或关系。

## 30. Retrieval 零写入

Service、Repository、API 与 Docker Smoke 均不调用或写入 Retrieval。Smoke 前后 Retrieval Log 计数一致。

## 31. Provider 零调用

M7 全程使用已发布 Asset 的确定性 Payload 序列化，不调用真实 LLM、Embedding、OCR、Caption 或任何外部 Provider；`P3_LLM_DRAFT_ENABLED` 最终保持 `false`。

## 32. 已知限制

- 当前只有本地文件 Storage。
- 导出为同步执行；没有外部分布式队列或云对象存储。
- 企业级对象锁、法定保留、自动 TTL、跨区域复制和大文件分片 Deferred。
- 导出不代表训练、RAG、MCP、Agent 或外部系统接入。
- Render P2 Persistent Disk 仍为独立 BLOCKED 项，不由 M7 改变。

## 33. M8 开始条件

M8 只有在本报告、Release commit、main push 和 `p3-m7-governed-export-release` annotated tag 均固化后，才能由新的明确指令开始。M8 只负责全中文前端任务流；本轮没有实现或启动 M8。
