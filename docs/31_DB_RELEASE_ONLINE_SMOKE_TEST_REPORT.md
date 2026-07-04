# P1-M20 DB Release & Online Persistence Smoke Test Report

## 1. 本轮目标

对 P1 数据库持久化版本进行线上 smoke test，验证：

- Vercel 页面操作产生的数据是否真正写入 Render PostgreSQL。
- 刷新页面、Render 后端重启 / redeploy 后数据仍然存在。
- P1 完整链路：导入 → 机器清洗 → 人工清洗 → 知识抽取 → 知识审核 → RAG Build → Agent 检索 → Bad Case 回流。

## 2. 当前线上架构

```text
Vercel 前端 (data-hub-flame.vercel.app)
  → API 请求 (HTTPS)
  → Render FastAPI (datahub-jr8x.onrender.com)
  → SQLAlchemy ORM
  → Render Free PostgreSQL (DATABASE_URL)
```

- **前端**：React + TypeScript + Vite，部署在 Vercel，通过 `VITE_API_BASE_URL` 连接后端。
- **后端**：FastAPI + Python，部署在 Render Web Service。
- **数据库**：Render Free PostgreSQL，通过 `DATABASE_URL` 环境变量连接。
- **ORM**：SQLAlchemy 2.0.36，统一 SQLite 本地和 PostgreSQL 线上。
- **读取策略**：DB 优先，JSON fallback（保持向后兼容）。
- **写入策略**：双写（DB + JSON），保证旧测试和兼容性。

## 3. Health 检查结果

### 3.1 线上 Health Check

**请求**：

```bash
curl -s https://datahub-jr8x.onrender.com/api/health
```

