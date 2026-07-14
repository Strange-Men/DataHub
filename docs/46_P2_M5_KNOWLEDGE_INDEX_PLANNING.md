# DataHub P2-M5 Knowledge Index Planning Gate

> 阶段：P2-M5 Knowledge Index Planning Gate
>
> 基线：P1 `p1-m24.3-real-embedding-online-release`；P2-M4 commit `b2856ab`
>
> 状态：Planning completed；本文只做架构决策与后续门禁，不创建表、不写索引、不接 Embedding、不修改检索
>
> 强约束：P1 `rag_chunks`、`rag_embeddings`、`customerops_vector_retrieval` 继续封板

## 1. 评审结论

P2 采用 **物理双索引、逻辑统一检索、分阶段开放 Agent** 的架构：

```text
P1 approved text knowledge
  -> sealed P1 rag_chunks / rag_embeddings
  -> P1 Retriever ----------------------------\
                                                  -> future Unified Retrieval Layer
P2 active Knowledge Assets                         -> normalize + deduplicate + rank fusion
  -> isolated P2 projection / chunks / embeddings /
  -> P2 Retriever -----------------------------/
```

“统一检索层”和“双路检索”不是二选一：

- **存储与写入必须双路隔离**，避免 P2 rebuild、撤回、模型切换破坏 P1。
- **查询入口未来可以逻辑统一**，由一个新增 API 并行调用 P1/P2 Retriever，再对结果标准化和融合。
- **现有 CustomerOpsAgent endpoint 保持 P1-only**，P2 未完成独立评估前不改变其行为。

本阶段不实现图中任何新组件。

## 2. P1 / P2 知识边界

### 2.1 职责边界

| 维度 | P1 | P2 |
|---|---|---|
| 知识定位 | 文本客服知识 | 来源于图片、商品素材及其审核结果的多模态知识资产 |
| 治理发布单元 | approved knowledge candidate | active `knowledge_asset` |
| 当前索引 | P1 `rag_chunks` + `rag_embeddings` | 尚未实现 |
| 当前检索 | `customerops_vector_retrieval` | 尚未实现 |
| 来源追踪 | Candidate -> source batch/messages | Knowledge Asset -> Snapshot -> Review -> Extraction -> Asset |
| 版本撤回 | P1 现有 approved/sync 规则 | Knowledge Asset active/archive + 未来独立 index state |

P2 索引只能读取 **active Knowledge Asset**。它不能绕过 M4 去读取原始 Asset、未审核 Extraction、Review 草稿或 Snapshot 之外的机器结果。索引投影必须以治理层输出为唯一事实源。

### 2.2 统一物理索引方案评审

方案：让 P2 直接写入 P1 `rag_embeddings`，统一使用一个 pgvector 索引。

优点：

- 单路 top-k 查询，初期代码和运维表面上较少。
- 如果所有向量永远使用同一模型、维度和文本语义空间，原始相似度较容易比较。

缺点：

- 直接突破 P1 封板边界，P2 delete-rebuild 可能误删或重建 P1 数据。
- P1 当前同步策略、字段和 source trace 都以 Candidate 为中心，不适配 Asset/Snapshot/Review 链。
- 图片向量、文本桥接向量和未来多模态向量可能使用不同模型与维度，无法安全放进同一固定向量列。
- P2 归档、撤回、版本切换会改变 P1 已验证的检索行为和回归面。
- 一旦 P2 质量或模型出现问题，难以独立回滚。

结论：**不采用**。即使未来两路恰好使用同一个文本 embedding provider，也不能因此共享写表和 rebuild 生命周期。

### 2.3 双路物理检索方案评审

方案：P1/P2 分别维护索引，查询时并行召回，再在统一层融合。

优点：

- P1 封板、回归、回滚和容量边界保持稳定。
- P2 可以独立处理 active/archive、版本、图片向量和不同 embedding profile。
- 两路可以独立限流、降级和评估；P2 失败时 P1 仍可提供已验证结果。
- source trace 可保持各自领域语义，再标准化到统一结果契约。

缺点：

- 查询延迟增加，需要并行、超时预算和部分结果策略。
- 两路原始相似度不可直接比较，需要 rank fusion 和配额控制。
- 必须建立 P1-only、P2-only、融合三类 eval，调试复杂度更高。

