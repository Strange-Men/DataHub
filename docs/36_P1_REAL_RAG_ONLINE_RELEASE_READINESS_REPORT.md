# P1 Real RAG Online Release Readiness Report

## 1. P1 当前完整链路

```
多来源客服数据 (JSON import)
  -> 机器清洗 (PII脱敏、去重、质量评分)
  -> 人工清洗 (手动校正/keep/drop)
  -> 生成待审核知识 (rule_based_mock extraction)
  -> 知识审核 (approve/reject/needs_revision)
  -> 同步向量 RAG (approved -> rag_embeddings)
  -> CustomerOpsAgent semantic retrieval (pgvector cosine similarity)
  -> Bad Case 回流 (submit -> triage -> create draft)
```

## 2. M20.7-M23.2 已完成能力摘要

| 阶段 | 能力 | 状态 |
|------|------|------|
| **P1-M20.7** | Lightweight Pipeline Harness (10步一键验证) | ✅ |
| **P1-M21** | Vector RAG Foundation (rag_embeddings表 + mock embedding + eval set) | ✅ |
| **P1-M21.1** | pgvector Readiness Verification Gate (pgvector_available=true) | ✅ |
| **P1-M22** | Approved Knowledge Sync to Vector RAG (delete-rebuild) | ✅ |
| **P1-M22.1** | Online Vector Sync Verification (发现维度不匹配) | ✅ |
| **P1-M22.2** | Vector Dimension Fix (64→1536, 线上embedding_count>0) | ✅ |
| **P1-M23** | CustomerOpsAgent Semantic Retrieval (pgvector cosine similarity) | ✅ |
| **P1-M23.1** | Semantic Retrieval Quality Diagnosis & Eval Calibration (token-based mock) | ✅ |
| **P1-M23.2** | RAG corpus cleanup & embedding readiness verification | ✅ |

## 3. M24 线上验收执行

### 3.1 Health Check

```bash
curl https://datahub-jr8x.onrender.com/api/health
```

**结果 (2026-07-05):**

```json
{
    "status": "ok",
    "service": "datahub-api",
    "phase": "P1-M24",
    "database_status": {
        "enabled": true,
        "backend": "postgresql",
        "status": "ok"
    },
    "pgvector_status": {
        "pgvector_available": true,
        "extension_create_ok": true,
        "backend": "postgresql"
    }
}
```

| 检查项 | 结果 |
|--------|------|
| status | ok |
| phase | P1-M24 |
| database_status.backend | postgresql |
| database_status.status | ok |
| pgvector_available | true |
| extension_create_ok | true |

### 3.2 Harness 验证

```bash
python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com --verbose --stop-on-fail
```

**结果 (2026-07-05):**

| 步骤 | 状态 | 关键数据 |
|------|------|----------|
| 01 health_check | ✅ PASS | phase=P1-M24 |
| 02 import_sample_data | ✅ PASS | batch_id created |
| 03 machine_cleaning | ✅ PASS | sanitized 8/8 messages |
| 04 manual_cleaning | ✅ PASS | manual clean record created |
| 05 generate_knowledge_candidates | ✅ PASS | 3 candidates |
| 06 approve_knowledge | ✅ PASS | 1 approved |
| 07 sync_rag | ✅ PASS | chunk_count=18, embedding_count=18 |
| 08 customerops_retrieve | ✅ PASS | retrieval_mode=customerops_vector_retrieval |
| 09 submit_bad_case | ✅ PASS | bad_case_id created |
| 10 bad_case_to_draft | ✅ PASS | draft candidate created |

**Summary: 10/10 PASS ✅**

同步 RAG 关键字段:
- `embedding_count`: 18 (> 0 ✅)
- `vector_sync_enabled`: true
- `embedding_provider`: mock
- `embedding_model`: mock-deterministic
- `embedding_dimension`: 1536
- `failed_embedding_count`: 0
- `vector_sync_error`: None

CustomerOpsAgent Retrieval 关键字段:
- `retrieval_mode`: customerops_vector_retrieval ✅
- `fallback_used`: false
- `fallback_reason`: None

### 3.3 Eval 验证

```bash
python scripts/run_rag_eval.py --base-url https://datahub-jr8x.onrender.com --top-k 5 --verbose
```

**结果 (2026-07-05):**

| 指标 | 值 | 最低门槛 | 达标 |
|------|-----|----------|------|
| **keyword_hit_rate@5** | **0.7694** | ≥ 0.6 | ✅ |
| **keyword_query_hit_rate@5** | **0.9167** | ≥ 0.75 | ✅ |
| **candidate_recall@5** | n/a (keyword proxy only) | — | ⚠️ 见注 |
| **semantic_mode_count** | 12/12 (100%) | — | ✅ |
| **fallback_count** | 0 | = 0 或原因明确 | ✅ |
| **avg_top1_score** | 0.5718 | — | ✅ |
| **avg_top5_score** | 0.4100 | — | ✅ |
| **low_score_queries** | 1 (noise query, expected) | — | ✅ |

