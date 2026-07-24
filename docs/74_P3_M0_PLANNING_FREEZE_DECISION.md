# P3-M0 Planning Freeze Decision

> 决策：**PASS — P3 数据资产复用规划通过审核并冻结。**
> 基线：`3a969c3d63b195caccd7c987fe108c3e809c7066`。
> 范围：仅规划与状态文档；未开发代码、未修改数据库、未新增 API、未修改前端。
> 下一阶段：P3-M1 仍未开始，必须等待独立人工指令。

## 1. 本次规划审核结论

docs/71～73 已覆盖 P3 产品边界、来源资格、数据模型、状态机、权限、生成/导出、测试门禁和 M1～M9 路线。审核发现的状态歧义、表职责不足和未关闭决策已修订，当前规划可以直接指导 P3-M1 的“来源资格查询与判定”，且不会要求 M1 提前创建 P3 表或进入生成、审核、导出能力。

冻结结论：

- P3 是 P1/P2 下游的受治理再生产层。
- P1/P2 继续冻结，P3 只读合法治理来源。
- P3 v1 使用七张独立表，不修改 P1/P2 既有表。
- 生成、审核、发布和导出是分离门禁。
- P3-M1 只做来源资格，不自动连续进入 M2。

## 2. 本次审核发现与修订

| 发现 | 修订 |
|---|---|
| `draft -> generating -> draft` 无法区分项目草稿和机器生成结果 | 分离 Project、AssetVersion、ExportJob 三套状态机；生成成功固定为 `generated` |
| 最小模型未完全冻结主外键、唯一约束和审计字段 | 冻结七表契约和事务约束 |
| `ready/serving` 容易与治理发布状态混淆 | P2 资格按 approved + active/current/non-archived；serving 不参与 |
| Bad Case `resolved` 可能被误当作已审核知识 | 仅允许 approved 修正 Candidate/不可变修正快照 |
| 来源失效对历史内容和 Artifact 处理不明确 | 历史资产不改写，source_stale 阻断新批准/发布/导出，Artifact 由 admin 逻辑 revoke |
| 角色和个人身份边界未冻结 | v1 复用五角色，只审计 actor_role/request_id/time；个人身份 Deferred |
| Migration 策略未决定 | 沿用 additive `create_all(checkfirst)`；应用回退保留表，无生产 destructive down |
| Artifact TTL/自动撤回未决定 | v1 无自动 TTL、无自动物理删除、无来源失效自动 revoke |
| P3 链式复用仍留未来入口 | v1 明确禁止 P3 资产再次作为 P3 来源 |
| 生成质量数值阈值提前固化 | M1～M8 使用结构性门禁，M9 用独立挑战集校准 release 数值 |

## 3. 最终产品边界

### In Scope

- P1/P2 合法来源的只读查询、资格判定和 Source Trace。
- Project、SourceItem、版本化生成内容、人工审核、发布和归档。
- training material、SOP、service script、QA bank、SFT dataset。
- 确定性模板生成和可选 LLM 草稿生成。
- JSONL/CSV、ExportJob、Artifact、Manifest、checksum 和逻辑 revoke。
- 中文前端与本地 Docker Release Closure。

### Out of Scope

- 模型训练或微调执行。
- 新 OCR/Caption、原生多模态 Embedding。
- 修改 P1/P2 内容、状态、表、索引、检索或审核。
- P3 链式复用和 P3 独立检索索引。
- P4 MCP/Agent 实现。
- 自动审核、自动发布、自动物理删除 Artifact。
- Render P2/P3 持久化上线声明。

## 4. 最终状态机

### 4.1 ReuseProject

```text
draft -> active -> archived
```

- draft：项目信息可编辑，尚未进入正式生成流程。
- active：允许选择合法来源并创建资产版本。
- archived：禁止新增来源、版本和任务；历史记录保留。

### 4.2 ReuseAssetVersion

```text
generating -> generated | failed
generated -> generating | pending_review
pending_review -> needs_revision | approved | rejected
needs_revision -> pending_review
approved -> published
published -> superseded | archived
failed -> generating
```

冻结语义：

- `generated` 只是确定性模板或 LLM 的生成结果，可编辑但不是已审核资产。
- `approved` 不等于 `published`。
- `published` 内容不可直接覆盖；修改必须创建同一 Project/asset kind 的下一 version。
- 新版本发布事务同时把旧 current published 版本置为 `superseded`。
- 同一 Project/asset kind 最多一个 current published 版本。
- `superseded`、`archived` 或 `source_stale` 禁止新发布、新导出和 P4 current 读取。

### 4.3 ExportJob

```text
pending -> running -> succeeded | failed
succeeded -> revoked
```

- failed 重试创建新 Job，不覆盖失败审计。
- revoked 是 admin 执行的逻辑撤回，不物理删除 Artifact。
- ExportJob 不改变 P1/P2 或源 P3 资产状态。

## 5. 最终七张表

