# P1-M18 Manual Cleaning & Review DB Persistence Report

## 1. 本轮目标

将"人工清洗"和"知识审核"迁移为数据库持久化，使人工清洗记录、候选知识和审核记录在 Render 重启或重新部署后依然保留。

## 2. 迁移的 API

| API 路径 | 变更 |
|----------|------|
| `PATCH /api/sanitized/{batch_id}/messages/{message_id}/manual-clean` | 人工清洗结果双写 DB（manual_cleaning_records）+ JSON |
| `GET /api/sanitized/{batch_id}` | 从 DB 读取 sanitized batch 时自动 merge manual cleaning records |
| `POST /api/extraction/run/{batch_id}` | 知识抽取优先从 DB 读取 sanitized messages；结果双写 DB + JSON |
| `GET /api/knowledge/candidates` | DB 优先，merge JSON fallback（确保 legacy import 候选不丢失） |
| `GET /api/knowledge/candidates/{candidate_id}` | DB 优先，JSON fallback |
| `PATCH /api/knowledge/candidates/{candidate_id}` | 编辑结果双写 DB + JSON |
| `GET /api/review/pending` | DB 优先，JSON fallback |
| `POST /api/review/{candidate_id}/approve` | 审核通过后更新 candidate.status + 写 review_records |
| `POST /api/review/{candidate_id}/reject` | 驳回后更新 candidate.status + 写 review_records |
| `POST /api/review/{candidate_id}/needs-revision` | 打回修改后更新 candidate.status + 写 review_records |

API path、request/response contract 均保持不变。前端无需修改。

## 3. 写入的数据库表

| 操作 | 写入表 |
|------|--------|
| 人工清洗保存 | `manual_cleaning_records`（record_id, sanitized_message_id, cleaner, action, original_content, cleaned_content, note, created_at） |
| 知识抽取 | `knowledge_candidates`（id, source_type, source_id, question, answer, intent, tags, risk_level, quality_score, status, metadata_json, created_at, updated_at） |
| 审核通过/驳回/打回 | `knowledge_candidates.status` 更新 + `review_records` 新增（id, candidate_id, reviewer, action, note, snapshot_json, created_at） |

## 4. 读取策略

**DB 优先，JSON merge fallback：**

- `list_knowledge_candidates`：合并 DB 和 JSON 候选，DB 优先（同 candidate_id 时 DB 覆盖 JSON），确保 legacy import、bad_case draft 等 JSON-only 来源不丢失。
- `get_knowledge_candidate`：先查 DB，未找到则回退 JSON。
- `get_sanitized_batch`：先查 DB 获取 sanitized messages，再查 DB 获取 manual cleaning records 并 merge。DB 无数据时回退 JSON。
- `list_pending_review_candidates`：先查 DB，有数据则直接返回，否则回退 JSON。

## 5. 尚未迁移的链路

以下链路仍使用 JSON storage，将在 P1-M19 逐步迁移：

- RAG 构建（`POST /api/rag/build`）
- RAG 检索（`POST /api/rag/search`）
- CustomerOpsAgent 检索（`POST /api/customer-ops-agent/retrieve`）
- Bad Case 反馈（`POST /api/customer-ops-agent/bad-cases`）
- Bad Case to draft（`POST /api/bad-cases/{bad_case_id}/create-draft`）
- Legacy RAG 导入（`POST /api/legacy-rag/import`）

## 6. 人工清洗结果如何影响知识抽取

知识抽取在 `run_extraction` 中调用 `get_sanitized_batch`，后者从 DB 读取 sanitized messages 并 merge 人工清洗记录：

- `action=drop` → 消息被跳过，不参与知识抽取
- `action=needs_review` → 消息被跳过，不参与知识抽取
- `action=keep_edited` → 使用 `manual_cleaned_content`（人工修正后的内容）
- `action=keep` → 使用原始 `content`（机器清洗后的内容）
- 如果某条消息没有人工清洗记录 → 使用机器清洗后的 `content` 和 `suggested_action` / `quality_level` 判断是否进入抽取

