# DataHub P2 AI 多模态知识资产中心规划

> 阶段：P2-M0 Planning
>
> 基线：`p1-m24.3-real-embedding-online-release`
>
> 状态：Planning completed；本文只定义边界和方案，不代表任何 P2 能力已经实现
>
> 强约束：P1 已封板；P2 只能增量扩展，不修改 P1 API、P1 schema、P1 前端或 P1 已验证检索契约

## 1. P2 目标

### 1.1 为什么需要 P2

P1 已把客服文本变成经过清洗、人工审核、可追溯、可被 CustomerOpsAgent 语义检索的知识。但真实客服和商品运营还大量依赖图片、海报、商品主图、活动素材和 SKU 信息。仅保存文件不能回答以下问题：

- 图片里写了什么政策、价格、规格或活动条件？
- 素材描述的是哪个商品或 SKU？
- OCR、Caption 和标签是否可靠，是否经过人工确认？
- 哪些内容允许进入 Agent 知识库，来源能否追溯到原图？
- 素材更新或下架后，Agent 使用的知识如何同步撤回？

因此 P2 的目标不是增加一个上传入口，而是把非结构化素材转成经过治理的知识资产。

### 1.2 P2 要解决的问题

P2 建立以下闭环：

```text
Raw Asset
  -> Extraction（OCR / Caption / Technical Metadata / Tag & SKU Suggestion）
  -> Human Review
  -> Approved Knowledge Snapshot
  -> RAG Knowledge Layer
  -> CustomerOpsAgent
```

闭环必须满足：

- 原始素材可重放：始终保留原文件身份、校验值和来源，不用抽取结果覆盖原始事实。
- 机器结果可解释：每项结果记录 provider、model、版本、置信度、输入哈希和执行状态。
- 人工审核是发布门：未审核、驳回、待修订内容不能进入 Agent 可检索层。
- 知识发布可追溯：检索结果能回到知识快照、审核记录、抽取结果和原始素材。
- 失败可恢复：单步失败不丢素材，重试不重复创建知识或向量。
- P1 可回归：P2 的上传、处理、发布和索引不会改变 P1 已封板行为。

### 1.3 与 P1 的关系

P1 是文本治理和 Agent 知识供给底座；P2 是在同一治理原则上增加多模态资产入口，不重写 P1。

| 维度 | P1 文本知识 | P2 多模态知识 |
|---|---|---|
| 原始输入 | 客服对话、Legacy RAG、Bad Case 等文本 | 图片、商品主图、海报及其结构化附属信息 |
| 机器处理 | 清洗、脱敏、知识抽取 | OCR、Caption、技术元数据、标签与 SKU 建议 |
| 人工门禁 | knowledge candidate review | extraction bundle review |
| 发布单元 | approved candidate / RAG chunk | approved asset knowledge snapshot |
| 检索 | P1 `rag_embeddings` + pgvector | P2 独立知识投影与索引；统一入口查询融合 |
| 不变原则 | approved-only、source trace、Bad Case 回流 | 继承 approved-only 和 source trace；后续再扩展多模态反馈 |

P2 不把 DataHub 变成网盘、数字资产管理系统或商品主数据系统。文件只是原料，审核后的可检索知识才是产品结果。

### 1.4 参考思想及 DataHub 取舍

本规划参考成熟平台的设计原则，但不引入其完整产品或框架：