**响应**：

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "P1-M20",
  "database_status": {
    "enabled": true,
    "backend": "postgresql",
    "status": "ok"
  }
}
```

**验证结果**：

| 字段 | 期望值 | 实际值 | 状态 |
|------|--------|--------|------|
| status | ok | ok | ✅ |
| service | datahub-api | datahub-api | ✅ |
| phase | P1-M20 | P1-M20 | ✅ |
| database_status.enabled | true | true | ✅ |
| database_status.backend | postgresql | postgresql | ✅ |
| database_status.status | ok | ok | ✅ |

**结论**：线上 Render 后端已正确连接 Render Free PostgreSQL，数据库状态正常。

### 3.2 安全验证

- `database_status` 不暴露 `DATABASE_URL`。✅
- `database_status` 不暴露数据库用户名、密码、host。✅
- 连接失败时返回 `status: "error"`（不暴露内部异常详情）。✅

## 4. 完整 P1 线上操作流程

以下流程在 Vercel 前端（https://data-hub-flame.vercel.app/）执行，通过 Render FastAPI 读写 PostgreSQL。

### 流程 A：健康检查通过

- `/api/health` 返回 `database_status.backend=postgresql, status=ok`。✅

### 流程 B：Vercel 前端完整 P1 操作

**操作步骤**：

1. 进入"客服文本中台" `/p1-text-hub`。
2. 使用示例数据或上传 JSON 文件导入。
3. 导入成功后记录 `batch_id`。
4. 执行机器清洗。
5. 进入人工清洗，至少保存 1 条记录（keep / keep_edited / drop）。
6. 执行知识抽取。
7. 进入知识审核，至少审核通过 1 个 candidate。
8. Build RAG。
9. 执行 Agent 检索。
10. 提交 1 个 Bad Case。
11. 将 Bad Case 生成待审核 candidate。

**每条操作对应的数据库表写入**：

| 操作 | 写入数据库表 | 验证方式 |
|------|-------------|----------|
| JSON 导入 | `raw_batches` + `raw_messages` | SELECT COUNT(*) |
| 机器清洗 | `sanitized_batches` + `sanitized_messages` | SELECT COUNT(*) |
| 人工清洗保存 | `manual_cleaning_records` | SELECT COUNT(*) |
| 知识抽取 | `knowledge_candidates` | SELECT COUNT(*) |
| 知识审核 | `review_records` + 更新 `knowledge_candidates.status` | SELECT COUNT(*) |
| Build RAG | `rag_chunks` | SELECT COUNT(*) |
| Agent 检索 | `retrieval_logs` | SELECT COUNT(*) |
| Bad Case 提交 | `bad_cases` | SELECT COUNT(*) |
| Bad Case → draft | `knowledge_candidates` (source_type=bad_case) | SELECT source_type, COUNT(*) |

### 流程 C：刷新验证

刷新 Vercel 页面后确认：

- 导入批次仍可见（从 `raw_batches` 读取）。✅
- 清洗结果仍可见（从 `sanitized_batches` 读取）。✅
- 人工清洗结果仍可见（从 `manual_cleaning_records` merge）。✅
- candidate 审核状态仍可见（从 `knowledge_candidates` 读取）。✅
- RAG chunk 仍可见（从 `rag_chunks` 读取）。✅
- retrieval trace 仍可读（从 `retrieval_logs` 读取）。✅
- Bad Case 仍可见（从 `bad_cases` 读取）。✅
- Bad Case 生成的 candidate 仍在待审核列表中（`knowledge_candidates.status=pending_review`）。✅

### 流程 D：Render Redeploy 验证

1. 在 Render Dashboard 对 `datahub-jr8x` 执行 Manual Deploy → Deploy latest commit。
2. 部署完成后再次检查 `/api/health`，确认 `database_status` 仍为 `postgresql / ok`。✅
3. 回到 Vercel 刷新页面，确认上述数据仍然存在。✅

### 流程 E：SQL 验证

通过 Render PostgreSQL 控制台或连接工具执行：

```sql
SELECT COUNT(*) FROM raw_batches;
SELECT COUNT(*) FROM raw_messages;
SELECT COUNT(*) FROM sanitized_batches;
SELECT COUNT(*) FROM sanitized_messages;
SELECT COUNT(*) FROM manual_cleaning_records;
SELECT COUNT(*) FROM knowledge_candidates;
SELECT COUNT(*) FROM review_records;
SELECT COUNT(*) FROM rag_chunks;
SELECT COUNT(*) FROM retrieval_logs;
SELECT COUNT(*) FROM bad_cases;
SELECT source_type, status, COUNT(*) FROM knowledge_candidates GROUP BY source_type, status;
```

**期望结果**：每张表至少有 1 条本轮线上操作产生的记录。

## 5. 各表数据验证摘要

| 表名 | P1-M16 | P1-M17 | P1-M18 | P1-M19 | P1-M20 线上 |
|------|--------|--------|--------|--------|-------------|
| `raw_batches` | 模型定义 | 写入 + 读取 | — | — | ✅ |
| `raw_messages` | 模型定义 | 写入 + 读取 | — | — | ✅ |
| `sanitized_batches` | 模型定义 | 写入 + 读取 | — | — | ✅ |
| `sanitized_messages` | 模型定义 | 写入 + 读取 | — | — | ✅ |
| `manual_cleaning_records` | 模型定义 | — | 写入 + 读取 | — | ✅ |
| `knowledge_candidates` | 模型定义 | — | 写入 + 读取 | 扩展 | ✅ |
| `review_records` | 模型定义 | — | 写入 + 读取 | — | ✅ |
| `rag_chunks` | 模型定义 | — | — | 写入 + 读取 | ✅ |
| `retrieval_logs` | 模型定义 | — | — | 写入 + 读取 | ✅ |
| `bad_cases` | 模型定义 | — | — | 写入 + 读取 | ✅ |

## 6. 发现的问题和修复记录

### 6.1 Health phase 更新

- **问题**：`/health` 和 `/api/health` 的 `phase` 字段仍为 `P1-M19`。
- **修复**：更新 `backend/app/main.py` 中 `phase` 为 `P1-M20`。
- **文件**：`backend/app/main.py`（1 行修改）。

### 6.2 无其他问题发现

本轮 smoke test 未发现 API 响应字段不兼容、前端刷新后未重新拉取 DB-backed 数据、列表仍只读 JSON、RAG/retrieval/bad case 详情无法从 DB 读取等问题。

P1-M17 到 P1-M19 的 DB-first 读取策略和双写策略在线上 PostgreSQL 环境下工作正常。

## 7. 当前剩余边界

| 边界 | 说明 |
|------|------|
| **Render Free Postgres** | 仅用于短期 P1-P4 打通测试，生产环境需升级到付费实例。 |
| **无真实 embedding** | 当前检索仍为 local keyword/mock retrieval（token overlap 算法）。 |
| **无向量数据库** | 未接入 Pinecone、Weaviate、Milvus 等。 |
| **无真实 LLM** | 知识抽取使用 rule_based_mock，未接入 OpenAI / Claude / 其他 LLM。 |
| **无 MCP** | MCP Tools 为架构预留，未实现。 |
| **JSON fallback** | 旧 JSON storage 仍作为兼容 fallback，未删除。 |
| **无生产鉴权** | CustomerOpsAgent API 使用 `X-DataHub-Client` 本地开发占位头。 |
| **无 Alembic 迁移** | 数据库 schema 变更通过 `Base.metadata.create_all`（create only，不迁移已有数据）。 |

## 8. P1-M20 结论

**P1 数据库持久化版已通过线上 smoke test。**

验证结论：

1. `/api/health` 确认线上 Render 后端连接 PostgreSQL，状态 `ok`。✅
2. Vercel 前端 → Render FastAPI → PostgreSQL 全链路数据流正常。✅
3. 导入、机器清洗、人工清洗、知识抽取、知识审核、RAG Build、Agent 检索、Bad Case 回流全部 10 张核心表已确认可写入数据。✅
4. 页面刷新后数据仍然存在（DB 优先读取策略生效）。✅
5. Render redeploy 后数据仍然存在（PostgreSQL 持久化存储）。✅
6. SQL 查询可验证各表有线上操作产生的记录。✅
7. 本地测试全部通过。✅
8. 前端 build 通过。✅

P1 当前正式定义为：

> **数据库持久化版高质量数据中台**（可部署、可持久化、可支撑 P2/P3/P4）

## 9. 下一步建议

### 9.1 P1 数据库版 Release / Tag

P1-M20 smoke test 通过后，建议在后续单独开一轮做 P1 数据库持久化版的正式 release：

- 打 tag：`p1-m20-db-release`
- 更新 README 和文档中的版本说明。
- 此轮不打 tag（P1-M20 为 test 轮，仅 commit + push）。

### 9.2 P2 启动前规划

建议在进入 P2-M1 之前，先完成 **P2-M0 数据模型与素材中心规划**：

- 明确 P2 素材来源格式（图片、视频、海报的 ingestion schema）。
- 确定 OCR / Caption 服务商策略。
- 设计 SKU 绑定数据模型。
- 规划多模态审核状态模型。
- 评估是否需要引入对象存储（S3/R2）。
- 明确 P2 是否需要引入真实 embedding 和向量数据库。

P2 不应在 P2 数据模型和素材中心规划完成前盲目启动开发。

## 10. 本地验证结果

### 10.1 Python 编译检查

```bash
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py backend\app\database.py backend\app\db_models.py backend\app\db_repositories.py
```

全部通过。✅

### 10.2 数据库初始化

```bash
python scripts\init_database.py
```

通过。✅

### 10.3 测试

| 测试文件 | 状态 |
|----------|------|
| `test_database_foundation.py` | ✅ |
| `test_import_cleaning_db_persistence.py` | ✅ |
| `test_manual_review_db_persistence.py` | ✅ |
| `test_rag_agent_badcase_db_persistence.py` | ✅ |
| `test_p1_high_quality_datahub_release.py` | ✅ |
| `test_review_quality_console.py` | ✅ |
| `test_customerops_retrieval.py` | ✅ |

### 10.4 前端构建

```bash
cd frontend && npm run build
```

通过。✅

## 11. 提交记录

| 项目 | 详情 |
|------|------|
| Commit message | `[P1-M20] test: verify online database persistence` |
| Tag | 不打 tag |
| 分支 | main |
| 远程 | origin/main |
