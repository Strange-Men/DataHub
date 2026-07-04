# DataHub P1 Database Persistence Roadmap

## 1. 背景

P1 高质量文本数据中台已完成以下核心能力：

- 客服数据 JSON 导入
- 机器清洗（脱敏、去重、质量评分）
- 人工清洗（内容修正、保留/丢弃/复核决策）
- 知识候选抽取（FAQ、标准回答、业务规则、禁答规则）
- 人工知识审核（通过、驳回、打回）
- 统一 RAG 知识块构建
- CustomerOpsAgent 受限检索
- Bad Case 回流并生成待审核 draft
- Legacy RAG 迁移
- 公开数据集小样本评测
- Vercel 前端 + Render 后端在线 Demo

但当前存储层仍然是 **local JSON storage**（`backend/storage/*.json`）。

这意味着：

- Render 免费实例重启后，所有运行时数据丢失。
- Render 重新部署后，所有运行时数据丢失。
- 无法支撑线上长期持久化需求。
- 导入、清洗、人工清洗、知识审核、RAG 构建等操作结果不适合长期保存在 Render 本地文件系统中。

当前 P1 状态定义：

> **local JSON demo 版高质量数据中台**

数据库补强后的目标状态定义：

> **数据库持久化版高质量数据中台**

---

## 2. 为什么数据库必须属于 P1

P1 不能直接进入 P2。原因：

### 2.1 P2 AI 素材中心依赖 P1 数据底座

P2 需要读取和扩展 P1 已审核的知识资产、标签、SKU、素材审核状态。如果 P1 仍停留在 local JSON storage，P2 没有可靠的数据底座可以依赖。

### 2.2 P3 数据资产复用依赖 P1 数据底座

P3 需要查询已审核的 FAQ、业务规则、Bad Case、优质问答来生成培训资料、SOP 手册、微调数据集。如果 P1 数据不能持久化，P3 无法稳定读取高质量数据。

### 2.3 P4 MCP + Agent 集群依赖 P1 数据底座

P4 需要通过 MCP 稳定暴露统一知识资产供 Agent 集群调用。如果数据只在 Render 本地文件中短暂存在，MCP 工具无法提供可靠的知识检索。

### 2.4 结论

数据库持久化不是 P2 的任务，而是 **P1 数据中台底座建设的必要补强**。没有数据库持久化的 P1 无法作为 P2/P3/P4 的可靠依赖。

---

## 3. 目标

最终目标：用户在 Vercel 页面完成以下任意操作后，数据可以持久保存在数据库中：

- 导入客服数据 → `raw_batches` / `raw_messages` 表有记录
- 执行机器清洗 → `sanitized_batches` / `sanitized_messages` 表有记录
- 保存人工清洗结果 → `manual_cleaning_records` 表有记录
- 抽取候选知识 → `knowledge_candidates` 表有记录
- 完成人工知识审核 → `review_records` 表有记录
- 构建 RAG 知识块 → `rag_chunks` 表有记录
- 执行 Agent 检索 → `retrieval_logs` 表有记录
- 提交 Bad Case → `bad_cases` 表有记录

并且需要满足：

- **页面刷新后**数据还在
- **Render 后端重启后**数据还在
- **Render 重新部署后**数据还在
- **数据库控制台**可以 SELECT 查询到对应记录

---

## 4. 技术选型

### 4.1 推荐技术栈

```
SQLAlchemy + SQLite（本地默认）+ PostgreSQL（生产可选）
```

### 4.2 设计要点

| 要点 | 说明 |
|------|------|
| **SQLAlchemy ORM** | 统一 ORM 层，避免后续从 SQLite 迁移 PostgreSQL 时大改业务代码 |
| **SQLite 本地默认** | 用于本地开发、测试、轻量 demo；连接串 `sqlite:///./datahub.db` |
| **PostgreSQL 生产** | 用于线上持久化部署；通过 `DATABASE_URL` 环境变量连接 |
| **DATABASE_URL** | 统一数据库连接配置入口 |
| **DB session / repository layer** | 提供数据库会话管理和数据访问抽象层 |
| **保留 JSON storage** | 保留现有 JSON storage 代码作为迁移参考或测试 fixture，但不再作为线上持久化核心 |

### 4.3 数据流