结论：**采用**。DataHub 对外提供逻辑统一检索，但底层保持双路、可独立关闭和回滚。

## 3. Knowledge Asset 到可检索状态

### 3.1 三种状态必须分离

不能继续用一个 `status` 同时表达治理、同步和可见性：

1. `knowledge_assets.status`：治理状态，继续使用 `draft / active / archived`。
2. index entry state：索引处理状态，未来独立保存。
3. serving eligibility：查询是否允许返回，必须同时满足治理和索引条件。

推荐可见性规则：

```text
serving_eligible =
  knowledge_asset.status == active
  AND index_entry.state == ready
  AND index_entry.is_serving == true
  AND source fingerprint matches
```

`active` 只表示内容已通过治理并是当前版本，不等于已经生成向量，也不等于 Agent 已可见。

### 3.2 推荐索引状态机

不存在 index entry 表示 `not_indexed`，持久化状态建议保持为：

```text
pending -> indexing -> ready
    |          |
    +----------+-> failed -> pending (explicit retry)

ready -> withdraw_pending -> withdrawn
failed -> withdraw_pending -> withdrawn
```

状态责任：

| 状态 | 含义 | 可检索 |
|---|---|---|
| `pending` | 已接收 active Knowledge Asset，等待投影/索引 | 否 |
| `indexing` | 正在生成或写入本次 index generation | 否 |
| `ready` | chunk、embedding、trace 均验证成功 | 仍需 `is_serving=true` |
| `failed` | 本次同步失败，保留安全错误与重试次数 | 否 |
| `withdraw_pending` | 已立即撤销查询可见性，等待物理清理 | 否 |
| `withdrawn` | 向量/文档已完成逻辑撤回 | 否 |

不把 `retrying` 作为长期状态；重试重新进入 `pending`，并递增 attempt/retry 字段，避免状态枚举膨胀。

### 3.3 active 版本与切换策略

M4 已规定新 Knowledge Asset 版本发布时，旧版本立即归档。索引层必须服从治理层：

- 旧版本一旦 archived，必须立即失去 serving eligibility，即使其向量尚未物理删除。
- 新 active 版本只有索引 `ready` 后才可检索。
- 因此版本切换期间允许出现短暂“新版本尚未可检索”的窗口，但不允许继续回答已归档旧内容。
- 如果未来业务要求零间断切换，必须新增单独 ADR 重新定义治理 active 与 serving alias 的原子关系，不能由索引层私自继续服务 archived 内容。

这里选择 **正确性优先于短时可用性**，适合价格、活动政策和 SKU 等可能过期的高风险素材知识。

### 3.4 source trace

未来每个 index entry 和 chunk 至少固化：

- `knowledge_asset_id`, `knowledge_asset_version`
- `source_snapshot_id`
- `asset_id`
- `content_type`, `content_hash`
- `projection_version`, `chunker_version`
- `index_profile` / `index_generation`

检索结果再通过 M4 的可信链解析：

```text
index chunk
  -> Knowledge Asset
  -> Snapshot
  -> Review
  -> Extraction / Job
  -> Asset
```

索引中的 trace 是防漂移快照，不是新的事实源。详情接口仍应验证它与治理表一致；trace 不完整时不得返回为可信结果。

### 3.5 增量、重建与幂等

推荐 source fingerprint：

```text
hash(
  knowledge_asset_id
  + knowledge_asset_version
  + content_hash
  + projection_version
  + chunker_version
  + embedding_profile
)
```

- fingerprint 相同：重复同步为 no-op。
- 新 Knowledge Asset 版本：新增 entry/chunks，不原地覆盖历史。
- projection/chunker 改版：生成新 index generation，在 shadow generation 验证后再开放 serving。
- embedding model/dimension 改变：创建新 embedding profile/generation，不混写旧向量空间。
- rebuild 只作用于 P2 namespace/profile，永远不执行跨 P1/P2 的 delete-rebuild。

稳定 chunk id 可由 `knowledge_asset_id + projection_version + ordinal + chunk_hash` 生成，使失败重试不会产生重复 chunk。

