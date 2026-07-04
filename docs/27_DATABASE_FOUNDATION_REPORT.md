# P1-M16 Database Foundation Report

## 1. 本轮目标

为 DataHub 建立数据库底座，引入 SQLAlchemy ORM，支持 SQLite 本地开发和 PostgreSQL 生产部署，但不迁移任何现有业务 API。

## 2. 新增数据库文件

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | SQLAlchemy engine、SessionLocal、Base、get_db dependency、check_database_connection() |
| `backend/app/db_models.py` | 10 张核心表 SQLAlchemy 模型定义 |
| `scripts/init_database.py` | 数据库初始化脚本（Base.metadata.create_all） |
| `backend/tests/test_database_foundation.py` | 数据库底座测试（SQLite 内存数据库） |

## 3. 核心表模型

| 表名 | 说明 |
|------|------|
| `raw_batches` | 导入批次元信息 |
| `raw_messages` | 原始消息 |
| `sanitized_batches` | 机器清洗批次元信息 |
| `sanitized_messages` | 脱敏及质量评分后的消息 |
| `manual_cleaning_records` | 人工清洗记录 |
| `knowledge_candidates` | 知识候选 |
| `review_records` | 审核记录 |
| `rag_chunks` | RAG 知识块 |
| `retrieval_logs` | Agent 检索日志 |
| `bad_cases` | Bad Case 反馈 |

所有模型使用 String 主键 + string index（非外键），兼容 SQLite 和 PostgreSQL。JSON 字段统一使用 `sa.JSON`。

## 4. DATABASE_URL 规则

- 设置 `DATABASE_URL` 环境变量 → 使用该连接串。
- 未设置 `DATABASE_URL` → 默认 SQLite `sqlite:///./datahub.db`。
- PostgreSQL 连接串格式：`postgresql://user:password@host:port/dbname`。
- `DATABASE_URL` 只在后端环境变量中配置，不暴露给前端。

## 5. SQLite 本地默认

本地开发无需任何配置：

```bash
python scripts/init_database.py
```

脚本自动在项目根目录创建 `datahub.db`。该文件已在 `.gitignore` 中排除。

## 6. PostgreSQL 线上配置方式

在 Render 或其他平台上设置环境变量：

```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

后端启动时自动读取该变量连接 PostgreSQL。

## 7. health check database_status 设计

`/health` 和 `/api/health` 新增 `database_status` 字段：

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "P1-M16",
  "database_status": {
    "enabled": true,
    "status": "ok",
    "backend": "sqlite"
  }
}
```

安全设计：

- 不暴露 DATABASE_URL。
- 不暴露数据库用户名。
- 不暴露数据库密码。
- 不暴露数据库 host。
- 数据库连接失败时返回 `status: "error"`（不返回数据库内部异常详情）。

## 8. 当前未迁移业务 API 的边界

本轮仅建立数据库底座。以下 API 仍使用 local JSON storage：

- JSON 导入 API（`POST /api/sources/import-json`）
- 机器清洗 API（`POST /api/cleaning/run/{batch_id}`）
- 人工清洗 API（`PATCH /api/sanitized/{batch_id}/messages/{message_id}/manual-clean`）
- 知识抽取 API（`POST /api/extraction/run/{batch_id}`）
- 知识审核 API（`POST /api/review/{candidate_id}/approve` 等）
- RAG 构建与检索 API（`POST /api/rag/build`、`POST /api/rag/search`）
- CustomerOpsAgent 检索 API（`POST /api/customer-ops-agent/retrieve`）
- Bad Case API（`POST /api/customer-ops-agent/bad-cases` 等）

现有 JSON demo 链路完整保留，不删除、不降级。

## 9. 下一步 P1-M17

P1-M17 Import & Cleaning DB Persistence：

- 导入 JSON 写 `raw_batches` / `raw_messages` 表。
- 机器清洗写 `sanitized_batches` / `sanitized_messages` 表。
- 批次列表从数据库读取。
- 保留 JSON fixture 作为测试样本。
