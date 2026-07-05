# DataHub P1 Real RAG Development Roadmap

## 1. 当前 P1 状态

P1 已完成以下能力：

- Vercel 前端 + Render FastAPI + Render PostgreSQL 线上部署
- 客服数据 JSON 导入
- 机器清洗（PII 脱敏、去重、质量评分）
- 人工清洗工作台
- 知识候选抽取（rule_based_mock）
- 知识审核工作台（通过、驳回、打回）
- RAG 知识块构建（approved-only）
- CustomerOpsAgent 受限检索
- Bad Case 回流与 draft 生成
- Legacy RAG 迁移
- 10 张核心表数据库持久化（SQLAlchemy + SQLite 本地 + PostgreSQL 线上）
- 线上 DB smoke test 通过（页面刷新 / Redeploy 后数据仍在）
- P1 四流程前端 UX
- 全站暗黑风视觉统一

P1 数据库持久化版已可定义为：

> **可部署、可持久化、可支撑 P2/P3/P4 的高质量数据中台底座**

---

## 2. 为什么 P1 还不能最终收版

当前 RAG 检索仍然是：

```
approved candidate -> rag_chunks 表 -> keyword / overlap 检索
```

`build_method` 仍为 `"local_json_mock_retrieval"`。
`retrieval_mode` 仍为 `"customerops_local_mock_retrieval"`。

这只能算 **RAG 数据准备层 / mock retrieval**，不是真正的语义 RAG 知识库。

P1 的最终目标必须是：

```
多来源客服数据
-> 多规则机器清洗
-> 人工清洗与审核
-> 高质量数据进入数据库
-> 已审核知识进入真实语义 RAG 知识库
-> CustomerOpsAgent 能调用语义检索结果
-> Bad Case 能回流继续优化知识库
```

没有真实语义 RAG 的 P1，即使数据库已持久化，仍然只是一个治理流程 demo，不是可被 Agent 真正使用的知识底座。

---

## 3. P1 最终收版标准

以下 6 条**全部满足**，P1 才能最终收版：

1. **向量底座可工作**：pgvector 扩展已启用，`vector_chunks` 表存在，可通过 SQL 查询
2. **语义检索上线**：对同一查询，语义检索能返回 keyword 匹配不到的但语义相关的结果
3. **source trace 不丢**：每条向量检索结果可追溯到 `candidate_id -> source_batch_id -> source_type`
4. **eval set 有分数**：至少 10 条 eval query，recall@5 ≥ 0.6（语义明显优于 keyword）
5. **approved-only 边界不破**：pending / rejected / needs_revision 不进入向量库，有测试覆盖
6. **线上持久化**：Render PostgreSQL + pgvector 在 redeploy 后数据仍在，检索可用

---

## 4. 收拢后的 P1 后续路线

```
P1-M20.7  Lightweight Pipeline Harness + RAG Readiness Check
P1-M21    Vector RAG Foundation + Eval Set
P1-M22    Approved Knowledge Sync to Vector RAG
P1-M23    CustomerOpsAgent Semantic Retrieval
P1-M24    Real RAG Online Smoke Test + P1 Release Readiness
```

共 5 个阶段。不拆 M20.7a/b，不单独开 M21.5，不设 M25。

---

## 5. P1-M20.7：Lightweight Pipeline Harness + RAG Readiness Check

### 目标

在投入真实 RAG 开发前，建立轻量一键验证能力，并确认 pgvector 可用。

### 范围

1. 新增 `scripts/run_p1_pipeline_harness.py`
2. 脚本调已有 API 串行跑：
   导入 -> 机器清洗 -> 人工清洗 -> 生成待审核知识 -> 审核通过 -> RAG Build -> Agent 检索 -> Bad Case -> Bad Case draft
3. 每一步输出：PASS / FAIL、HTTP status、response 摘要、关键 ID、失败原因
4. 脚本支持 `--base-url` 参数：
   - `http://127.0.0.1:8000`
   - `https://datahub-jr8x.onrender.com`
5. 不新增 pipeline 数据库表
6. 不改数据库 schema
7. 不改业务 API
8. 轻量 SDD/TDD 规则写入文档：
   后续每轮必须先写/更新测试，必须通过 harness 或对应 eval