- [Databricks Medallion Architecture](https://docs.databricks.com/aws/en/lakehouse/medallion)：借鉴 Raw → Validated → Business-ready 的质量分层；在 DataHub 中映射为 Raw Asset → Reviewed Extraction → Published Knowledge，不建设 Lakehouse、Spark 或 Bronze/Silver/Gold 表群。
- [LlamaIndex Ingestion Pipeline](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/)：借鉴可组合 transformation、缓存、文档哈希去重和幂等 upsert；P2 保留自有轻量 pipeline 与 provider adapter，不在 M0 决定引入 LlamaIndex 运行时。
- [Airbyte Protocol](https://docs.airbyte.com/platform/understanding-airbyte/airbyte-protocol)：借鉴 source adapter、标准记录包络、能力检查和 checkpoint 思想；P2-MVP 只有本地上传 source，不建设连接器市场或通用 ELT 平台。
- [Azure RAG Chunk Enrichment](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-enrichment-phase)：借鉴 OCR、Caption、结构化元数据共同形成可检索表示，以及在启用增强项前评估成本；P2-MVP 先采用文本桥接，不直接上高成本原生多模态检索。

适配 DataHub 后的原则是：**质量逐级提升、处理步骤可替换、发布门禁统一、写入相互隔离、查询结果统一。**

## 2. 用户流程设计

### 2.1 主流程

从用户视角只保留五步：

```text
上传素材
  -> 自动处理
  -> 人工审核
  -> 成为知识资产
  -> 被 Agent 使用
```

1. **上传素材**：拖拽或选择图片，可选填写素材名称、来源和 SKU；系统立即显示上传结果。
2. **自动处理**：系统完成存储、去重、OCR、Caption 和元数据抽取；用户只看到一个总体进度和必要的失败提示。
3. **人工审核**：在同一屏幕对照原图和机器结果，修正 OCR、Caption、标签、SKU 后执行通过、驳回或待修订。
4. **成为知识资产**：审核通过后自动生成版本化知识快照并进入索引队列，无需用户再手动“生成候选、构建 chunk、同步向量”三次点击。
5. **被 Agent 使用**：资产详情展示发布状态和最近一次索引结果；统一检索返回文本证据、素材预览和完整来源链。

### 2.2 避免复杂步骤堆叠

- 上传页不要求用户理解 OCR provider、embedding 维度或存储 bucket。
- 处理步骤在后台展开，前端聚合为 `处理中 / 待审核 / 处理失败`。
- 审核页一次提交完整 extraction bundle，不要求分别审核 OCR、Caption 和每个标签。
- 审核通过默认触发知识发布，失败时提供“重试同步”，不让用户重新审核。
- 高级执行信息只在资产详情的折叠区展示。

### 2.3 用户可见状态

处理状态与审核状态必须分离，避免一个 `status` 承担所有含义：

| 维度 | 状态 | 用户含义 |
|---|---|---|
| processing | `uploaded` / `processing` / `ready` / `failed` | 文件是否完成机器处理 |
| review | `not_ready` / `pending_review` / `needs_revision` / `approved` / `rejected` | 内容是否通过人工门禁 |
| publication | `not_published` / `pending_sync` / `published` / `sync_failed` / `withdrawn` | 是否可被 Agent 检索 |

只有 `review=approved` 且 `publication=published` 的快照可进入 Agent 结果。

## 3. 数据模型设计

### 3.1 总体原则

P2-MVP 只规划四个核心聚合，不为 OCR、Caption、Tag、SKU、provider log 分别建孤立表：

```text
Asset 1 --- N AssetExtraction
  |               |
  |               +--- grouped by processing_run_id / input_hash
  |
  +--- N AssetReview
  |
  +--- N AssetKnowledgeLink（同一时刻最多一个 active published version）
```

以下是逻辑模型，不是本轮数据库变更。P2-M1 开始前仍需用 ADR 确认最终字段、索引、迁移和命名；所有未来表采用 P2 命名空间或明确的 `p2_*` 前缀，不能修改 P1 表结构。

### 3.2 Asset：资产聚合根

`Asset` 表示一个原始素材的稳定身份，保存业务和存储元数据，不保存图片二进制。

建议字段组：

| 字段组 | 逻辑字段 | 说明 |
|---|---|---|
| 标识 | `asset_id`, `asset_type`, `media_type` | MVP 的 `media_type` 仅支持 `image`；`asset_type` 可标记 `product_material`、`poster` 等 |
| 来源 | `source_type`, `source_ref`, `source_name`, `uploaded_by` | MVP `source_type=manual_upload`；为未来 connector 预留标准来源包络 |
| 存储 | `storage_provider`, `bucket`, `object_key`, `original_filename` | 数据库只存对象引用；下载/预览 URL 运行时短期签名，不持久化公开 URL |
| 完整性 | `content_hash`, `mime_type`, `byte_size`, `width`, `height` | 哈希用于去重、幂等和后续重处理判断 |
| 业务提示 | `source_tags`, `source_sku_refs`, `business_metadata` | 用户上传时给出的原始提示；使用 JSONB/数组，避免为每个标签建表 |
| 状态 | `processing_status`, `review_status`, `current_version`, `archived_at` | 软删除/归档，不直接物理删除已发布来源 |
| 时间 | `created_at`, `updated_at` | 审计时间 |

关键约束：

- 同一业务空间内 `content_hash` 幂等；重复上传可返回已有资产或创建显式的新版本，不能静默复制。
- 二进制原图进入 S3-compatible 对象存储；不得进入 PostgreSQL、Git 或 `backend/storage/`。
- `source_sku_refs` 只是用户声明，不等于审核通过的 SKU 事实。
- SKU 在 MVP 中是外部字符串引用，不复制商品主数据，也不新增孤立 SKU 主表。

### 3.3 Asset Extraction：统一抽取结果

所有机器理解结果使用同一 `AssetExtraction` 模型，通过 `extraction_type` 区分，不拆成 `ocr_results`、`captions`、`tags` 等表。

建议字段：

- `extraction_id`, `asset_id`, `processing_run_id`
- `extraction_type`: `ocr` / `caption` / `technical_metadata` / `tag_suggestion` / `sku_suggestion`
- `status`: `pending` / `running` / `succeeded` / `failed` / `skipped`
- `result_json`: provider 原始但已安全化的结构化结果
- `normalized_text`: 可供审核和知识投影使用的标准文本
- `confidence`, `language`
- `provider`, `model`, `model_version`, `pipeline_version`
- `input_hash`, `result_hash`, `supersedes_extraction_id`
- `error_code`, `safe_error_message`, `started_at`, `completed_at`

设计规则：

- 同一个 `asset_id + extraction_type + input_hash + pipeline_version` 具备幂等键。
- provider 重跑新增版本，不覆盖历史结果；当前有效版本由资产详情聚合计算。
- 原始 provider 响应只能保存业务必要字段，不能保存 token、签名 URL 或敏感请求头。
- OCR 坐标框等大结构放 `result_json`；审核和 embedding 使用 `normalized_text`，避免向量层理解 provider 私有格式。
- SKU 建议保存在 `sku_suggestion` 结果中，人工确认后的 SKU 进入审核快照和知识快照。

### 3.4 Review：一次审核一个 extraction bundle

`AssetReview` 审核的是某个资产在明确版本下的完整机器结果包，而不是为每种抽取建立独立审核流。

建议字段：

- `review_id`, `asset_id`, `asset_version`
- `extraction_refs`: 本次审核所依据的 extraction IDs 和 result hashes
- `decision`: `approved` / `rejected` / `needs_revision`
- `reviewed_content`: 人工确认后的 OCR、Caption、tags、SKU refs 和必要说明
- `reviewer`, `review_note`, `reviewed_at`
- `snapshot_hash`, `supersedes_review_id`

设计规则：

- 审核记录不可变；再次修改形成新 review version。
- 审核页面必须显示原图、机器值和人工最终值，不能只保存最终文本而丢失差异。
- 默认要求 OCR、Caption、技术元数据步骤完成后才可批准；无文字图片可显式把 OCR 标记为 `skipped/no_text`，不应伪造空成功。
- `approved` 只批准当前快照；原图、抽取版本变化后自动回到 `pending_review`，旧知识版本可保留审计但必须停止作为 active publication。

### 3.5 Knowledge Link：知识候选与发布边界

P2-MVP 不再增加第五张孤立的 candidate 表。审核通过后，由 `Asset + approved Review + referenced Extractions` 生成不可变的 **Approved Knowledge Snapshot**，并通过 `AssetKnowledgeLink` 登记发布关系。它同时承担“P2 知识候选落地”和“知识索引链接”职责。

建议字段：

- `knowledge_link_id`, `asset_id`, `review_id`
- `knowledge_namespace`: 固定为 `p2_asset`
- `knowledge_payload`: `title`, `evidence_text`, `caption`, `ocr_text`, `tags`, `sku_refs`, `modality`
- `source_trace`: asset、review、extraction、source 的稳定 ID 和哈希
- `publication_status`, `publication_version`, `is_active`
- `index_target`, `indexed_document_ids`, `embedding_provider`, `embedding_model`, `embedding_dimension`
- `supersedes_link_id`, `published_at`, `withdrawn_at`, `last_sync_error`

设计规则：

- 只有 approved review 可以创建 `pending_sync` link。
- `knowledge_payload` 是发布时快照；后续抽取或人工修改必须生成新版本，不原地改变 Agent 已使用的证据。
- 每个 asset 同时最多一个 active published link；新版本成功发布后再切换 active，避免索引半更新。
- 撤回知识只影响 Agent 可见性，不删除原始资产、历史审核和来源链。
- 若后续出现“一个资产生成多个独立知识单元”的真实需求，再把 snapshot 升级为独立实体；MVP 不提前拆表。

### 3.6 标签与 SKU 的事实层级

```text
用户输入 source_tags / source_sku_refs
  -> 机器建议 tag_suggestion / sku_suggestion
  -> 人工确认 reviewed_content.tags / sku_refs
  -> 发布事实 knowledge_payload.tags / sku_refs
```

检索过滤只使用发布事实，不能使用未经审核的用户输入或模型建议。

## 4. 与 P1 连接设计

### 4.1 连接原则：写入隔离，查询融合

P1 和 P2 共用 DataHub 的治理理念及 PostgreSQL/pgvector 技术底座，但不共享会互相覆盖的写入流程。

```text
P1 approved text candidates
  -> P1 rag_chunks / rag_embeddings（冻结）
                                      \
                                       -> Unified Retrieval -> CustomerOpsAgent
                                      /
P2 approved asset knowledge snapshots
  -> P2 knowledge projection / P2 index（新增、隔离）
```

- P1 `knowledge_candidates`、`rag_chunks`、`rag_embeddings` 和 `POST /api/customer-ops-agent/retrieve` 保持原契约。
- P2 发布使用自己的 namespace、sync method 和索引目标；P2 rebuild 不删除或重写 P1 向量。
- 新增统一检索入口在查询时调用 P1 retriever 与 P2 retriever，标准化后融合；不让 CustomerOpsAgent 直接访问数据库。
- P1 原检索入口保留为回归和兼容入口，CustomerOpsAgent 是否切换到统一入口必须在 P2-M4 单独验收。

### 4.2 MVP 多模态检索策略：先做文本桥接

P2 第一版不直接把图片向量混入 P1 `Vector(1536)`：

1. 将人工确认后的 OCR、Caption、tags、SKU 和技术元数据投影成 `evidence_text`。
2. 使用与 P1 兼容且已验证的真实文本 embedding 路径生成 P2 文本向量。
3. 在 P2 独立索引中检索，返回原图预览和 source trace。
4. 查询融合使用 rank fusion（优先规划 Reciprocal Rank Fusion），避免直接比较不同索引或未来不同模型的原始相似度。

这已经支持“用文本问题找到相关图片/商品素材”，同时把原生 image embedding、以图搜图、图片直接进多模态模型留到后续版本。

若未来引入视觉 embedding：

- 必须使用独立 vector column/table/index，记录 provider/model/dimension。
- 不允许把不同维度、不同语义空间的向量塞入 P1 `rag_embeddings.embedding`。
- 文本召回与视觉召回在结果层融合，不在存储层假装为同一种分数。

### 4.3 统一检索结果契约

统一结果至少包含：

- `knowledge_id` / `knowledge_namespace`
- `modality`: `text` / `image_text_bridge`，未来可增加 `image`
- `score` 与 `rank_source`，不暴露不可比较的假统一分数
- `evidence_text`
- `candidate_id`（P1 可用时）或 `asset_id + knowledge_link_id`（P2）
- `source_trace`
- `asset_preview`（短期签名 URL 或受控预览端点，P2 才有）
- `tags`, `sku_refs`, `reviewed_at`
- `embedding_provider`, `embedding_model`

CustomerOpsAgent 使用的是经过审核的证据和引用；P2-MVP 不宣称 DataHub 内部已经实现多模态 LLM 回答生成。

### 4.4 回归门禁

每个 P2 开发阶段都必须：

- 从封板 tag 创建基线并保留 P1 全量回归测试通过。
- 验证 P2 未审核、驳回、待修订资产不能出现在任何 Agent 结果中。
- 验证 P2 rebuild/withdraw 不改变 P1 chunk、embedding 数量和检索结果契约。
- 验证 source trace 从统一结果分别回到 P1 candidate 或 P2 asset。
- 不修改 P1 schema；若未来确需改变，必须单独提出 P1 compatibility ADR，不能夹带在 P2 milestone 中。

## 5. Pipeline 设计

### 5.1 流程和责任

| 步骤 | 责任 | 输入 | 输出 / 门禁 |
|---|---|---|---|
| Upload | 接收素材声明、校验类型/大小、建立 asset 身份 | 文件元数据、可选 tags/SKU | `Asset(processing=uploaded)`；拒绝不支持格式 |
| Storage | 把原文件写入对象存储并验证 checksum | 上传对象、asset_id | 稳定 object key、content hash；数据库不存二进制 |
| Technical Metadata | 读取 MIME、尺寸、大小、方向等，不做业务判断 | 原图 | `technical_metadata` extraction |
| OCR | 提取可见文字、语言、可选位置与置信度 | 原图 | `ocr` extraction；失败可单步重试 |
| Caption | 生成面向客服检索的客观描述，禁止编造价格/政策 | 原图 | `caption` extraction |
| Metadata Enrichment | 汇总 tags，生成 SKU 候选并规范化可审核文本 | asset + 已完成 extraction | tag/SKU suggestions 和 review preview |
| Human Review | 人工校正并给出决策 | 原图 + extraction bundle | 不可变 review snapshot；approved 才解锁发布 |
| Knowledge Projection | 生成 Agent 可消费的 evidence_text 与来源链 | approved review | `AssetKnowledgeLink(pending_sync)` |
| Embedding / Index | 生成向量并原子发布新版本 | active pending snapshot | `published` 或 `sync_failed`；不得影响旧 active 版本 |

### 5.2 执行语义

- **异步**：上传完成后处理异步执行，API 不等待 OCR/Caption 全链路结束。
- **可重试**：技术元数据、OCR、Caption、enrichment、embedding 独立重试；人工审核不自动重放。
- **幂等**：每步以 `asset_id + input_hash + pipeline_version + extraction_type` 判断复用或重跑。
- **版本化**：provider/model/prompt/normalizer 改变时提升 pipeline version，保留旧结果。
- **部分失败**：OCR 失败不删除 Caption；必须步骤未完成时进入 `failed` 或 `needs_revision`，不能发布残缺知识。
- **原子发布**：新索引版本完全成功后再切换 active link，避免 Agent 读到半成品。
- **安全错误**：日志和 `safe_error_message` 不包含 API key、对象存储签名或原始私密 URL。

### 5.3 Pipeline 可观测性取舍

MVP 不预先创建 `pipeline_runs + pipeline_steps + pipeline_events` 三层表。先使用：

- `processing_run_id` 串联 AssetExtraction；
- extraction 自身的状态、耗时、provider 和安全错误；
- API `requestId` 与结构化应用日志；
- Asset 聚合状态展示总体进度。

只有出现并发批处理、定时任务、部分重跑 SLA 或跨 worker checkpoint 的真实需求时，才在后续里程碑引入单一 `processing_runs` 聚合；不一次性建设通用编排平台。

### 5.4 Provider 边界

OCR、Caption、Embedding 都通过 DataHub provider adapter 接入，并统一支持：

- readiness check；
- timeout / retry / rate limit；
- provider/model/version 记录；
- mock/deterministic 测试 provider；
- 输出规范化；
- secret 仅从环境变量读取。

P2-M0 不锁定 OCR/Caption 厂商。P2-M1 开始前用少量代表性中文商品素材比较准确率、延迟、成本、数据保留政策和可用区域，再通过 ADR 选型。

## 6. API 规划

以下 API 全部是规划，不在 P2-M0 实现；最终 contract 必须在对应 milestone 先写文档和测试。

### 6.1 P2-M1：Asset 与上传

| 方法与路径 | 责任 |
|---|---|
| `POST /api/p2/assets/upload-intents` | 创建短期直传凭证、校验类型/大小策略 |
| `POST /api/p2/assets` | 完成上传登记并创建 Asset；支持 `Idempotency-Key` |
| `GET /api/p2/assets` | 分页、按 processing/review/publication/media/SKU/tag 筛选 |
| `GET /api/p2/assets/{asset_id}` | 返回聚合详情和受控预览信息 |
| `POST /api/p2/assets/{asset_id}/archive` | 归档素材；已发布资产需先撤回或原子联动撤回 |

若对象存储 provider 在 MVP 不支持安全直传，可临时采用后端代理上传，但对外资源模型保持不变，避免前端绑定具体存储厂商。

### 6.2 P2-M2：Extraction

| 方法与路径 | 责任 |
|---|---|
| `POST /api/p2/assets/{asset_id}/process` | 触发或幂等重试处理；可指定失败步骤 |
| `GET /api/p2/assets/{asset_id}/extractions` | 返回当前有效结果与版本历史摘要 |
| `GET /api/p2/assets/{asset_id}/processing-status` | 提供轻量轮询状态；未来可替换为事件推送 |

### 6.3 P2-M3：Review 与发布

| 方法与路径 | 责任 |
|---|---|
| `GET /api/p2/reviews/pending` | 分页读取待审核队列 |
| `POST /api/p2/assets/{asset_id}/reviews` | 一次提交修订后的完整 bundle 与 decision |
| `GET /api/p2/assets/{asset_id}/reviews` | 返回审核历史和差异摘要 |
| `GET /api/p2/assets/{asset_id}/knowledge-link` | 返回 active/pending 发布状态和 trace |
| `POST /api/p2/assets/{asset_id}/knowledge-link/retry` | 只重试发布/索引，不重复人工审核 |
| `POST /api/p2/assets/{asset_id}/knowledge-link/withdraw` | 撤回 Agent 可见版本，保留审计历史 |

### 6.4 P2-M4：统一 RAG

| 方法与路径 | 责任 |
|---|---|
| `POST /api/knowledge/retrieve` | 新增统一文本 + 多模态知识检索入口 |
| `GET /api/knowledge/retrievals/{retrieval_id}` | 查看融合结果、各路 rank 和 source trace |

规划请求能力：`query`, `top_k`, `modalities`, `sku_refs`, `tags`。默认检索所有已发布知识，过滤字段只作用于审核后的发布事实。

### 6.5 通用 API 规则

- 继续使用 DataHub 统一 response/error envelope 和 `requestId`。
- 列表必须分页；批量上传也必须返回每个素材的独立结果。
- 写接口支持 idempotency；审核使用 `asset_version` 或 ETag 做乐观并发控制。
- API 不返回 bucket secret、永久公开 URL、provider key 或未经审核的内容给 Agent。
- CustomerOpsAgent 继续只通过 DataHub API 访问，不直连 PostgreSQL 或对象存储。
- 生产认证/RBAC 不在 P2-MVP 内，但 API 设计不能把当前 placeholder 当成生产安全能力。

## 7. 前端页面规划

P2 页面沿用 P1 中文暗色 Data Governance / AgentOps 视觉体系，复用现有颜色 token、卡片、按钮、状态 badge、间距和连接状态组件，不另建一套亮色“图库”界面。

### 7.1 素材中心页面

目标：上传、查找、判断处理状态。

- 顶部：`上传素材` 主按钮、总资产/处理中/待审核/已发布/失败统计。
- 主区：列表/缩略图视图切换，展示缩略图、名称、类型、SKU、标签、三维状态和更新时间。
- 筛选：关键字、处理状态、审核状态、发布状态、SKU、标签。
- 上传抽屉：拖拽文件、可选来源/tags/SKU；技术限制在选择文件后就地提示。
- 批量操作仅保留“触发失败项重试”和“归档未发布项”等安全动作，不在 MVP 增加文件夹、分享、移动目录。

### 7.2 审核页面

目标：一屏完成判断，不让审核员在多个步骤间跳转。

- 左侧：待审核队列和状态筛选。
- 中间：可缩放原图；可选叠加 OCR 区域。
- 右侧：Caption、OCR、tags、SKU 的机器值和可编辑最终值；显示置信度/provider 但不喧宾夺主。
- 底部固定操作：`通过并发布`、`待修订`、`驳回`。
- 提交前显示本次知识预览，明确哪些文本会被 Agent 检索。
- 切换资产时保留未提交编辑提示，避免误丢人工修订。

### 7.3 资产详情页面

目标：查看从原图到 Agent 知识的完整来源链。

- 基础信息：受控预览、来源、checksum、尺寸、创建时间、SKU/tags。
- 处理结果：当前 OCR/Caption/metadata 及其 provider/model/version；历史版本折叠显示。
- 审核记录：决策、审核人、时间、差异摘要。
- 知识发布：evidence preview、publication version、索引状态、最近错误、撤回/重试入口。
- Agent 使用：最近检索命中可在后续版本加入；MVP 不建设复杂 BI dashboard。

### 7.4 交互一致性

- 三类状态使用固定颜色语义，不能同色表达“处理失败”和“审核驳回”。
- skeleton、空状态、错误重试沿用 P1 组件模式。
- 默认展示业务含义；provider payload、object key、pipeline version 放入高级折叠区。
- P2-M0 不修改现有 `P2MaterialCenter` 或任何前端文件；以上内容从 P2-M1 后按阶段实现。

## 8. MVP 范围

### 8.1 P2 第一版做什么

- 支持人工上传静态 `JPEG / PNG / WebP` 图片和商品素材。
- 原图进入一个 S3-compatible 对象存储，PostgreSQL 保存 P2 元数据和来源链。
- 基于 content hash 去重和幂等处理。
- 抽取技术元数据、中文/英文 OCR、面向客服使用的 Caption、标签和 SKU 建议。
- 允许用户在上传时提供 SKU，审核员确认最终 SKU；不建设商品主数据。
- 单一审核队列完成修订、通过、驳回、待修订。
- 审核通过生成不可变知识快照；未审核内容绝不发布。
- 将 OCR + Caption + tags + SKU 投影成文本证据，进入 P2 独立 pgvector 索引。
- 新增统一检索入口，融合 P1 文本知识和 P2 素材知识，并返回完整 source trace。
- 建立 P2 小型 eval set，至少覆盖 OCR 文字命中、Caption 语义命中、SKU 过滤、未审核隔离、撤回后不可检索和 P1 回归。
- 保留 mock providers，使本地和 CI 不依赖真实外部 OCR/Caption API。

### 8.2 P2 第一版不做什么

- 不做视频、音频、PDF、3D、动态图或帧级理解。
- 不做图片编辑、裁切、模板设计、版本协作、文件夹、分享链接、水印和完整 DAM 功能。
- 不做 CDN/图片处理平台；预览优化仅满足审核页面。
- 不做以图搜图、原生 image embedding、视觉 reranker 或把图片直接交给多模态 LLM 回答。
- 不做自动发布；任何模型结果必须经过人工门禁。
- 不做商品主数据、库存、价格、上下架或 SKU 生命周期管理。
- 不做通用 Airbyte connector 平台；MVP 只支持手动上传。
- 不引入 Databricks、Spark、通用 Lakehouse 或完整 LlamaIndex 框架。
- 不建设分布式工作流编排、复杂事件总线、pipeline 三表体系。
- 不修改 P1 API、P1 schema、P1 前端流程或 P1 CustomerOpsAgent retrieval contract。
- 不做 P3 数据集导出、P4 MCP/Agent 集群和生产级 RBAC。

### 8.3 建议里程碑

| 里程碑 | 单一目标 | 明确不跨入 |
|---|---|---|
| P2-M1 Material Ingestion | 对象存储、Asset 元数据、上传/列表/详情、校验与去重 | OCR、Caption、审核、RAG |
| P2-M2 Multimodal Understanding | provider adapters、metadata/OCR/Caption/tag/SKU suggestion、可重试处理 | 人工发布、统一检索 |
| P2-M3 Multimodal Review | 审核工作台、不可变 review snapshot、Knowledge Link 发布门禁 | 原生视觉检索、P1 改造 |
| P2-M4 Multimodal RAG | 文本桥接 embedding、P2 独立索引、统一检索与 eval | 视频、以图搜图、P3/P4 |

P2-M1 只建立 Raw Asset 可靠落地，不为了“看起来完整”提前接 OCR、Caption 或 RAG。

### 8.4 MVP 完成门禁

- P1 封板回归全绿，P1 API/schema 未改变。
- 支持格式上传后原图、checksum、元数据在重启/重新部署后仍可用。
- 重复上传/重试不会产生重复 active knowledge 或 embedding。
- 所有 published P2 结果都有 asset → extraction → review → knowledge link → index trace。
- 未审核、驳回、待修订、已撤回资产在统一检索中为零命中。
- P2 单步失败可重试，且不泄露 secret 或永久对象 URL。
- 统一检索同时通过 P1 text regression 和 P2 asset eval。

## 9. 风险分析

| 风险 | 影响 | 主要诱因 | P2 方案 | 阶段门禁 |
|---|---|---|---|---|
| 数据模型膨胀 | 高 | 每种 modality/provider/result 独立建表；过早建设商品、连接器、pipeline 平台 | 四个核心聚合；Extraction 多类型；JSONB 承载 provider 结构；SKU 只作外部引用 | 每新增实体必须证明独立生命周期、查询和约束，不能只为字段分类拆表 |
| 多模态 RAG 复杂度 | 高 | 混合不同 embedding 维度/分数；直接把未审图片交给模型；修改 P1 索引 | MVP 文本桥接；P1/P2 写入隔离；rank fusion；视觉向量以后独立索引 | P2-M4 前必须有 retrieval contract、eval set、approved-only 与 P1 regression 测试 |
| 存储成本 | 高 | 保存重复原图、多尺寸衍生图、OCR 大 payload、无限历史版本 | content hash 去重；原图单份；限制格式/大小；只存必要 preview；生命周期/归档策略 | P2-M1 ADR 必须包含单图成本、月增量、保留/删除和 egress 估算 |
| 模型调用成本 | 中高 | 重复 OCR/Caption、无缓存重跑、所有增强默认开启 | input hash + pipeline version 缓存；单步重试；按业务价值启用增强；记录调用量 | Provider 选型需基于代表性样本的准确率/延迟/单张成本，不只看模型能力 |
| 审核吞吐 | 高 | 每项独立审核、低置信结果过多、页面频繁跳转 | bundle review、一屏对照、预填机器结果、批量队列但逐资产决策 | 记录单资产审核耗时和退回原因；证据不足前不做自动批准 |
| OCR/Caption 幻觉 | 高 | Caption 编造价格/政策；OCR 错字成为 Agent 事实 | 提示词限制为客观描述；置信度；原图对照；人工最终值；发布快照 | 价格、政策、时效等高风险字段必须人工确认，不能只凭 Caption 发布 |
| SKU 错绑 | 高 | 相似商品图、模型猜测、用户输入错误 | 区分 source/suggested/reviewed/published 四层事实；MVP 人工确认 | SKU 过滤只读取 published refs；无法确认时允许空值，不强行猜测 |
| P1 回归破坏 | 高 | 共用 delete-rebuild、直接写 P1 表、改旧 endpoint 响应 | P2 表/namespace/index 独立；新增统一 API；P1 route 保留 | 每阶段运行 P1 全量回归并比对 schema/API；失败则阻止 merge |
| 隐私与访问 | 高 | 永久公开图片 URL、EXIF 泄露、provider 留存数据 | 私有 bucket、短期签名 URL、EXIF 白名单、provider 数据政策评估、安全日志 | P2-M1 前完成访问和删除策略；任何 secret/public URL 泄露阻止发布 |
| Pipeline 可靠性 | 中高 | 外部 API 限流、超时、进程重启、重复消息 | 异步、幂等键、单步状态、指数退避、原子发布；按需求再引入 run/checkpoint | M2 必须覆盖失败重试、重复执行和部分成功测试 |
| Provider 锁定 | 中 | 私有响应格式渗透到审核、知识和前端 | adapter + normalized_text/result_json；业务 contract 不暴露 provider 私有字段 | 更换 mock/real provider 时核心 API 和 review snapshot 格式不变 |

### 9.1 最高优先级决策

P2-M1 前必须先确定：

1. 对象存储 provider、私有访问方式、生命周期和成本上限。
2. Asset 逻辑模型、content hash 幂等规则和 P1 schema 零修改证明。
3. 支持格式、单文件/批量限制和删除/撤回语义。

P2-M2 前再确定 OCR/Caption provider；P2-M4 前再确定 P2 vector 表/索引与统一检索融合算法。按阶段决策能避免在 M1 同时引入存储、模型、审核、RAG 四类高风险变化。

## 结论

P2 应以“受治理的知识发布链”而不是“文件上传功能”立项。DataHub 的最小正确架构是：对象存储承载原始二进制，PostgreSQL 承载四个核心治理聚合，机器抽取统一版本化，人工审核生成不可变知识快照，P2 独立索引保护 P1，统一检索在查询层融合两类知识。

P2-M0 到此完成。下一步只能进入 **P2-M1 Material Ingestion**：先完成对象存储 ADR、Asset foundation、上传/列表/详情、校验、去重和 P1 regression gate；不得提前实现 OCR、Caption、审核或多模态 RAG。