## 7. 审核状态如何持久化

审核操作（approve / reject / needs_revision）执行以下持久化步骤：

1. 更新 `knowledge_candidates` 表中对应行的 `status` 字段
2. 在 `knowledge_candidates.metadata_json` 中记录 reviewer、review_note、reviewed_at
3. 在 `review_records` 表中新增一条审核记录（含 candidate_snapshot 供追溯）

页面刷新后，candidate 列表和详情 API 优先从 DB 读取，审核状态保持正确。

## 8. 幂等策略

- **人工清洗**：同一 `sanitized_message_id` 允许多条记录。最新 `created_at` 记录为有效记录。`get_sanitized_batch` 取最新一条 merge。
- **知识抽取**：按 `source_id + question + answer` 组合去重。重复抽取同一 batch 时，先删除旧记录再插入新记录，不无限追加。
- **审核记录**：每次审核操作新增一条 `review_records`，不覆盖历史记录。
- **candidate.status**：审核时原地更新，保持最新状态。

## 9. 如何验证数据入库

### 本地 SQLite 验证

```bash
# 初始化数据库
python scripts/init_database.py

# 启动后端
cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 通过前端或 API 执行导入 → 清洗 → 人工清洗 → 知识抽取 → 审核
# 然后查询验证：

sqlite3 datahub.db "SELECT COUNT(*) FROM manual_cleaning_records;"
sqlite3 datahub.db "SELECT COUNT(*) FROM knowledge_candidates;"
sqlite3 datahub.db "SELECT COUNT(*) FROM review_records;"
sqlite3 datahub.db "SELECT status, COUNT(*) FROM knowledge_candidates GROUP BY status;"
```

### 线上 PostgreSQL 验证

部署到 Render 后，通过 Render PostgreSQL 控制台或 psql 连接执行：

```sql
SELECT COUNT(*) FROM manual_cleaning_records;
SELECT COUNT(*) FROM knowledge_candidates;
SELECT COUNT(*) FROM review_records;
SELECT status, COUNT(*) FROM knowledge_candidates GROUP BY status;
```

## 10. Render PostgreSQL DATABASE_URL 说明

Render 已配置 `DATABASE_URL` 环境变量指向 PostgreSQL。后端启动时自动读取该变量连接 PostgreSQL。

- 本地未设置 `DATABASE_URL` → 默认 SQLite（`datahub.db`）
- Render 设置 `DATABASE_URL` → 使用 PostgreSQL

当前 Render Free Postgres 仅作为短期 P1-P4 打通测试使用，生产环境需升级到付费实例。

## 11. 新增测试

`backend/tests/test_manual_review_db_persistence.py`（16 个测试）：

1. 人工清洗保存后 manual_cleaning_records 表有数据
2. keep action 能保存
3. keep_edited action 能保存 cleaned_content
4. drop action 能保存并影响后续知识抽取
5. needs_review action 能保存并影响后续知识抽取
6. 知识抽取从 DB sanitized_messages 读取
7. 知识抽取能应用人工清洗后的 effective content
8. knowledge_candidates 表有数据
9. 重复抽取不无限重复生成 candidate
10. candidate 列表可以从 DB 读取
11. candidate 编辑能持久化
12. approve 写 review_records，并更新 candidate.status=approved
13. reject 写 review_records，并更新 candidate.status=rejected
14. needs_revision 写 review_records，并更新 candidate.status=needs_revision
15. 刷新式读取不依赖内存变量
16. /health 报告 P1-M18

## 12. 下一步 P1-M19

P1-M19 RAG / Agent / Bad Case DB Persistence：

- RAG build 写 `rag_chunks` 表
- CustomerOpsAgent 检索写 `retrieval_logs` 表
- Bad Case 写 `bad_cases` 表
- Bad Case draft candidate 入库
- 页面刷新后 RAG chunks、retrieval logs、Bad Case 列表仍在