| 表 | 职责 | 关键约束 |
|---|---|---|
| `reuse_projects` | 复用任务、asset kind、模板和 Project 状态 | PK `id`；create idempotency key 唯一；逻辑 archived |
| `reuse_source_items` | P1/P2 不可变来源快照、指纹、Trace 和资格 | FK Project；`project_id + canonical_source_key` 唯一 |
| `reuse_asset_versions` | generated、审核、发布和历史版本 | FK Project；`project_id + asset_kind + version` 唯一；单一 current published |
| `reuse_asset_version_sources` | 冻结版本实际引用的来源集合 | 复合 PK/FK；同一来源不得重复绑定 |
| `reuse_reviews` | 只追加人工审核决定和被审内容指纹 | FK AssetVersion；review idempotency；不可修改/删除 |
| `export_jobs` | JSONL/CSV 执行、幂等、结果和 revoke | FK current published AssetVersion；Job idempotency |
| `export_artifacts` | data/manifest 文件元数据和 checksum | FK ExportJob；`job + artifact_kind` 唯一；available/revoked |

共同规则：

- 所有 P3 外键使用 `ON DELETE RESTRICT`，不级联删除历史。
- P3 不对 P1/P2 表建立物理外键，不修改 P1/P2 schema。
- 内容、来源集合、导出配置均保存 SHA-256 指纹。
- v1 审计字段记录 `actor_role`、`request_id`、UTC 时间，不保存 Token 或 Token Hash。
- 发布、旧版本 supersede、current published 唯一检查和来源重检在同一事务完成。
- 资产版本创建与来源绑定在同一事务完成。
- ExportJob 创建事务确认版本仍为 current published、非 archived/superseded/source_stale。

## 6. 来源资格规则

### 6.1 P1

P1 来源必须：

- Candidate 当前状态为 approved。
- 存在 approved ReviewRecord。
- 绑定审核时不可变 `snapshot_json` 或审核内容指纹。
- question、answer、intent、tags、risk level、knowledge type 等规范化业务字段的当前指纹等于审核指纹。
- 来源 Trace 完整。

当前内容指纹漂移、未审核、needs_revision、rejected 或缺少审核快照时禁止复用。该规则由 P3 只读 adapter 实现，不修改 P1。

### 6.2 P2

P2 来源必须：

- 已完成 Review 和 Knowledge Asset 发布。
- Review 为 approved。
- Knowledge Asset 为 active、current、non-archived。
- 绑定 Knowledge Asset ID/version、Snapshot ID/version、Review ID/version、Extraction 和 Asset Trace。
- 内容指纹和完整 Source Trace 有效。

`serving` 不是 P3 来源资格。ready 但未 serving 可以复用，因为 P3 读取治理后已发布资产，而不是线上检索可见性。

archived、被新版本替代、非当前版本、只有 Snapshot 尚未发布或 Source Trace 不完整时禁止复用。

### 6.3 Bad Case

- 原始 Bad Case、agent answer 和 `BadCase.status=resolved` 不能直接成为 P3 来源。
- Bad Case 必须先形成 P1 修正 Candidate 或等价不可变修正快照。
- 只有该修正结果完成 approved Review 后才能进入 P3。
- Source Trace 保留 `source_bad_case_id`、Retrieval 和原 Chunk 引用。

## 7. 来源失效规则

来源在选择后发生归档、版本替换或内容指纹变化时：

1. 不修改已发布历史 P3 资产内容。
2. `ReuseSourceItem.eligibility_status` 置为 `source_stale`。
3. 相关 `ReuseAssetVersion.source_validity_status` 置为 `source_stale`。
4. source_stale 禁止新的审核批准、发布和导出。
5. 已生成 Artifact 和 Manifest 不自动物理删除、不自动 revoke。
6. admin 可以显式逻辑 revoke ExportJob/Artifact，随后阻断系统内下载。
7. 历史 Source Trace、内容 hash、Manifest、checksum 和审计记录保留。
8. 不回写、覆盖、恢复或归档 P1/P2 来源。

## 8. 角色权限

| 角色 | 冻结权限 |
|---|---|
| cleaner | 创建/维护 Project、选择合法来源、生成和编辑 generated/needs_revision、提交审核 |
| reviewer | 查看项目/来源、执行 needs_revision/approved/rejected |
| admin | 全部 P3 权限，包括发布、supersede、archive、导出、revoke |
| viewer | 只读项目、版本、审核、Source Trace、导出状态 |
| service | 仅执行被明确授权的生成/导出后台任务；不能人工审核或直接发布 |

P3 v1 不新增认证角色。稳定个人身份、自然人级禁止自审和独立 publisher/exporter 角色 Deferred。

## 9. 生成与导出策略

### 9.1 生成