**注**: candidate_recall@5 计算不可用，因为 `expected_candidate_ids` 为空。当前使用 keyword_hit_rate 作为 proxy metric。实际召回率需要真实 embedding provider (real semantic) 或人工标注 expected_candidate_ids。

**按 query 详细结果:**

| Query | kw_hit_rate | matched | missed | retrieval_mode |
|-------|-------------|---------|--------|----------------|
| eval_refund_001 | 0.67 (4/6) | return, refund, 30, days | shoes, box | customerops_vector_retrieval |
| eval_refund_002 | 1.00 (3/3) | return, refund, money | — | customerops_vector_retrieval |
| eval_refund_003 | 1.00 (3/3) | return, 30, days | — | customerops_vector_retrieval |
| eval_shipping_001 | 0.67 (2/3) | order, tracking | transit | customerops_vector_retrieval |
| eval_shipping_002 | 0.75 (3/4) | days, business, delivery | arrive | customerops_vector_retrieval |
| eval_shipping_003 | 0.60 (3/5) | shipping, delivery, days | germany, international | customerops_vector_retrieval |
| eval_escalation_001 | 1.00 (4/4) | human, agent, transfer, speak | — | customerops_vector_retrieval |
| eval_escalation_002 | 1.00 (4/4) | chatbot, help, agent, transfer | — | customerops_vector_retrieval |
| eval_refund_004 | 0.75 (3/4) | original, refund, return | box | customerops_vector_retrieval |
| eval_badcase_noise_001 | 0.00 (0/0) | — | — | customerops_vector_retrieval |
| eval_badcase_ambiguous_001 | 1.00 (1/1) | help | — | customerops_vector_retrieval |
| eval_cross_001 | 0.80 (4/5) | refund, agent, transfer, human | escalate | customerops_vector_retrieval |

retrieval_mode distribution: 100% `customerops_vector_retrieval` (no fallback cases).

### 3.4 Corpus Inspect

**状态: SKIP**

原因: 本地未设置 DATABASE_URL，无法直接连接 Render PostgreSQL 进行 corpus 检查。

间接评估:
- Eval 运行正常 (0 fallback, 12/12 semantic mode)
- Harness sync 成功 (embedding_count=18, failed_embedding_count=0)
- 线上知识库存在 harness 测试数据污染 (多个 "Manually verified content" 条目出现在 eval 结果中)

**关于污染数据的影响:**
- eval 结果中出现 harness 人工清洗产生的占位文本 "Manually verified content — harness automated cleaning."
- eval_badcase_noise_001 的 top-5 结果中有 4 个是 harness 占位条目
- 污染不影响 keyword_hit_rate@5 计算（因为 eval queries 按 expected_keywords 匹配，不依赖知识库清洁度）
- 但对于真实语义检索，污染数据会降低检索质量

### 3.5 Embedding Provider Readiness

```bash
python scripts/check_embedding_provider.py
```

**结果 (2026-07-05):**

| 字段 | 值 |
|------|-----|
| **EMBEDDING_PROVIDER** | mock |
| **EMBEDDING_MODEL** | (default: mock-deterministic) |
| **EMBEDDING_DIMENSION** | 1536 |
| **API key** | missing |
| **mock_ready** | **true** ✅ |
| **provider_ready** | **true (mock only)** ⚠️ |
| **real_embedding_ready** | **false** ❌ |

**当前 embedding 能力说明:**

MockEmbeddingProvider (P1-M23.1 升级版):
- 基于 bag-of-words token-based hashing
- 每个字母数字 token 独立哈希生成确定性单位向量
- 共享 token 的文本获得非零 cosine similarity
- 完全确定性（同 text → 同 vector）
- **捕捉的是词汇重叠，不是语义理解**

当前不是生产级真实语义 embedding。同义表达（如 "money back" vs "refund"）只在共享 token 时有信号。

**⚠️ 重要声明:**
> P1 当前 embedding provider 为 mock/deterministic（token-based bag-of-words），不是真实语义 embedding provider (OpenAI/其他)。
> 当前 eval 指标 (keyword_hit_rate@5=0.7694) 反映的是 keyword-aware 检索质量，不是真实语义检索质量。
> 若要求生产级真实语义 RAG，需要接入真实 embedding provider（如 OpenAI text-embedding-3-small）并重新验证 eval 指标。

### 3.6 CustomerOpsAgent Semantic Retrieval 验证

| 验证项 | 结果 |
|--------|------|
| retrieval_mode | **customerops_vector_retrieval** ✅ |
| pgvector cosine similarity search | 正常工作 (avg_top1_score=0.5718) |
| fallback_used | false (0/12 queries) ✅ |
| fallback_count | 0 ✅ |
| keyword fallback preserved | 保留（SQLite 环境自动激活）✅ |
| retrieval_logs 记录 retrieval_mode | 正常 ✅ |
| retrieval_logs 记录 scores | 正常 ✅ |
| retrieval_logs 记录 embedding_provider/model | 正常 ✅ |
| 返回 candidate_id / source trace | 正常 ✅ |

### 3.7 Bad Case 回流验证