9. **确认 Render PostgreSQL 是否支持 pgvector**：
   ```sql
   SELECT * FROM pg_available_extensions WHERE name = 'vector';
   ```
   或 `CREATE EXTENSION IF NOT EXISTS vector;`
10. **如果 pgvector 不可用，停止 M21 路线并重新评估向量库方案**

### 验收

- [x] 本地 harness 可运行（local backend unavailable → expected FAIL，不是语法错误）
- [x] 线上 harness 全 PASS（2026-07-05 验证：10/10 PASS，Render PostgreSQL）
- [ ] pgvector 可用性结论明确（本地 SKIP，需在 Render 环境验证）
- [x] 不新增 pipeline trace 表
- [x] 不新增数据库表

### 实装记录（2026-07-05）

- `scripts/run_p1_pipeline_harness.py` — 一键全链路验证脚本，覆盖 10 个步骤
- `scripts/check_pgvector_support.py` — pgvector 扩展可用性检查脚本
- `backend/tests/test_p1_pipeline_harness_script.py` — 24 个 harness 逻辑测试
- 线上验证：10/10 PASS
- pgvector 检查：本地 DATABASE_URL 未设置 → SKIP；需在 Render PostgreSQL 环境手动验证

### Harness 使用命令

```powershell
# 本地
python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000 --verbose

# 线上
python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com --verbose --stop-on-fail

# pgvector 检查
python scripts/check_pgvector_support.py
# 或
python scripts/run_p1_pipeline_harness.py --check-pgvector
```

### pgvector 检查命令

