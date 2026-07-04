# P1-M19 RAG / Agent / Bad Case DB Persistence Report

## 1. 本轮目标

将 RAG 构建、CustomerOpsAgent 检索和 Bad Case 回流迁移为数据库持久化，使数据在 Render 重启或重新部署后依然保留。本轮完成后，P1 主链路（导入 → 清洗 → 人工清洗 → 知识抽取 → 审核 → RAG → Agent 检索 → Bad Case）已全部数据库持久化。

## 2. 迁移的 API

| API 路径 | 变更 |
|----------|------|
| `POST /api/rag/build` | RAG build 双写 DB（rag_chunks 表）+ JSON；只使用 approved 候选 |
| `GET /api/rag/chunks` | RAG chunk 列表 DB 优先，回退 JSON |
| `GET /api/rag/chunks/{chunk_id}` | RAG chunk 详情 DB 优先，回退 JSON |
| `POST /api/customer-ops-agent/retrieve` | Agent 检索优先读 DB rag_chunks；结果双写 retrieval_logs + JSON |
| `GET /api/customer-ops-agent/retrievals/{retrieval_id}` | 检索 trace DB 优先，回退 JSON |
| `POST /api/customer-ops-agent/bad-cases` | Bad Case 提交双写 DB（bad_cases 表）+ JSON |
| `GET /api/bad-cases` | Bad Case 列表 DB 优先，回退 JSON |
| `GET /api/bad-cases/{bad_case_id}` | Bad Case 详情 DB 优先，回退 JSON |
| `PATCH /api/bad-cases/{bad_case_id}` | Bad Case 更新同时写 DB |
| `POST /api/bad-cases/{bad_case_id}/create-draft` | Bad Case → candidate draft 双写 knowledge_candidates + Bad Case 更新 |

API path、request/response contract 均保持不变。前端无需修改。

## 3. 写入的数据库表

| 操作 | 写入表 |
|------|--------|
| RAG Build | `rag_chunks`（id, candidate_id, chunk_text, intent, tags, metadata_json, created_at） |
| Agent 检索 | `retrieval_logs`（id, query, matched_chunk_ids, response_preview, metadata_json, created_at） |
| Bad Case 提交 | `bad_cases`（id, retrieval_id, user_question, bad_answer, expected_answer, status, created_candidate_id, metadata_json, created_at, updated_at） |
| Bad Case → draft | `knowledge_candidates`（source_type=bad_case, status=pending_review, extraction_method=bad_case_resolution） |

metadata_json 中保存完整的 source trace 和补充字段，避免核心字段丢失。

## 4. RAG 构建：只使用 approved candidate

- `build_rag_chunks` 从 `list_knowledge_candidates()` 读取所有候选。
- 只有 `review_status == "approved"` 的候选生成 RAG chunks。
- `pending_review`、`needs_revision`、`rejected` 候选被跳过，不计入 built_count。
- 跳过原因记录在 `skipped_reasons` 中（如 `review_status_pending_review`、`review_status_rejected`）。
- DB 优先读取候选（P1-M18 已实现），JSON fallback。

## 5. Agent 检索：读取 DB rag_chunks

- `run_customerops_retrieval` 调用 `list_rag_chunks()` 获取所有 chunks。
- `list_rag_chunks()` DB 优先，有数据则直接返回，否则回退 JSON。
- 检索仍然使用 local JSON mock retrieval（token overlap 算法），不接真实 embedding/向量数据库/LLM。
- 检索 trace 通过 `_write_retrieval_trace` 双写：
  - JSON：`backend/storage/retrieval_logs/{retrieval_id}.json`
  - DB：`retrieval_logs` 表
- retrieval_logs.metadata_json 保存完整 trace（filters、result_count、conversation_id、agent_session_id 等）。

## 6. Bad Case 写入 DB

- `create_bad_case` 生成 BadCaseRecord 后通过 `_write_bad_case` 双写：
  - JSON：`backend/storage/bad_cases/{bad_case_id}.json`
  - DB：`bad_cases` 表
- `update_bad_case` 同时更新 JSON 和 DB 中的记录。
- `list_bad_cases` / `get_bad_case` DB 优先，JSON fallback。
- bad_cases.metadata_json 保存 issue_type、severity、linked_chunk_ids、retrieval_result_count、conversation_id、agent_session_id、metadata 等字段。

## 7. Bad Case 生成待审核 candidate

- `create_candidate_from_bad_case` 生成的 candidate 通过 `create_candidate_from_bad_case_in_db` 双写 knowledge_candidates 表。
- 生成的 candidate 属性：
  - `source_type = "bad_case"`
  - `source_id = bad_case_id`（用于去重）
  - `review_status = "pending_review"`
  - `extraction_method = "bad_case_resolution"`