### 3.6 archive、撤回与删除

处理顺序必须是：

1. Knowledge Asset archive 成功。
2. 查询层同步拒绝该 Knowledge Asset，立即停止服务。
3. index entry 进入 `withdraw_pending`。
4. 异步删除或标记其 P2 embedding/chunks。
5. 成功后进入 `withdrawn`。

物理删除失败不能让内容重新可见。查询必须检查治理状态和 serving flag，而不能只依赖“向量是否还在”。

用户撤回应采用逻辑撤回并保留审计。硬删除仅适用于明确的数据保留/隐私策略，并按 `embedding -> chunk -> index entry -> governance history/object` 的受控顺序执行；MVP 不提供级联硬删除 API。

## 4. 文本桥接与多模态演进

### 4.1 MVP：Reviewed Text Bridge

MVP 检索投影只读取 active Knowledge Asset：

```text
Image Asset
  -> OCR / Caption / reviewed metadata
  -> approved Snapshot
  -> active Knowledge Asset
  -> versioned text projection
  -> P2 text chunks
  -> P2 text embeddings
```

原则：

- 不直接索引原始 OCR/Caption Extraction，避免绕过人工审核。
- 投影模板只使用 `knowledge_asset.content`、`content_type` 和已审核 metadata。
- MVP 默认一个 Knowledge Asset 生成一个 chunk；只有内容超过明确阈值后才做稳定分段。
- 同一 Asset 的 OCR、Caption 等多个 Knowledge Asset 可以分别召回，但结果层应按 `asset_id` 去重/聚合，避免一张图占满 top-k。
- 检索结果必须返回文字证据和 Asset 引用；图片预览只能使用未来的受控短期 URL/预览端点。

该方案解决“用文本问题找到图片中的审核知识”，但不等于原生图片检索。

### 4.2 未来图片 embedding

图片 embedding 用于以图搜图或视觉相似素材召回，必须：

- 使用独立 embedding profile、向量列/表和 pgvector index；
- 记录模型、维度、预处理版本和原图 content hash；
- 只关联已通过治理且允许服务的 Asset/Knowledge Asset；
- 不与 P1 文本向量共享固定 `Vector(1536)` 列；
- 在结果层融合，不比较不同模型的裸 cosine score。

### 4.3 未来多模态 embedding

当模型支持文本与图片进入同一经过验证的共享语义空间时，可以增加 `multimodal_shared` profile：

- 文本 query 和图片在同一模型/profile 内的分数才允许直接排序。
- 不同 profile 之间仍使用 late fusion。
- 必须先证明中文商品素材、OCR 密集海报、视觉相似但政策不同等 eval 场景优于 text bridge。
- 多模态模型不能替代审核；视觉召回仍只能返回 active + ready 的治理知识。

### 4.4 文本 + 图片联合检索

推荐采用 late fusion：

```text
text query
  -> P1 text retriever
  -> P2 text-bridge retriever
  -> optional P2 multimodal retriever
  -> per-route top-k + filters
  -> deduplicate by knowledge/asset
  -> Reciprocal Rank Fusion (RRF)
  -> optional reranker in a later gated stage
```

初期不使用 query classifier 排除某一路，避免分类错误造成漏召回。待有真实日志和 eval 后，才可将 routing 用作成本/延迟优化。

## 5. 数据库设计评审（只评审，不建表）

### 5.1 推荐分层

未来候选实体按控制面、文本数据面、向量数据面分开：

| 候选实体 | 责任 | 最早创建阶段 |
|---|---|---|
| `p2_knowledge_index_entries` | 每个 Knowledge Asset/profile 的同步状态、fingerprint、generation、重试、serving/withdraw | P2-M6 Index Foundation，经独立 schema ADR 后 |
| `p2_knowledge_chunks` | 不可变文本投影、chunk 顺序/hash、source trace、projection/chunker version | P2-M6，与 deterministic projection 测试一起 |
| `p2_knowledge_embeddings` | chunk 的向量、provider/model/dimension/profile 与生成状态 | P2-M7 Text Bridge，在 provider/dimension/迁移/eval 门禁通过后 |

表名是本阶段推荐命名，不是已批准 migration；P2-M6 开始前仍需确认命名、约束、索引和 PostgreSQL/SQLite 行为。