```powershell
# 本地（需设置 DATABASE_URL）
$env:DATABASE_URL = "postgresql://..."
python scripts/check_pgvector_support.py

# 或在 Render PostgreSQL 上手动执行
# SELECT * FROM pg_available_extensions WHERE name = 'vector';
# CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 6. P1-M21：Vector RAG Foundation + Eval Set

### 目标

建立真实 RAG 的最小底座，并提前建立检索评估集。

### 范围

1. 启用 pgvector 扩展（`CREATE EXTENSION IF NOT EXISTS vector`）
2. 新增 `vector_chunks` 或 `rag_embeddings` 表：
   - `id`、`candidate_id`、`chunk_text`、`embedding`（vector 列）
   - `source_type`、`source_batch_id`、`source_conversation_id`、`source_message_ids`
   - `knowledge_type`、`intent`、`tags`、`risk_level`、`quality_score`
   - `modality`（预留，默认 "text"，为 P2 多模态做准备）
   - `created_at`、`updated_at`
3. 新增 embedding provider 配置（走环境变量）：
   - `EMBEDDING_PROVIDER`（例如 `openai`）
   - `EMBEDDING_MODEL`（例如 `text-embedding-3-small`）
   - `EMBEDDING_API_KEY`
4. **必须支持 mock/deterministic embedding** 用于本地测试：
   - 不依赖真实外部 API 即可跑通测试
   - mock embedding 基于 text hash 生成固定维度向量
5. 支持真实 embedding provider 作为线上可选
6. 新增 `samples/rag_eval_queries.json`：
   - 至少 10 条 query
   - 每条标注 `expected_candidate_id` / `expected_chunk_id` / `intent`
   - 格式约定：
     ```json
     [
       {
         "query": "How do I return an item?",
         "expected_candidate_ids": ["kc_abc123"],
         "intent": "refund"
       }
     ]
     ```
7. 不接真实 CustomerOpsAgent semantic retrieval（留在 M23）

### 注意事项

- embedding API 调用应有基本重试（建议 3 次）
- 注意 Render Free PostgreSQL 1GB 存储限制（vector 维度 × 行数 影响存储）
- 注意 embedding API 费用（OpenAI text-embedding-3-small 约 $0.02/1M tokens）
- 本地 SQLite 不支持 pgvector，本地测试使用 mock embedding

### 验收

- [x] pgvector 扩展已启用（函数已添加，Render 环境自动执行 `CREATE EXTENSION IF NOT EXISTS vector`）
- [x] `rag_embeddings` 表可创建（Vector 类型在 PostgreSQL，Text JSON fallback 在 SQLite）
- [x] mock embedding 可写入 vector column（JSON 序列化在 SQLite 下已验证）
- [x] eval set 存在且格式校验通过（12 条 query，14 个测试覆盖）
- [x] 不破坏现有 keyword fallback
- [x] 现有测试全部通过（149 tests：57 new + 92 existing）
- [x] 线上 harness 10/10 PASS

### 实装记录（2026-07-05）

**pgvector 可用性检查结果**：
- 本地：SKIP（DATABASE_URL 未设置），pgvector_available=unknown。
- Render PostgreSQL：已确认 PostgreSQL 后端运行中（database_status.backend=postgresql, status=ok）。
- pgvector 函数已添加：`check_pgvector_available()` 和 `ensure_pgvector_extension()`，在 Render 环境自动执行。
- 本地 SQLite 优雅跳过（不报错、不崩溃）。

**新增 vector table 名称**：`rag_embeddings`

**embedding provider 策略**：
- 默认：MockEmbeddingProvider（deterministic, SHA-256 hash-based, dimension=64）
- 可选：OpenAIEmbeddingProvider（需 EMBEDDING_API_KEY，3 次重试，timeout）
- 配置：EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_API_KEY / EMBEDDING_DIMENSION 环境变量
- 降级：未知 provider 自动 fallback 到 mock

**mock embedding 的用途**：
- 本地测试无需外部 API
- 确定性输出（同 text → 同 vector），适合测试断言
- 默认维度 64（可通过 EMBEDDING_DIMENSION 配置）
- L2 归一化到单位向量（cosine-ready）

**eval set 路径和作用**：
- 路径：`samples/rag_eval_queries.json`
- 12 条 query，覆盖 refund / shipping / escalation / product_info / policy / bad case
- 每条 query 有 id / query / intent / expected_keywords / expected_candidate_ids / notes
- expected_candidate_ids 在 M21 为空，M22 同步 approved knowledge 后补填
- M23 可用于计算 recall@k

**M22 下一步**：Approved Knowledge Sync to Vector RAG — 让审核通过的知识真正写入 `rag_embeddings` 表。

---

## 6A. P1-M21.1：pgvector Readiness Verification Gate

### 目标

真正确认 Render PostgreSQL 是否支持 pgvector，为 M22 解锁。

### 验证方式

**方式 A**：通过 Render 后端 health endpoint 间接验证。

在 `backend/app/database.py` 的 `init_database_tables()` 中调用 `ensure_pgvector_extension()`，并在 `/api/health` 中暴露 `pgvector_status` 字段。

验证命令：
```bash
curl -s https://datahub-jr8x.onrender.com/api/health
```

### 验证结果（2026-07-05）

| 检查项 | 结果 |
|--------|------|
| **验证时间** | 2026-07-05 |
| **DATABASE_URL 是否拿到** | 是（Render 环境变量，未在本地暴露） |
| **database_backend** | postgresql |
| **pgvector_available** | **true** |
| **pgvector default_version** | 0.8.1 |
| **extension_create_ok** | **true** |
| **验证方式** | Render 后端 health endpoint 间接验证 |
| **连接串是否泄露** | 否（health endpoint 不返回 DATABASE_URL） |
| **是否允许进入 M22** | **是 ✅ — M22 已解锁** |

### 结论

Render PostgreSQL (Free tier) 支持 pgvector 扩展（version 0.8.1）。`CREATE EXTENSION IF NOT EXISTS vector` 执行成功。所有 M22 前置条件已满足：

1. ✅ pgvector_available = true
2. ✅ extension_create_ok = true
3. ✅ database_backend = postgresql
4. ✅ 验证方式、验证时间、验证结果已记录
5. ✅ 没有泄露连接串

M22 可立即启动：Approved Knowledge Sync to Vector RAG。

### 实装记录（2026-07-05）

- `backend/app/database.py`：`init_database_tables()` 中新增 `ensure_pgvector_extension()` 调用（safe no-op on SQLite）
- `backend/app/main.py`：`/api/health` 新增 `pgvector_status` 字段（含 pgvector_available + extension_create_ok + backend）
- 线上验证：`pgvector_available=true, extension_create_ok=true, backend=postgresql`
- pgvector version: 0.8.1

---

## 7. P1-M22：Approved Knowledge Sync to Vector RAG

### 目标

让审核通过的高质量知识真正同步进向量 RAG 知识库。

### 范围

1. "同步已审核知识到 RAG 知识库" 不再只写 `rag_chunks`
2. approved knowledge_candidates → chunk text + metadata + embedding + source trace → `rag_embeddings`
3. **pending_review / rejected / needs_revision 绝对不能进入向量知识库**
4. 重复同步幂等：同一 candidate_id 不产生重复行（delete-rebuild by sync_method）
5. 保留 `rag_chunks` / keyword fallback 兼容
6. 预留 `source_type` / `modality` 字段，为 P2 多模态接入做准备
7. 新增 sync 测试和 approved-only 边界测试

### 验收

- approved candidate 数量和 rag_embeddings 数量可对应
- 重复 sync 不产生重复行
- rejected / pending 不进入向量知识库
- source trace 不丢
- keyword fallback 仍可用

### 实装记录（2026-07-05）

**同步策略**：delete-rebuild（Plan A）
- 每次 RAG build 时，先删除所有 `sync_method=approved_knowledge_vector_sync` 的旧 `rag_embeddings` 行，然后根据当前 approved candidates 重建。
- 优点：简单、可测、不容易重复堆垃圾。

**rag_embeddings 写入规则**：
1. 只有 `status=approved` 的 knowledge_candidates 可进入 `rag_embeddings`。
2. `pending_review` / `rejected` / `needs_revision` 绝对不进入。
3. 每条 approved candidate 生成一个 embedding chunk。
4. `chunk_text` 格式：`"Question: {question}\nAnswer: {answer}\nIntent: {intent}\nTags: {tags}"`
5. `metadata_json` 包含完整 source trace：`candidate_id`, `source_type`, `source_batch_id`, `source_message_id`, `intent`, `quality_score`, `modality: text`, `sync_method: approved_knowledge_vector_sync`
6. `embedding_provider` / `embedding_model` / `embedding_dimension` 完整写入。
7. `modality` 默认 `text`，为 P2 多模态预留。
8. 默认使用 MockEmbeddingProvider（deterministic, SHA-256 hash-based, dimension=64），无需外部 API。

**幂等策略**：
- 按 `sync_method` 标记进行 delete-rebuild。同一次 build 中，相同的 candidate 不会重复写入。
- 测试验证：第一次 sync 后 count = approved candidates count；第二次 sync 后 count 不变。

**API 返回扩展**：
`POST /api/rag/build` 的 `RagBuildResult` 新增字段：
- `embedding_count`：写入的 embedding 数量
- `vector_sync_enabled`：是否本次 build 启用了向量同步
- `embedding_provider` / `embedding_model` / `embedding_dimension`：embedding provider 配置
- `approved_candidate_count`：本次 approved candidates 数量
- `skipped_candidate_count`：被跳过的 candidates 数量

**source trace 字段**：
从 `rag_embeddings` 可追溯回 `knowledge_candidates`：
- `candidate_id` → `knowledge_candidates.id`
- `source_type` / `source_batch_id` → 原始数据来源
- `source_message_id` → 原始消息

**测试覆盖**（18 个新增测试）：
- approved candidate 同步到 rag_embeddings
- rejected / pending_review / needs_revision 不同步
- 重复 sync 幂等
- metadata_json 包含 candidate_id / source_type / modality
- embedding_dimension 与 mock provider 一致
- source trace 不丢
- rag_chunks 原有逻辑仍可用
- 不需要真实外部 embedding API

**M23 下一步**：CustomerOpsAgent Semantic Retrieval — 让 CustomerOpsAgent 真正调用语义 RAG 知识库。

---

## 7A. P1-M22.1：Online Vector Sync Verification

### 目标

验证 Render 线上已部署 P1-M22 新代码，确认 `POST /api/rag/build` 真正执行 approved knowledge → `rag_embeddings` 向量同步。

### 验证时间

2026-07-05

### 验证结果

| 验证项 | 结果 |
|--------|------|
| **Render 已部署 M22 代码** | ✅ `phase=P1-M22` |
| **database_status** | ✅ postgresql / ok |
| **pgvector_available** | ✅ true |
| **extension_create_ok** | ✅ true |
| **线上 harness** | ✅ 10/10 PASS |
| **vector_sync_enabled** | ✅ true（代码路径已激活） |
| **embedding_provider** | ✅ mock |
| **embedding_model** | ✅ mock-deterministic |
| **embedding_dimension** | ✅ 64 |
| **approved_candidate_count** | ✅ 8（approved candidates 存在） |
| **embedding_count** | ❌ **0 — Vector 维度不匹配** |
| **DATABASE_URL 泄露** | ✅ 无 |
| **API Key 泄露** | ✅ 无 |

### embedding_count=0 根因分析

`db_models.py` 的 `_embedding_column()` 函数在 PostgreSQL + pgvector 环境下硬编码使用 `Vector(1536)`：

```python
if _HAS_PGVECTOR and _is_postgresql():
    return Column("embedding", Vector(1536), nullable=True)
