# P1-M17 Import & Cleaning DB Persistence Report

## 1. 本轮目标

将"导入客服 JSON"和"机器清洗结果"迁移为数据库持久化，使数据在 Render 重启或重新部署后依然保留。

## 2. 迁移的 API

| API 路径 | 变更 |
|----------|------|
| `POST /api/sources/import-json` | 导入时双写 DB（raw_batches + raw_messages）+ JSON |
| `GET /api/sources` | 批次列表 DB 优先，回退 JSON |
| `GET /api/sources/{batch_id}` | 批次详情 DB 优先，回退 JSON |
| `POST /api/cleaning/run/{batch_id}` | 清洗时优先从 DB 读取 raw data，结果双写 DB + JSON |
| `GET /api/sanitized/{batch_id}` | 清洗结果 DB 优先，回退 JSON |

API path、request/response contract 均保持不变。前端无需修改。

## 3. 写入的数据库表

| 操作 | 写入表 |
|------|--------|
| 导入客服 JSON | `raw_batches`（批次元信息 + raw_payload） |
| 导入客服 JSON | `raw_messages`（每条消息一行，batch_id 索引） |
| 机器清洗 | `sanitized_batches`（清洗摘要 + metadata_json 补充指标） |
| 机器清洗 | `sanitized_messages`（每条清洗消息，含质量字段） |

## 4. 清洗消息写入的字段

每条 `sanitized_messages` 记录包含：

- `role` — 角色（customer / agent / system）
- `content` — 脱敏后内容
- `sanitized_content` — 脱敏内容
- `quality_score` — 质量评分（0.0 - 1.0）
- `quality_level` — 质量等级（high / medium / low）
- `suggested_action` — 建议操作（keep / review / drop）
- `cleaning_issues` — 清洗问题列表（JSON）
- `risk_flags` — 风险标记列表（JSON）
- `pii_entities` — PII 类型列表（JSON）

## 5. 清洗摘要写入的字段

`sanitized_batches` 表核心列：

- `message_count` — 清洗后消息数
- `high_quality_count` — 高质量消息数
- `review_recommended_count` — 建议人工复核数
- `drop_recommended_count` — 建议丢弃数
- `average_quality_score` — 平均质量分

补充指标存储在 `metadata_json`：

- `raw_message_count`、`dropped_message_count`、`pii_detected_count`
- `exact_duplicate_count`、`near_duplicate_count`
- `low_quality_count`、`noise_count`

## 6. 尚未迁移的链路

以下链路仍使用 JSON storage，将在 P1-M18 / P1-M19 逐步迁移：

- 人工清洗（`PATCH /api/sanitized/{batch_id}/messages/{message_id}/manual-clean`）
- 知识抽取（`POST /api/extraction/run/{batch_id}`）
- 知识审核（`POST /api/review/{candidate_id}/approve` 等）
- RAG 构建与检索（`POST /api/rag/build`、`POST /api/rag/search`）
- CustomerOpsAgent 检索（`POST /api/customer-ops-agent/retrieve`）
- Bad Case 反馈（`POST /api/customer-ops-agent/bad-cases` 等）
- Legacy RAG 导入

## 7. 数据读取策略

**DB 优先，JSON 回退：**

- 读取时先查询数据库，有数据则直接返回。
- 数据库无数据或查询失败时，回退到 JSON storage。
- 写入时双写（DB + JSON），保证旧测试和兼容性。

## 8. 幂等策略

- 重复导入同一个 `batch_id`：更新 `raw_batches` 行，删除旧 `raw_messages`，重写新消息。
- 重复清洗同一个 `batch_id`：更新 `sanitized_batches` 行，删除旧 `sanitized_messages`，重写新消息。
- `Base.metadata.create_all` 是幂等的，不会删除已有数据。

## 9. 本地 SQLite 验证方式

```bash
# 初始化数据库
python scripts/init_database.py

# 启动后端
cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 导入数据（通过前端或 API）
# 查询验证
sqlite3 datahub.db "SELECT COUNT(*) FROM raw_batches;"
sqlite3 datahub.db "SELECT COUNT(*) FROM raw_messages;"
sqlite3 datahub.db "SELECT COUNT(*) FROM sanitized_batches;"
sqlite3 datahub.db "SELECT COUNT(*) FROM sanitized_messages;"
```

## 10. Render PostgreSQL DATABASE_URL 说明

Render 已配置 `DATABASE_URL` 环境变量指向 PostgreSQL。后端启动时自动读取该变量连接 PostgreSQL。

- 本地未设置 `DATABASE_URL` → 默认 SQLite（`datahub.db`）
- Render 设置 `DATABASE_URL` → 使用 PostgreSQL

当前 Render Free Postgres 仅作为短期 P1-P4 打通测试使用，生产环境需升级到付费实例。

## 11. 下一步 P1-M18

P1-M18 Manual Cleaning & Review DB Persistence：

- 人工清洗写 `manual_cleaning_records` 表
- 知识抽取从数据库读取人工清洗后的数据
- candidate 写 `knowledge_candidates` 表
- 审核动作写 `review_records` 表
- candidate 状态持久化