```text
Vercel 前端（不存数据）
  → 用户操作触发 API 请求
  → Render 后端 FastAPI
  → SQLAlchemy session
  → SQLite（本地）或 PostgreSQL（线上）
  → 数据持久化到数据库
```

### 4.4 重要提示

- **只在 Render 配置 `DATABASE_URL` 不够**：后端代码必须从 local JSON storage 改成 DB-backed API，页面操作产生的数据才会真正入库。
- **Vercel 前端不存数据**：前端只通过 API 调用 Render FastAPI，不直接连接数据库。
- **前端不能暴露数据库连接字符串**：`DATABASE_URL` 只在 Render 后端环境变量中配置。

---

## 5. 核心数据表规划

| 表名 | 说明 |
|------|------|
| `raw_batches` | 保存一次导入任务的元信息（source_name、message_count、conversation_count、status、created_at） |
| `raw_messages` | 保存导入批次中的原始消息（batch_id、conversation_id、role、content、PII 字段） |
| `sanitized_batches` | 保存一次机器清洗任务的元信息（source_batch_id、cleaning_job_id、summary metrics） |
| `sanitized_messages` | 保存脱敏和质量评分后的消息（batch_id、content、pii_detected、pii_types、quality_score、quality_level、suggested_action、cleaning_issues、risk_flags） |
| `manual_cleaning_records` | 保存人工清洗员的操作、修改内容、备注（message_id、cleaner、manual_action、content_before、content_after、cleaning_note） |
| `knowledge_candidates` | 保存抽取出的 FAQ、标准回答、业务规则、禁答规则等候选知识（source_batch_id、question、answer、knowledge_type、intent、tags、risk_level、review_status、quality_score、extraction_method） |
| `review_records` | 保存审核员的通过、驳回、打回记录（candidate_id、reviewer、decision、review_note、reviewed_at） |
| `rag_chunks` | 保存 approved candidate 构建后的 RAG 知识块（candidate_id、chunk_text、build_method、created_at） |
| `retrieval_logs` | 保存 CustomerOpsAgent 检索记录（query、top_k、result_count、result_chunk_ids、retrieval_mode） |
| `bad_cases` | 保存用户提交的坏例和修正建议（retrieval_id、user_query、agent_answer、issue_type、expected_answer、severity、status、linked_candidate_id） |

---

## 6. 后续版本规划

### P1-M16：Database Foundation ✅ (已完成 2026-07-04)

**目标**：建立数据库底座，不大改业务。

**范围**：

- 新增 `backend/app/database.py`（数据库连接、session 管理、DATABASE_URL 读取）
- 新增 `backend/app/db_models.py`（SQLAlchemy 模型定义，10 张核心表）
- 支持 `DATABASE_URL` 环境变量
- 本地默认 SQLite（`sqlite:///./datahub.db`）
- 线上支持 PostgreSQL（通过 `DATABASE_URL` 切换）
- 新增数据库初始化脚本 `scripts/init_database.py`（create_all tables）
- 新增数据库测试 `backend/tests/test_database_foundation.py`
- `/health` 增加 `database_status` 字段（safe, no URL/password leak）
- **不迁移任何现有 API**

**实际落地**：

- 数据库文件：`backend/app/database.py`、`backend/app/db_models.py`
- 初始化脚本：`scripts/init_database.py`
- 测试文件：`backend/tests/test_database_foundation.py`
- 依赖新增：`sqlalchemy==2.0.36`、`psycopg2-binary==2.9.10`
- health 新增字段：`database_status: { enabled, status, backend }`
- database_status 不暴露 DATABASE_URL、用户名、密码、host
- 本地 SQLite 路径为项目根目录 `datahub.db`（已加入 .gitignore）

**验收**：

- [x] 本地可以初始化 SQLite 数据库
- [x] DATABASE_URL 机制已预留 PostgreSQL 支持
- [x] `/health` 返回 `database_status`（status: "ok" | "error"，backend: "sqlite" | "postgresql"）
- [x] 不破坏现有 P1 JSON demo 链路
- [x] 现有测试全部通过（phase 更新至 P1-M16）

---

### P1-M17：Import & Cleaning DB Persistence ✅ (已完成 2026-07-04)

**目标**：导入和机器清洗结果真正入库。

**范围**：