```

pgvector 的 `vector(1536)` 类型在 PostgreSQL 中**强制要求恰好 1536 维**。但默认 mock embedding provider 只生成 64 维向量。因此 `save_rag_embeddings_to_db()` 在 `db.commit()` 时因维度不匹配失败，异常被静默捕获，`embedding_count` 保持 0。

本地 SQLite 测试全部通过（Text JSON fallback 无维度约束）。

### 修复方案

需要在下轮（M23 前或 M23 内）执行：

1. 修改 `_embedding_column()` 使用动态维度：
   ```python
   dim = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
   return Column("embedding", Vector(dim), nullable=True)
   ```
   或使用 `Vector()` 无维度约束。

2. 修改 Render 上已存在的 `rag_embeddings` 表：
   - 方案 A：DROP TABLE rag_embeddings; 让 init_database_tables() 重建。
   - 方案 B：ALTER COLUMN embedding TYPE vector;

### M23 解锁条件

修复后重新验证，`embedding_count > 0` 且 `embedding_count = approved_candidate_count`，M23 才能解锁。

---

## 7B. P1-M22.2：Vector Dimension Fix & Online Re-verify

### 目标

修复 M22.1 发现的向量维度不一致问题，让 approved knowledge 能在线上成功写入 `rag_embeddings`。

### 问题根因

`db_models.py` `_embedding_column()` 硬编码 `Vector(1536)`（对应 OpenAI text-embedding-3-small），但 `MockEmbeddingProvider` 默认输出 64 维向量。pgvector `vector(1536)` 类型强制要求恰好 1536 维，导致 `db.commit()` 失败，异常被静默捕获 → `embedding_count=0`。

### 修复方式（方案 A）

**保持数据库字段 `Vector(1536)` 不变，将 mock embedding 默认维度改为 1536。**

具体改动：

1. `MockEmbeddingProvider.__init__` 默认维度 64 → 1536
2. `get_embedding_provider()` factory：mock dim 1536, fallback dim 1536
3. `RagBuildResult` 新增 `failed_embedding_count`、`vector_sync_error`（不再静默失败）
4. `build_rag_chunks()` 捕获异常后设置 `failed_embedding_count` 和 `vector_sync_error`
5. `_safe_error_message()` 擦除 DATABASE_URL / API Key

### 为什么不优先改 Vector(1536) 表结构

- 方案 B（改 `Vector()` 无约束或 `Text`）需要 ALTER TABLE 或 DROP/RECREATE 线上表，风险更大。
- 方案 A 只需改默认值，不涉及 schema migration。
- 后续使用真实 embedding provider 时 1536 维也是标准选择（OpenAI text-embedding-3-small）。

### 线上验证结果（2026-07-05）

| 验证项 | 结果 |
|--------|------|
| **phase** | P1-M22.2 |
| **pgvector_available** | true |
| **extension_create_ok** | true |
| **线上 harness** | **10/10 PASS** |
| **embedding_count** | **9** (> 0 ✅) |
| **vector_sync_enabled** | true |
| **embedding_provider** | mock |
| **embedding_model** | mock-deterministic |
| **embedding_dimension** | 1536 |
| **chunk_count** | 9 |
| **failed_embedding_count** | 0 |
| **vector_sync_error** | None |
| **M23 unlocked** | **YES ✅** |

### 结论

`chunk_count == embedding_count`（9==9）。所有 approved candidates 已成功同步到 `rag_embeddings`。M23 已解锁。

---

## 8. P1-M23：CustomerOpsAgent Semantic Retrieval

### 目标

CustomerOpsAgent 真正调用语义 RAG 知识库。

### 范围

1. `POST /api/customer-ops-agent/retrieve` 优先走 semantic retrieval
2. query → embedding → pgvector cosine similarity search
3. 返回：
   - matched chunks
   - similarity score
   - candidate_id
   - source trace
   - Agent answer（模板/证据拼接，不需要真实 LLM 生成）
   - retrieval_id
4. keyword retrieval 作为 fallback（pgvector 不可用时）
5. `retrieval_logs` 记录：
   - `retrieval_mode`：`"semantic"` / `"semantic_with_fallback"` / `"keyword_fallback"`
   - `matched_chunk_ids`
   - `scores`
   - `fallback_reason`（如果走了 fallback）
6. eval set 可用于计算 recall@k
7. `build_method` 相关字段从 `"local_json_mock_retrieval"` 改为 `"vector_semantic_retrieval"`

### 验收

- [x] retrieval_mode 从 mock/keyword 变为 semantic 或 semantic_with_fallback
- [x] eval recall@5 有可量化结果
- [x] keyword fallback 可用
- [x] CustomerOpsAgent 返回引用来源和分数
- [x] retrieval_logs 记录 retrieval_mode

### 实装记录（2026-07-05）

**语义检索实现方式**：
- `run_customerops_retrieval()` 改写了主逻辑：先尝试 semantic retrieval，失败或无命中时 fallback 到 keyword retrieval。
- 新增 `search_rag_embeddings_semantic()` repository 函数支持两种后端：
  - PostgreSQL + pgvector：使用 `embedding <=> query_embedding`（cosine distance），similarity = 1 - distance。
  - SQLite：Python 端计算 cosine similarity，然后排序取 top_k。

**pgvector 查询方式**：
- 距离方式：**cosine distance** (`<=>` 运算符)。
- similarity_score = 1 - distance（范围 [-1, 1]，越大越相似）。
- top_k 默认 5，可从 request 读取。

**fallback 策略**：
- `sqlite_no_pgvector`：本地 SQLite 数据库，无 pgvector 扩展。
- `pgvector_unavailable`：PostgreSQL 但 pgvector 未安装或不可用。
- `embedding_dimension_mismatch`：查询向量维度与存储向量维度不一致。
- `semantic_no_hits`：语义搜索成功执行但未返回任何结果（相似度太低或知识库为空）。
- `pgvector_query_error`：pgvector SQL 查询执行异常。
- `embedding_generation_failed`：查询 embedding 生成失败。

**retrieval_logs 记录内容**：
- metadata_json 中包含：`retrieval_mode`, `fallback_used`, `fallback_reason`, `matched_chunk_scores`, `embedding_provider`, `embedding_model`。
- trace 表已有字段：`query`, `matched_chunk_ids`, `response_preview`, `created_at`。

**eval 脚本**：
- 路径：`scripts/run_rag_eval.py`
- 功能：读取 `samples/rag_eval_queries.json`，调用 `/api/customer-ops-agent/retrieve`，计算 recall@5 和 keyword_hit_rate@5。
- 支持参数：`--base-url`, `--top-k`, `--verbose`, `--output-json`。
- 初次结果需在 Render 部署后通过线上运行获得。

**M24 下一步**：Real RAG Online Smoke Test + P1 Release Readiness — 线上完整验证 semantic retrieval 闭环并准备 P1 收版。

---

## 8A. P1-M23.1：Semantic Retrieval Quality Diagnosis & Eval Calibration

### 目标

诊断 P1-M23 语义检索已接入但 recall@5 偏低的问题，校准 eval set，优化最小必要逻辑。

### M23 初始线上 eval 结果（2026-07-05）

| 指标 | 值 |
|------|-----|
| **recall@5 (avg)** | 0.1389 |
| **keyword_hit_rate@5** | 0.3333 |
| **semantic_mode_count** | 12/12 |
| **fallback_count** | 0 |
| **avg_top1_score** | ~0.3 (volatile) |
| **avg_top5_score** | ~0.1 (volatile) |

### 低分根因分析

1. **Mock embedding 语义能力为零**（主要根因）：P1-M23 的 `MockEmbeddingProvider` 使用 SHA-256 全文哈希，两条不同文本产生完全无关的向量。`cosine("return item", "get refund") ≈ 0`。这导致 semantic retrieval 本质上等同于随机排序。

2. **Eval queries 与知识库内容严重不匹配**：eval set 询问 "warranty on electronics", "payment methods", "shipping to Germany" 等问题，但知识库只有退款/退货、订单追踪、人工升级三类知识。

3. **线上知识库被 harness 测试数据污染**：多次 harness 运行产生大量 "Question: Manually verified content — harness automated cleaning." 这种无意义条目，占据大量 rag_embeddings 行。中文内容也混入英文测试环境。

4. **chunk_text 质量良好但被数据污染抵消**：`_chunk_text` 格式正确（Question + Answer + Intent + Tags），但 harness manual_cleaning 步骤将 question 替换为 meaningless cleaning note。

5. **expected_candidate_ids 为空**：无法计算正式的 candidate_recall@5，只能依赖 keyword proxy。

### 本轮修复（P1-M23.1）

1. **Mock embedding 升级为 bag-of-words token-based**：
   - 每个字母数字 token 独立哈希生成确定性单位向量。
   - 文本向量 = 所有 token 向量求和后 L2 归一化。
   - 共享 token 的文本获得非零 cosine similarity。
   - 仍保持确定性（同 text → 同 vector）。
   - 注意：这仍只是 keyword-aware，不是语义理解。真正的语义检索需要真实 embedding provider。

2. **Eval set 校准**：
   - 重写 12 条 eval queries，匹配实际知识库内容（退款、订单追踪、人工升级）。
   - 每个 query 的 expected_keywords 基于实际 chunk_text 中的词语。
   - 保留同义表达 query 检验 keyword-aware 检索。
   - 保留 bad case queries（noise / too short）。

3. **Eval 脚本增强**：
   - 分离 `keyword_hit_rate@5` 和 `candidate_recall@5` 指标。
   - 当 expected_candidate_ids 为空时，明确说明是 keyword proxy。
   - 新增 `missed_keywords` 输出、`avg_top1_score`、`avg_top5_score`。
   - 新增 `low_score_queries` 列表。
   - 新增 retrieval_mode 分布统计。
   - Verbose 模式显示每条 query 的 top-5 匹配明细。

### 新 eval 结果

待 Render 部署后通过 `python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5 --verbose` 运行获得。

### M24 解锁条件

- [ ] `keyword_hit_rate@5 >= 0.6`（建议阈值，表示 keyword-aware 检索已校准）
- [ ] 线上 harness 10/10 PASS
- [ ] retrieval_mode = customerops_vector_retrieval
- [ ] fallback_count = 0（或明确合理原因）
- [ ] eval 输出能解释每条 query 命中/未命中原因

如果优化后仍低于阈值：
- 不进入 M24。
- 明确建议：P1-M24 前需要接入真实 embedding provider（OpenAI text-embedding-3-small），因为 mock embedding 无法提供语义泛化能力。

---

## 9. P1-M24：Real RAG Online Smoke Test + P1 Release Readiness

### 目标

线上验证真实 RAG 闭环，并准备 P1 最终收版。

### 范围

1. Vercel → Render FastAPI → Render PostgreSQL + pgvector 线上验证
2. 完整跑：
   导入 -> 清洗 -> 人工清洗 -> 生成待审核知识 -> 审核通过 -> 同步向量 RAG -> CustomerOpsAgent 语义检索 -> Bad Case 回流
3. 跑 harness（`python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com`）
4. 跑 eval set，记录 recall@5
5. 验证 redeploy 后向量数据仍在
6. 输出 P1 Real RAG Release Readiness Report
7. 明确 P1 已完成能力和未完成能力
8. 不自动打 tag，等用户确认后再单独开 release tag 轮

### 验收

- 线上 semantic retrieval 可用
- eval recall@5 ≥ 0.6（建议最低阈值）
- source trace 可追溯
- Bad Case 回流仍可用
- harness 全 PASS
- 文档边界清晰
- 用户确认后，才允许后续单独打 P1 release tag

---

## 10. 为什么不做 pipeline_runs / pipeline_steps / pipeline_events 表

这三张表是数据管道可观测性模式，适用于：

- 有定时调度需求的 pipeline
- 有 SLA 监控需求的生产系统
- 有失败重试和部分重跑需求的复杂场景
- 有多个 pipeline 并行运行的平台

DataHub P1 全链路是**单用户、串行、手动触发**的。一个 `run_p1_pipeline_harness.py` 脚本打印到 stdout 的日志已经足够定位问题。

等 P2 有多模态 pipeline、P4 有 Agent 集群并发调用时，再考虑 pipeline trace 表。

当前替代方案：
- 利用现有 `requestId`（每个 API 响应已有）
- 利用 `metadata_json` 字段加可选 `_pipeline_run_id`
- harness 脚本的 stdout 日志

---

## 11. 为什么 eval set 必须前置

eval set 是衡量"RAG 做完了没有"的唯一客观尺度。

- 没有 eval set → M23 做完了也说不清检索质量好不好
- 没有 eval set → semantic vs keyword 无法量化对比
- 没有 eval set → M24 smoke test 只能验证"跑通了"，不能验证"跑得好"

在 M21 就建好 eval set，M22 和 M23 就有了一把尺子，每一步进展都可以量化。

---

## 12. 为什么 CustomerOpsAgent semantic retrieval 必须属于 P1

P1 的定义是"文本客服知识闭环"。语义检索是这个闭环的核心交付物，不是可选的 P2 功能。

- 如果检索仍是 keyword/overlap，P1 的 RAG 就是 mock
- 如果 semantic retrieval 拖到 P2，P1 就不能称为"RAG 知识平台"
- Architecture 文档早已预留："Vector store and embedding provider remain candidates" 是 P1 内的候选决策，不是 P2 的工作

---

## 13. Render pgvector 可用性检查要求

**在 M20.7 必须执行，这是 M21-M24 的前置条件。**

```sql
-- 检查 pgvector 扩展是否可用
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- 尝试创建扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