- M3 默认使用版本化确定性模板，不依赖 LLM。
- 相同来源集合、模板版本和配置必须得到相同 content hash。
- M4 LLM Provider 可选并复用现有 Provider 抽象；具体 Provider/模型在 M4 入口决定。
- LLM 只能产生 generated 草稿，不能审核或发布。
- LLM 不得改写无法从来源证明的事实；不确定内容必须标为待人工补充。
- 确定性和 LLM 生成均必须保留 source binding 和引用。

### 9.2 输出类型

- `training_material`
- `sop`
- `service_script`
- `qa_bank`
- `sft_dataset`

### 9.3 SFT 导出

JSONL 每条至少包含：

- `instruction`
- `input`
- `output`
- `metadata`
- `source_refs`
- `review`

CSV 使用冻结稳定列：

`schema_version,sample_id,dataset_id,dataset_version,instruction,input,output,system,language,intent,tags,risk_level,source_ref_ids,source_trace_hash,approved_at`

JSONL/CSV 来自同一规范化样本模型。最终精确重复、无效 JSONL、PII、forbidden content 和缺失 Source Trace 均必须为 0。

## 10. Migration 决策

仓库当前没有 Alembic，数据库初始化使用 SQLAlchemy `Base.metadata.create_all(checkfirst)`。

P3 v1 冻结策略：

- M2 起按阶段注册 additive P3 表。
- 只新增、前向兼容，不 ALTER/DROP P1/P2。
- 初始化重复执行安全。
- 应用回退时切回上一 Git tag，保留未被旧应用读取的 P3 表。
- 物理 schema rollback 仅允许在 disposable test DB 中按精确七表逆序执行。
- 生产/保留卷不提供自动 destructive down migration。
- 若未来引入 versioned migration，必须另立 ADR，不能在 P3 小阶段顺带替换全项目机制。

## 11. Artifact 策略

- P3 v1 本地 Docker 使用独立 P3 Artifact 目录/卷和存储 adapter。
- 不配置自动 TTL，不自动过期删除。
- 来源失效不自动删除或 revoke 历史 Artifact。
- admin 可显式执行逻辑 revoke。
- revoke 保留文件元数据、checksum、Manifest、原因、actor_role、request_id 和时间。
- 外部已经下载的副本无法物理召回，Manifest 必须支持版本和撤回核对。
- 外部对象存储、签名下载、企业保留年限和 DLP Deferred。

## 12. 禁止链式复用和独立索引

- P3 v1 只接受合法 P1/P2 来源。
- P3 资产不能再次作为 P3 来源，禁止递归/循环 lineage。
- P3 v1 不建立独立全文或向量检索索引。
- P3 不执行模型训练。
- P4 未来只能通过稳定只读 API 或 MCP 获取 current published P3 资产和 Export Manifest。
- P4 不能读取生成中、generated、pending_review、approved 未发布、superseded、archived 或 source_stale 版本。

## 13. 质量决策

- M1～M8 使用结构性门禁：approved/current/non-archived、指纹一致、Trace 完整、必填完整、引用完整、精确去重、PII/Secret/forbidden content 为 0。
- 不在 M1～M8 凭经验冻结 factual consistency 数值。
- M9 使用独立、run-scoped 挑战集测量并校准 release 数值阈值。
- 不允许根据挑战集逐条修改期望值或放宽来源门禁。

## 14. P1/P2 冻结保护

- 不修改 P1/P2 ORM、表、API、service、repository、状态或数据。
- P3 source adapter 只读 P1/P2。
- 不改变 P1 `rag_chunks/rag_embeddings`。
- 不改变 P2 Review/Snapshot/Knowledge Asset/Index/Serve/Archive。
- CustomerOpsAgent 默认保持 P1-only。
- Unified 继续显式 opt-in。
- Render P2 持久化继续 BLOCKED。
- P3 每阶段必须执行相关 P1/P2 回归；P3-M0.1 本轮按范围不运行测试或 Docker。

## 15. Deferred 生产能力

- 稳定个人身份、OIDC、身份生命周期和自然人级审批分离。
- 独立 publisher/exporter 角色。
- M4 真实 LLM Provider、模型、数据出境和 Prompt 审批。
- 外部 Artifact 对象存储、签名下载、企业保留期限和 DLP。
- PDF/DOCX/PPTX/SCORM 等资料交付格式。
- 近似重复自动处理；v1 只提示人工，精确重复必须清零。
- P3 published-only 独立检索索引；只有未来经测量需求后单独规划。
- P4 MCP 和 Agent 集群。

上述 Deferred 不阻断 P3-M1。

## 16. P3-M1 开始条件

只有全部满足后才能另行开始 P3-M1：

1. docs/71～74 和 README/docs/08/docs/09 状态已 commit。
2. `main` 已推送。
3. annotated tag `p3-m0-planning-freeze` 已推送。
4. working tree clean。
5. P1/P2 冻结边界保持不变。
6. 收到明确、独立的 P3-M1 开发指令。

P3-M1 只允许实现来源资格 DTO、只读 adapter、资格策略和只读查询/evaluate API；不得创建 P3 表、Project、草稿、LLM、审核、发布、导出或前端能力。