### 5.2 `p2_knowledge_index_entries`

建议字段组：

- identity：`id`, `knowledge_asset_id`, `index_namespace`, `index_profile`
- source：`knowledge_asset_version`, `source_snapshot_id`, `asset_id`, `source_fingerprint`
- pipeline：`projection_version`, `chunker_version`, `index_generation`
- state：`state`, `is_serving`, `attempt_count`, `safe_error_message`
- lifecycle：`started_at`, `ready_at`, `withdrawn_at`, `created_at`, `updated_at`

需要它的原因：索引同步具有独立的失败、重试、generation 和撤回生命周期，不应塞进不可变 Knowledge Asset 内容，也不应靠 chunk 数量猜测状态。

### 5.3 `p2_knowledge_chunks`

建议字段组：

- `id`, `index_entry_id`, `knowledge_asset_id`
- `ordinal`, `chunk_text`, `chunk_hash`
- `content_type`, `modality=text_bridge`
- `source_trace_json`
- `projection_version`, `chunker_version`, `created_at`

需要它的原因：一份较长 OCR 内容未来可能产生多个稳定 chunk；投影文本和向量生命周期不同；embedding 换模型时不应重新丢失或复制治理投影。

### 5.4 `p2_knowledge_embeddings`

建议字段组：

- `id`, `chunk_id`, `embedding_profile`
- `embedding`, `provider`, `model`, `dimension`
- `input_hash`, `generation`, `created_at`

需要它的原因：同一个 chunk 未来可能有 text、image 或 multimodal profile，模型和维度也会升级。向量不应嵌入 chunk 表或 P1 `rag_embeddings`，否则迁移/回滚会耦合内容与模型生命周期。

该表 **不能在 P2-M6 提前创建**；只有 P2-M7 已确定真实 provider、维度、pgvector DDL、回滚和 eval 时才创建。

### 5.5 暂不建议的表

- 不创建通用 `knowledge_indexes` collection 表：MVP 只有一个 P2 namespace 和少量代码配置的 profile，尚无独立租户/collection 生命周期。
- 不创建 `index_jobs + index_steps + index_events` 三表：entry 状态、attempt 和日志足够支撑初期同步。
- 不为 OCR/Caption/SKU/tag 分别建 chunk 或 embedding 表：使用 `content_type` 和 profile 区分。
- 不复制 Snapshot/Review/Extraction/Asset 全字段到索引表：只保存稳定 trace 和防漂移 hash。
- 不创建 P1/P2 统一向量表：融合发生在查询层。

当出现多租户、多 collection、多地区部署、复杂 alias 或独立索引配置管理需求时，再评审 `knowledge_index_profiles` / `knowledge_index_collections`；当前不预建。

## 6. CustomerOpsAgent 融合方案

### 6.1 保持现有契约

以下路径继续保持原行为：

```text
POST /api/customer-ops-agent/retrieve
  -> P1 only
  -> retrieval_mode=customerops_vector_retrieval
```

不能在 P2 开发过程中悄悄把该 endpoint 改为双路召回，即使 response 字段暂时不变，也会改变排序、结果集合、延迟、Bad Case trace 和线上回归基线。

### 6.2 新增统一检索契约（未来）

建议未来新增独立版本化入口，例如：

```text
POST /api/knowledge/retrieve
GET  /api/knowledge/retrievals/{id}
```

统一结果建议包含：

- `namespace`: `p1_text` / `p2_asset`
- `knowledge_id`, `asset_id`（P2 时）
- `modality`: `text` / `image_text_bridge` / future `image`
- `evidence_text`
- `route_rank`, `fusion_rank`, `rank_source`
- `source_trace`
- `asset_preview_ref`（P2 可选、受控）
- `embedding_profile`（诊断字段，不向业务伪装统一分数）

### 6.3 融合策略

MVP 使用并行双路召回和 RRF：

1. P1 Retriever 取独立 top-k。
2. P2 Retriever 只取 active + ready + serving 的结果。
3. 各路按 route rank 转换为 RRF 贡献，不直接归一化裸 cosine score。
4. 按 `knowledge_id` 去重，并按 `asset_id` 限制同一素材占位数。
5. 保留路由来源、原始 rank 和 trace，便于 eval 与 Bad Case。
6. 任一路超时可返回另一条已完成路线，但必须记录 `partial=true` 和失败原因。