- 导入 JSON 写 `raw_batches` / `raw_messages` 表
- 机器清洗写 `sanitized_batches` / `sanitized_messages` 表
- 批次列表从数据库读取（而非 JSON 文件）
- 前端刷新后批次仍可见
- 保留 JSON fixture 作为测试样本

**实际落地**：

- 新增文件：`backend/app/db_repositories.py`（数据访问层）
- 新增测试：`backend/tests/test_import_cleaning_db_persistence.py`
- 修改 `database.py`：新增 `init_database_tables()`，FastAPI startup 自动调用
- 修改 `storage.py`：`create_raw_batch`、`list_raw_batches`、`get_raw_batch_metadata`、`get_raw_batch_document`、`run_cleaning`、`get_sanitized_batch` 全部改为 DB-first + JSON fallback
- 修改 `main.py`：startup event 自动建表，phase 更新至 P1-M17
- `raw_batches` 存储导入元信息 + raw_payload（用于重构完整文档）
- `raw_messages` 存储每条原始消息（batch_id 索引）
- `sanitized_batches` 存储清洗摘要指标 + metadata_json（补充指标）
- `sanitized_messages` 存储每条清洗消息（含 quality_score、quality_level、suggested_action、cleaning_issues、risk_flags、pii_entities）
- 写入策略：双写（DB + JSON），读取策略：DB 优先（DB 有数据则返回 DB，否则 fallback JSON）
- 幂等策略：重复导入/清洗同一 batch_id 时删除旧 messages 再重写
- 未迁移：人工清洗、知识审核、RAG、Agent 检索、Bad Case（留到 P1-M18/P1-M19）

**验收**：

- [x] Vercel 上传 JSON → Render 后端写数据库
- [x] 刷新页面后批次数据仍在
- [x] 数据库可 SELECT 查到 raw/sanitized 数据
- [x] 现有测试通过（含 JSON fixture 兼容）

---

### P1-M18：Manual Cleaning & Review DB Persistence ✅ (已完成 2026-07-05)

**目标**：人工清洗和知识审核真正保存。

**范围**：

- 人工清洗写 `manual_cleaning_records` 表
- 修改后内容持久化到 `sanitized_messages`
- 知识抽取从数据库读取人工清洗后的数据（而非 JSON 文件）
- candidate 写 `knowledge_candidates` 表
- 审核动作（approve/reject/needs_revision）写 `review_records` 表
- candidate 状态（review_status）持久化

**实际落地**：

- 新增 repository 函数（10 个）：save/get manual cleaning records, save/list/get/update knowledge candidates, save review records
- manual_cleaning_records 表：保存 sanitized_message_id, cleaner, action, original_content, cleaned_content, note
- knowledge_candidates 表：保存所有候选知识字段（含 source_type, question, answer, intent, tags, risk_level, quality_score, status, metadata_json）
- review_records 表：保存 candidate_id, reviewer, action, note, snapshot_json
- 写入策略：双写（DB + JSON），读取策略：DB 优先 merge JSON fallback
- 幂等策略：
  - 人工清洗：同 sanitized_message_id 允许多条记录，最新为 effective record
  - 知识抽取：按 source_id + question + answer 去重，重复抽取替换而非追加
  - 审核：每次审核新增 review_records，同时更新 knowledge_candidates.status
- get_sanitized_batch：从 DB 读取时自动 merge manual_cleaning_records
- 新增测试：16 个测试覆盖人工清洗、知识抽取、审核持久化全链路
- 未迁移：RAG、Agent 检索、Bad Case（留到 P1-M19）

**验收**：

- [x] 人工清洗保存后刷新页面仍在
- [x] 审核通过后刷新页面仍为 approved
- [x] Render 重启后记录仍在
- [x] 数据库可查 `manual_cleaning_records` / `knowledge_candidates` / `review_records`

---

### P1-M19：RAG / Agent / Bad Case DB Persistence ✅ (已完成 2026-07-05)

**目标**：RAG、Agent 检索、Bad Case 回流全部数据库化。

**范围**：

- approved candidate 构建 `rag_chunks` 表记录
- CustomerOpsAgent 检索写 `retrieval_logs` 表
- Bad Case 写 `bad_cases` 表
- Bad Case 生成 candidate 草稿并入库
- RAG 页面刷新后仍可看到构建结果