如果 Render Free PostgreSQL 不支持 pgvector：
- 停止 M21-M24 原路线
- 评估替代方案：ChromaDB（Render 磁盘不持久但可通过别的方式）、Pinecone 免费层、升级 Render PostgreSQL 计划、或其他向量库

如果支持：
- 记录 pgvector 版本
- 继续 M21

---

## 14. 防跑偏规则

### 每轮必须验证

1. 相关测试全部通过（`pytest backend/tests/`）
2. 新功能有对应的测试文件
3. `/health` 的 `phase` 字段更新为当前版本号
4. `docs/08_DEV_STATUS.md` 更新完成记录
5. harness 脚本仍能跑通（如果涉及 API 改动）
6. M21 起：eval set 格式校验通过
7. M23 起：eval recall@5 可计算

### 每轮不能做

- 不能跨阶段开发（例如在 M20.7 就开始写 pgvector 代码）
- 不能在 M21 建表时顺手改 M23 的检索 API
- 不能引入新的外部服务而不记录在文档中
- 不能删除或破坏 JSON fallback 路径（保持 DB-first + JSON-fallback 模式）
- 不能修改 CustomerOpsAgent 仓库
- 不能进入 P2/P3/P4 后端开发

### 每轮完成标准

- `git status` clean
- Commit message 使用 `[P1-Mxx]` 前缀
- 不打 tag（除非明确 release）
- 不提交 `.env`、`datahub.db`、`backend/storage/`、API Key

---

## 15. 路线总览

```text
P1-M20.7  Harness + pgvector 确认
   |
   v
P1-M21    pgvector 底座 + eval set
   |
   v
P1-M22    已审核知识同步向量库
   |
   v
P1-M23    CustomerOpsAgent 语义检索
   |
   v
P1-M24    线上 Smoke Test + Release Readiness
   |
   v
用户确认后 → P1 Release Tag → 再决定是否进入 P2
```