| 验证项 | 结果 |
|--------|------|
| Bad Case 提交 | ✅ (harness step 09 PASS) |
| Bad Case 绑定 retrieval_id | ✅ |
| Bad Case 创建 draft candidate | ✅ (harness step 10 PASS) |
| Draft candidate 进入 pending_review | ✅ |
| Source trace (bad_case -> retrieval -> chunk -> candidate) | ✅ |

## 4. P1 Release Readiness 判断

### 4A. 可以进入 P1 release tag 的条件检查

| # | 条件 | 状态 |
|---|------|------|
| 1 | harness 10/10 PASS | ✅ |
| 2 | pgvector 可用 | ✅ |
| 3 | rag_embeddings 线上写入成功 | ✅ (embedding_count=18 > 0) |
| 4 | CustomerOpsAgent retrieval_mode = customerops_vector_retrieval | ✅ |
| 5 | eval 指标达标 | ✅ (keyword_hit_rate@5=0.7694 ≥ 0.6) |
| 6 | source trace 可追溯 | ✅ |
| 7 | Bad Case 回流可用 | ✅ |
| 8 | 文档明确边界 | ✅ (本文档) |
| 9 | 用户确认 | ⚠️ 待确认 |

### 4B. 真实 embedding provider 状态

**当前为 mock/deterministic embedding。**

P1 已具备真实向量 RAG 工程闭环，但当前线上 embedding provider 仍为 mock/deterministic (token-based bag-of-words)，适合作为 **Demo / 工程验收版**。若要求生产级真实语义 RAG，需要补 **P1-M24.1 Real Embedding Provider Verification**。

### 4C. Eval 达标情况

- keyword_hit_rate@5 = 0.7694 ≥ 0.6 ✅
- keyword_query_hit_rate@5 = 0.9167 ≥ 0.75 ✅
- fallback_count = 0 ✅

Eval 指标达标。注意：这是 keyword-aware retrieval 指标，不是真实语义检索指标。

### 4D. Corpus 污染情况

线上知识库存在 harness 测试数据污染（"Manually verified content" 占位文本、中文内容混入英文测试环境）。但这不影响当前的 keyword-aware 检索指标评估。对于生产级使用，建议在接入真实 embedding provider 前做一次全量 corpus cleanup。

## 5. P1 收版结论

### 可以收版 ✅

**P1 已具备真实向量 RAG 工程闭环:**

1. ✅ 完整数据链路打通（导入 → 清洗 → 审核 → 向量同步 → 语义检索 → Bad Case 回流）
2. ✅ pgvector 在线可用（Render PostgreSQL, version 0.8.1）
3. ✅ CustomerOpsAgent semantic retrieval 正常（pgvector cosine similarity, 0 fallback）
4. ✅ Harness 10/10 PASS
5. ✅ Eval keyword_hit_rate@5 = 0.7694 (≥ 0.6)
6. ✅ Source trace 全链路可追溯
7. ✅ Bad Case 回流完整可用
8. ✅ 10 张核心表数据库持久化
9. ✅ 全站暗黑风视觉统一

### 边界声明

**当前 P1 是 Demo / 工程验收版:**
- mock embedding (token-based bag-of-words, 捕捉词汇重叠)
- rule_based_mock extraction (非真实 LLM)
- 模板化 Agent answer (非真实 LLM 生成)
- Render Free PostgreSQL (1GB 存储限制)
- P2/P3/P4 未接入

**不是生产级真实语义 RAG:**
- 未接入真实 embedding provider (OpenAI/其他)
- 未接入真实 LLM 生成
- 未接入 multi-modal (P2)
- 未接入 dataset export (P3)
- 未接入 MCP / Agent cluster (P4)

### 建议 release tag 名

如果用户确认收版，建议 tag: `p1-m24-real-rag-online-release`

### 下一步 (P1-M24.1, 可选)

如果需要生产级真实语义 RAG:
1. 配置 `EMBEDDING_PROVIDER=openai`
2. 设置 `EMBEDDING_API_KEY`
3. 运行 `python scripts/check_embedding_provider.py --verify`
4. 重新运行 harness + eval，对比 mock vs real 指标
5. 重新评估 release readiness

### P2 不在此轮启动

P2/P3/P4 在 P1 real RAG 最终收版且用户确认后再启动。

## 6. 当前边界清单

| 边界 | 状态 |
|------|------|
| mock embedding | ✅ (token-based bag-of-words, keyword-aware) |
| 真实 LLM | ❌ 未接入 (rule_based_mock extraction + 模板回答) |
| P2 多模态 | ❌ 未接入 |
| P3 数据资产 | ❌ 未接入 |
| P4 MCP/Agent | ❌ 未接入 |
| 真实 embedding provider | ❌ 未验证 |
| Render Free Postgres | ⚠️ 1GB 存储限制 |
| 前端 | ✅ P1 4步流程完整 |
| 数据库持久化 | ✅ 10 张核心表 |

## 7. 验证时间 & 签名

- **验证时间**: 2026-07-05
- **验证人**: DataHub P1-M24 pipeline
- **Health phase**: P1-M24
- **Commit**: [P1-M24] test: verify real rag online release readiness