- 去重策略：同一 source_id + question + answer 更新已有行，不创建重复候补。
- 生成的 candidate 可进入现有知识审核链路（GET /api/review/pending、approve/reject/needs-revision）。
- bad_cases.created_candidate_id / linked_candidate_id 关联生成的 candidate。

## 8. 幂等策略

- **RAG Build**：`save_rag_chunks_to_db` replace 全部 rag_chunks 行（先 delete 再 insert），不无限追加重复 chunk。
- **Agent 检索**：`save_retrieval_log_to_db` 按 retrieval_id upsert。
- **Bad Case 提交**：`save_bad_case_to_db` 按 bad_case_id upsert。
- **Bad Case → candidate**：`create_candidate_from_bad_case_in_db` 按 source_id + question + answer 去重。

## 9. 读取策略

所有 RAG、Agent 检索、Bad Case 读取遵循 **DB 优先，JSON fallback**：

- 读取时先查询数据库，有数据则直接返回。
- 数据库无数据或查询失败时，回退到 JSON storage。
- 写入时双写（DB + JSON），保证旧测试和兼容性。

## 10. 如何验证数据入库

### 本地 SQLite 验证

```bash
# 初始化数据库
python scripts/init_database.py

# 启动后端
cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 通过前端或 API 执行导入 → 清洗 → 人工清洗 → 知识抽取 → 审核 → Build RAG → Agent 检索 → Bad Case
# 然后查询验证：

sqlite3 datahub.db "SELECT COUNT(*) FROM rag_chunks;"
sqlite3 datahub.db "SELECT COUNT(*) FROM retrieval_logs;"
sqlite3 datahub.db "SELECT COUNT(*) FROM bad_cases;"
sqlite3 datahub.db "SELECT source_type, status, COUNT(*) FROM knowledge_candidates GROUP BY source_type, status;"
```

### 线上 PostgreSQL 验证

部署到 Render 后，通过 Render PostgreSQL 控制台或 psql 连接执行：

```sql
SELECT COUNT(*) FROM rag_chunks;
SELECT COUNT(*) FROM retrieval_logs;
SELECT COUNT(*) FROM bad_cases;
SELECT source_type, status, COUNT(*) FROM knowledge_candidates GROUP BY source_type, status;
```

## 11. Render PostgreSQL DATABASE_URL 说明

Render 已配置 `DATABASE_URL` 环境变量指向 PostgreSQL。后端启动时自动读取该变量连接 PostgreSQL。

- 本地未设置 `DATABASE_URL` → 默认 SQLite（`datahub.db`）
- Render 设置 `DATABASE_URL` → 使用 PostgreSQL

当前 Render Free Postgres 仅作为短期 P1-P4 打通测试使用，生产环境需升级到付费实例。

## 12. 新增测试

`backend/tests/test_rag_agent_badcase_db_persistence.py`（16 个测试）：

1. approved candidate 构建 RAG 后 rag_chunks 表有数据
2. pending_review candidate 不进入 rag_chunks
3. rejected candidate 不进入 rag_chunks
4. 重复 Build RAG 不无限追加重复 chunk
5. RAG chunks 可以从 DB 读取
6. Agent 检索优先读取 DB rag_chunks
7. Agent 检索后 retrieval_logs 表有数据
8. retrieval detail 可以从 DB 读取
9. Bad Case 提交后 bad_cases 表有数据
10. Bad Case 生成 knowledge_candidates 草稿
11. Bad Case 生成的 candidate 状态为 pending_review
12. created_candidate_id 能关联 candidate
13. Bad Case 生成的 candidate 能被 candidate list 读取
14. DB 优先、JSON fallback 不破坏旧链路
15. Health check 报告 P1-M19
16. 不依赖真实 PostgreSQL，使用临时 SQLite

## 13. 尚未迁移的链路

P1 主链路已全部完成数据库持久化。本轮无剩余迁移项。

以下功能不在 P1 范围：

- P2 AI 素材中心（多模态）
- P3 数据资产复用（销售培训导出、微调数据集导出）
- P4 MCP + Agent 集群
- 真实 LLM / embedding / 向量数据库

## 14. 下一步 P1-M20

P1-M20 DB Release & Online Persistence Smoke Test：

- 完整线上 Smoke Test（Vercel 前端 → Render 后端 → PostgreSQL）
- Render 后端重启后复测（确认数据仍在）
- 数据库控制台 SELECT 验证（所有表有对应记录）
- README / 部署文档更新（本地 SQLite 与线上 PostgreSQL 配置说明）
- 输出数据库版 P1 最终验收报告（`docs/27_DB_RELEASE_REPORT.md`）
- P1-M20 打 release tag：`p1-m20-db-release`