**实际落地**：

- 新增 repository 函数（11 个）：save/list/get RAG chunks, save/get/list retrieval logs, save/get/list/update bad cases, create candidate from bad case
- RAG build 双写 DB（rag_chunks 表）+ JSON
- RAG 只使用 approved 候选；pending_review / rejected / needs_revision 不进入 RAG
- 重复 Build RAG 幂等：替换全部 rag_chunks 行，不无限追加
- Agent 检索优先从 DB 读取 rag_chunks，写 retrieval_logs
- retrieval_logs 保存 query、matched_chunk_ids、response_preview、metadata_json
- Bad Case 提交双写 DB（bad_cases 表）+ JSON
- Bad Case → create-draft 双写 knowledge_candidates（source_type=bad_case, status=pending_review）
- Bad Case candidate 按 source_id + question + answer 去重
- bad_cases.created_candidate_id 关联生成的 candidate
- 读取策略：DB 优先，JSON fallback（保留所有旧 JSON 写入）
- 新增测试：16 个测试覆盖 RAG 持久化、Agent 检索持久化、Bad Case 持久化全链路
- 未迁移：P2/P3/P4 后端功能

**验收**：

- [x] Build RAG 后 `rag_chunks` 表有数据
- [x] Agent 查询后 `retrieval_logs` 表有数据
- [x] Bad Case 提交后 `bad_cases` 表有数据
- [x] Bad Case draft candidate 可进入审核链路
- [x] 页面刷新后 RAG chunks、retrieval logs、Bad Case 列表仍在

---

### P1-M20：DB Release & Online Persistence Smoke Test

**目标**：数据库版 P1 最终验收。

**范围**：

- 完整线上 Smoke Test
- Vercel 页面全流程测试（导入 → 清洗 → 人工清洗 → 审核 → RAG → 检索 → Bad Case）
- Render 后端重启后复测（确认数据仍在）
- 数据库控制台 SELECT 验证（确认所有表有对应记录）
- README / 部署文档更新（本地 SQLite 与线上 PostgreSQL 配置说明）
- 输出数据库版 P1 最终验收报告（`docs/27_DB_RELEASE_REPORT.md`）

**验收**：

- [ ] 页面操作产生的数据能入库
- [ ] 页面刷新后仍在
- [ ] Render 重新部署后仍在
- [ ] P1 全链路仍能跑通
- [ ] 文档清楚说明本地 SQLite 与线上 PostgreSQL 的配置方式

---

## 7. 不做什么

P1-M16 到 P1-M20 期间严格禁止：

- 不进入 P2 后端开发
- 不做真实多模态
- 不做销售培训导出真实实现
- 不做微调数据集真实导出
- 不做 MCP 真实实现
- 不接真实 LLM
- 不接 embedding
- 不接向量数据库
- 不修改 CustomerOpsAgent 仓库
- 不做面试包装
- 不做简历包装
- 不提交 API Key
- 不提交真实客服数据
- 不提交 `backend/storage/`、`.env`、`.venv`、`node_modules`、`frontend/dist`

---

## 8. 风险与边界

| 风险 / 边界 | 说明 |
|-------------|------|
| Render 本地文件不持久 | Render Web Service 免费实例的本地文件系统不适合作为长期持久化核心 |
| SQLite 本地定位 | SQLite 适合本地开发、测试、轻量 demo，不建议作为线上长期数据源 |
| PostgreSQL 线上推荐 | PostgreSQL 是线上持久化推荐方案 |
| 数据库连接信息管理 | `DATABASE_URL` 必须通过 Render 环境变量管理，不能硬编码 |
| 前端不能暴露数据库连接串 | 前端只能通过 FastAPI API 访问数据，不能直接连接数据库 |
| 数据库迁移 | SQLite → PostgreSQL 迁移通过 SQLAlchemy ORM 和 `DATABASE_URL` 切换实现，不引入 Alembic 等额外迁移工具（除非必要） |

---

## 9. 完成后的 P1 定义

P1-M20 完成后，P1 才能正式定义为：

> **可部署、可持久化、可支撑 P2/P3/P4 的高质量数据中台底座**

在此之前，P1 仍然是 **local JSON demo 版高质量数据中台**，可以在本地和 Render 演示完整治理流程，但不能保证线上数据持久性。