在有充分 eval 前，P1/P2 各自保留最低候选配额，避免某一路因规模或分数分布垄断结果。

### 6.4 Agent 开放门禁

开放顺序：

1. P2 index 离线/管理端可验证，但 Agent 不可见。
2. 统一检索 API 在测试客户端和 eval 中运行。
3. shadow 模式记录 P1-only 与 fused 差异，不改变线上回答证据。
4. P2 approved-only、archive、source trace、latency 和 P1 回归全部达标。
5. CustomerOpsAgent 通过显式新 API/版本或受控 feature flag 选择融合检索。
6. 旧 P1 endpoint 永久保留为兼容与快速回滚路径，除非另有版本废弃计划。

## 7. 后续 MVP 路线评审

原示例“P2-M5 index foundation -> M6 text bridge -> M7 multimodal retrieval”过于紧凑：当前 M5 是 Planning Gate，且从文本桥接直接跳到原生多模态检索，缺少独立索引 eval、融合回归和 Agent 暴露门禁。

推荐路线：

| 里程碑 | 单一目标 | 明确禁止跨入 |
|---|---|---|
| **P2-M5（本轮）Planning Gate** | 冻结物理双索引、状态机、候选模型、文本桥接和融合边界 | 任何代码、表、Embedding、检索 |
| **P2-M6 Knowledge Index Foundation** | 经 schema ADR 后实现 index entries + deterministic text projection/chunks + archive/幂等状态；使用测试数据验证 | 向量、真实 Embedding、检索 API、Agent |
| **P2-M7 Text Bridge Semantic Index** | P2-only pgvector/embedding profile、增量同步、withdraw、P2 eval；只索引 active Knowledge Asset | P1 表写入、统一 Agent 检索、图片向量 |
| **P2-M8 Unified Retrieval Gate** | 新增双路检索 API、RRF、去重、partial/trace、P1/P2 eval 和 shadow 对比 | 修改旧 CustomerOpsAgent endpoint、原生图片检索 |
| **P2-M9 Native Multimodal Retrieval（可选）** | 独立 image/multimodal profile、图片/联合检索和成本质量评估 | 视频、自动发布、替代人工审核 |

P2-M7 开始前还必须确认用于 text bridge 的内容来自真实已审核数据。即使 Extraction 仍由 Mock provider 产生，也只能用于测试，不能作为“真实多模态知识可用”的发布结论。

### 7.1 P2-M6 最小验收建议

- 只新增 P2 index control-plane/chunk schema，不新增向量列。
- active Knowledge Asset 能生成确定性、版本化、幂等的文本投影。
- archived Knowledge Asset 立即不可 serving，并形成 withdraw 状态。
- 重复同步不重复创建 entry/chunk。
- 新版本不覆盖旧 chunk，trace 全链完整。
- P1 表数量、内容、API 契约和 Harness 10/10 保持不变。

### 7.2 P2-M7 最小验收建议

- provider/model/dimension 与 pgvector DDL 先通过独立 ADR。
- approved/active-only 与 archive 零命中测试通过。
- 增量同步、失败重试、model generation rebuild 和撤回通过。
- P2 eval 至少覆盖 OCR 文本、Caption 语义、SKU/tag 过滤、同 Asset 去重、版本更新和归档。
- 此阶段仍不让 CustomerOpsAgent 使用 P2。

## 8. 评估与回归门禁

未来 P2 可检索前至少建立：

- **P1 regression set**：保留既有 P1 eval 与 Harness 10/10。
- **P2 text-bridge set**：问题 -> expected Knowledge Asset/Asset，按 OCR、Caption、SKU/tag 分类。
- **governance negative set**：draft、archived、failed、withdraw_pending、withdrawn 必须零命中。
- **version set**：新 active 命中、旧 archived 零命中。
- **fusion set**：P1-only、P2-only、两者都有答案以及同义冲突场景。
- **latency budget**：记录 P1、P2、fusion 总延迟和 partial 比例。

不只计算 recall@k，还要记录：

- source trace completeness；
- stale/withdrawn hit rate（目标为 0）；
- per-namespace recall；
- 同一 Asset top-k 占位数；
- fusion 对 P1 基线的退化率；
- embedding 调用数、失败率与成本。

## 9. 风险与控制

| 风险 | 影响 | 控制 |
|---|---|---|
| P1 索引污染 | P1 回归和线上行为被破坏 | P2 独立表/namespace/rebuild；禁止写 P1 rag 表 |
| archived 内容残留 | Agent 返回已撤回政策/商品信息 | 查询同时检查治理 active 与 serving；先撤可见性再物理清理 |
| 状态双写漂移 | governance active 与 index ready 不一致 | 明确 serving predicate、fingerprint、reconciliation job；状态不靠行数推断 |
| 不同分数空间误排序 | P1/P2 或文本/图片结果不可比 | RRF/late fusion；保留 route rank；禁止直接拼 cosine score |
| 双路延迟 | Agent 响应变慢或超时 | 并行召回、独立 timeout、partial 结果标记、后续基于日志优化 routing |
| 版本/模型膨胀 | chunk 与向量存储成本持续增加 | generation、保留策略、只重建变化 fingerprint；历史向量可清理但治理历史保留 |
| embedding 维度漂移 | 写入失败或不同空间混用 | profile 固化 provider/model/dimension；新 generation/表索引，不原地混写 |
| 未审核数据旁路 | 机器幻觉成为 Agent 事实 | 只读 active Knowledge Asset；禁止直接读 Extraction/Snapshot 进入索引 |
| trace 查询成本 | 列表/检索后多次 join | chunk 固化稳定 trace 摘要；详情时验证完整链；批量加载避免 N+1 |
| 撤回清理失败 | 向量仍占空间 | 逻辑撤回优先且不可服务；异步重试物理清理，不因清理失败恢复可见性 |
| P2 规模压制 P1 | 融合 top-k 被素材重复占满 | namespace 配额、按 Asset 去重、fusion eval |
| 模型/存储成本 | 多 profile、多版本导致成本不可控 | M7 前成本预算；默认 text bridge；原生多模态必须证明增益后才启用 |

## 10. 本阶段不做事项

- 不新增或修改任何数据库模型、表、迁移和索引。
- 不修改 P1 `rag_chunks`、`rag_embeddings` 或同步逻辑。
- 不修改 `POST /api/customer-ops-agent/retrieve` 和 `customerops_vector_retrieval`。
- 不新增 P2 index service、chunker、worker、provider、API 或前端。
- 不调用 SiliconFlow 或其他 Embedding provider。
- 不接入 Agent，不创建 feature flag，不执行 shadow retrieval。
- 不运行数据 backfill、rebuild、delete 或 withdraw。

## 11. 决策记录

| 决策 | 结论 |
|---|---|
| P1/P2 物理索引 | 隔离 |
| 对外查询形态 | 未来新增逻辑统一检索层 |
| 查询执行 | 初期并行双路 |
| 融合 | RRF / late fusion，不比较跨 profile 裸分数 |
| MVP 表示 | Reviewed Text Bridge |
| 索引事实源 | active Knowledge Asset only |
| archive 优先级 | 正确性优先；立即不可 serving，再物理清理 |
| 增量策略 | immutable version + fingerprint + generation |
| Agent 接入 | 新契约、shadow/eval 后显式开放；旧 endpoint 不变 |
| 原生多模态 | P2-M9 可选，独立 profile，经 eval/成本门禁 |

## 12. 结论

DataHub 的合理演进不是把 P2 内容塞入现有 P1 向量表，而是让 P2 建立独立、可撤回、可版本化的索引投影，再由新增统一检索层在查询时融合。这样既能保住 P1 `customerops_vector_retrieval` 的稳定基线，也为文本桥接、图片 embedding 和多模态共享空间保留清晰演进路径。

P2-M5 到此只完成规划。下一阶段若获明确授权，只能进入 **P2-M6 Knowledge Index Foundation**：先做独立 schema ADR、index state 和 deterministic text projection/chunks；不得同时接 Embedding、统一检索或 Agent。
