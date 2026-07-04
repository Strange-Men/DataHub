# DataHub｜面向 Agent 集群的多源数据治理与 RAG 知识中台

English version: [README.en.md](./README.en.md)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![React](https://img.shields.io/badge/React-Frontend-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-UI-3178C6)
![RAG](https://img.shields.io/badge/RAG-local%20mock-orange)
![pytest](https://img.shields.io/badge/pytest-optional-lightgrey)
![Data Governance](https://img.shields.io/badge/Data%20Governance-P1%20complete-brightgreen)
![Agent-ready](https://img.shields.io/badge/Agent--ready-CustomerOpsAgent-brightgreen)

DataHub 是一个面向 AI Agent 集群的数据资产中心。它把客服聊天记录、公开客服数据小样本、Bad Case 修正草稿、CustomerOpsAgent legacy RAG 迁移数据统一治理成 knowledge candidates，经人工审核后构建为本地 RAG chunks，并通过受限检索 API 提供给 CustomerOpsAgent。

当前仓库已完成 **P1-M11 Unified DataHub RAG Release**。P1 已收版，但仍然是本地 JSON + keyword/mock retrieval，不是生产级向量数据库方案。

## 快速上手

后端：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

期望：

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "P1-M11"
}
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

默认地址：

```text
http://localhost:5173
```

## STAR 项目拆解

### Situation

AI 客服和 Agent 项目经常面临知识资产分散、客服数据噪声高、隐私风险难控、RAG 知识难持续更新的问题。CustomerOpsAgent 需要稳定、可追溯、可回流的知识来源，而不是直接维护一套孤立知识库。

### Task

构建一个面向 Agent 集群的数据治理与统一 RAG 知识中台：

- 将原始客服聊天记录转成可审核的知识候选。
- 保证未脱敏、未审核数据不能进入检索。
- 为 CustomerOpsAgent 提供只读、受限、可追溯的检索接口。
- 支持 Bad Case 回流并重新进入候选知识流程。
- 将 CustomerOpsAgent legacy RAG 知识迁移进 DataHub，形成统一 RAG 入口。

### Action

P1 已完成：

- JSON 客服聊天记录导入。
- 清洗、基础脱敏、空内容过滤、角色标准化。
- rule-based mock 知识候选抽取。
- 人工审核、编辑、approve / reject / needs_revision。
- approved candidates 构建本地 RAG chunks。
- 本地 RAG build 幂等保护。
- CustomerOpsAgent restricted retrieval API。
- retrieval_id 和 retrieval trace。
- Bad Case 提交、队列、人工处理状态。
- Bad Case 转 `pending_review` candidate。
- 公开客服数据集小样本评测。
- CustomerOpsAgent legacy RAG export 导入。
- 统一 DataHub RAG release 测试。

### Result

已验证指标：

- Public dataset sample：50 conversations / 100 messages。
- Public dataset evaluation：`candidate_count: 50`。
- Controlled approval：`approved_count: 10`。
- Local RAG build：`rag_chunk_count: 10`。
- Retrieval evaluation：`retrieval_hit_count: 5`。
- Bad Case loop：`bad_case_to_draft_count: 1`。
- P1 core flow test passed。
- Public dataset eval test passed。
- Legacy RAG migration test passed。
- Unified RAG release test passed。

这些结果证明 P1 数据治理与回流链路可跑通；它们不代表生产级语义检索质量。

## 为什么它不是普通 RAG Demo

DataHub 的重点不是“把文本丢进向量库搜索”，而是治理闭环：

```text
raw data
-> sanitized data
-> knowledge candidates
-> human review
-> approved candidates
-> local RAG chunks
-> CustomerOpsAgent retrieval
-> Bad Case feedback
-> pending_review draft
```

硬边界：

- raw data 不进入 extraction / RAG / CustomerOpsAgent retrieval。
- sanitized data 不能直接进入 RAG。
- `pending_review` / `needs_revision` / `rejected` 不能进入 RAG。
- Bad Case 不能直接修改 candidate 或 RAG chunk。
- CustomerOpsAgent 只能通过 DataHub API 检索，不能直接改知识库。

## 技术架构与工作流

```text
React + TypeScript Admin UI
    |
    v
FastAPI + Python API
    |
    +--> JSON Import
    +--> Cleaning & Sanitization
    +--> Knowledge Extraction
    +--> Human Review
    +--> Local RAG Builder
    +--> CustomerOpsAgent Retrieval
    +--> Bad Case Feedback
    +--> Legacy RAG Migration
    |
    v
Local JSON Storage under backend/storage/  (Git ignored)
```

P1-M11 统一 RAG 来源：

```text
chat_logs
public_dataset
bad_case
legacy_rag
manual (reserved)
```

当前真实实现覆盖：

- `chat_logs`：客服聊天记录主链路。
- `public_dataset`：P1-M9.5 公开客服数据小样本评测。
- `bad_case`：M8.5 Bad Case 转 pending-review draft，审核后可入 RAG。
- `legacy_rag`：P1-M10 legacy RAG migration。

## 技术栈

已确定：

- Frontend：React + TypeScript。
- Backend：FastAPI + Python。
- Test style：Python `unittest` scripts + FastAPI `TestClient`。
- Current storage：local JSON files under `backend/storage/`。
- Current retrieval：local keyword/mock retrieval。

仍保持候选，不在 P1 拍死：

- Database：SQLite / PostgreSQL。
- Vector store：pgvector / Qdrant。
- ORM：SQLAlchemy / SQLModel。
- RAG orchestration：lightweight service / LangChain / LlamaIndex。
- Background tasks：FastAPI BackgroundTasks / Celery / RQ。
- Deployment：local Docker Compose / later cloud deployment。

## P1 核心能力

### M2 JSON Import

```text
POST /api/sources/import-json
GET  /api/sources
GET  /api/sources/{batch_id}
```

### M3 Cleaning / Sanitization

```text
POST /api/cleaning/run/{batch_id}
GET  /api/cleaning/jobs/{job_id}
GET  /api/sanitized/{batch_id}
```

支持 masking：

- Email -> `[EMAIL]`
- Phone -> `[PHONE]`
- Order id -> `[ORDER_ID]`
- Tracking id -> `[TRACKING_ID]`
- Address-like text -> `[ADDRESS]`

### M4 Knowledge Candidate Extraction

```text
POST /api/extraction/run/{batch_id}
GET  /api/extraction/jobs/{job_id}
GET  /api/knowledge/candidates
GET  /api/knowledge/candidates/{candidate_id}
```

当前方法：

```text
rule_based_mock
```

### M5 Human Review

```text
GET   /api/review/pending
PATCH /api/knowledge/candidates/{candidate_id}
POST  /api/review/{candidate_id}/approve
POST  /api/review/{candidate_id}/reject
POST  /api/review/{candidate_id}/needs-revision
```

### M6 / M6.5 Local RAG

```text
POST /api/rag/build
GET  /api/rag/chunks
GET  /api/rag/chunks/{chunk_id}
POST /api/rag/search
```

说明：

- 只读取 approved candidates。
- 重复 build 不重复生成 chunks。
- `chunk_id` 稳定派生自 `candidate_id`。
- search 返回 `score`、`matched_terms` 和 source trace。

### M7 / M7.5 CustomerOpsAgent Retrieval

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
```

必须带 header：

```text
X-DataHub-Client: CustomerOpsAgent
```

该 header 是本地开发阶段鉴权占位，不是生产 token。

### M8 Bad Case Feedback

```text
POST  /api/customer-ops-agent/bad-cases
GET   /api/bad-cases
GET   /api/bad-cases/{bad_case_id}
PATCH /api/bad-cases/{bad_case_id}
```

### M8.5 Bad Case To Draft

```text
POST /api/bad-cases/{bad_case_id}/create-draft
```

生成 candidate 必须是：

```text
review_status: pending_review
source_type: bad_case
extraction_method: bad_case_resolution
```

### P1-M10 Legacy RAG Migration

```text
POST /api/legacy-rag/import
GET  /api/legacy-rag/imports
GET  /api/legacy-rag/imports/{import_id}
```

`trusted_import=true`：

```text
legacy item -> approved candidate
```

`trusted_import=false`：

```text
legacy item -> pending_review candidate
```

## 统一 RAG 与 CustomerOpsAgent 接入

P1-M11 后，CustomerOpsAgent 后续推荐只调用 DataHub：

```text
CustomerOpsAgent receives user query
-> POST /api/customer-ops-agent/retrieve
-> use returned answer / chunks / source trace
-> generate final customer-facing response
-> if answer is bad, submit Bad Case with retrieval_id
```

CustomerOpsAgent 不需要知道知识来自：

- chat logs
- public dataset sample
- bad case draft
- legacy RAG import

DataHub 在结果里保留 source trace，用于排查、审核和 Bad Case 回流。

调用示例：

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

提交 Bad Case：

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/bad-cases `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{
    "retrieval_id":"retrieval_xxx",
    "user_query":"Where is my order?",
    "agent_answer":"Your package should arrive soon.",
    "issue_type":"wrong_answer",
    "expected_answer":"The answer should mention tracking status or escalation.",
    "severity":"medium"
  }'
```

DataHub-only 集成说明：

```text
docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md
```

## 测试与评估

语法检查：

```powershell
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py
```

P1 测试：

```powershell
python backend\tests\test_customerops_retrieval.py
python backend\tests\test_rag_quality.py
python backend\tests\test_bad_case_feedback.py
python backend\tests\test_phase_one_flow.py
python backend\tests\test_public_dataset_eval_flow.py
python backend\tests\test_legacy_rag_migration.py
python backend\tests\test_unified_rag_release.py
```

测试覆盖：

- approved-only RAG chunking。
- RAG build idempotency。
- CustomerOpsAgent retrieval contract。
- Bad Case queue and draft creation。
- P1 full flow。
- Public dataset sample evaluation。
- Legacy RAG migration。
- Unified RAG release from multiple source types。

## 公开数据集实测

Dataset：

```text
Bitext customer support dataset
```

Source：

```text
https://github.com/bitext/customer-support-llm-chatbot-training-dataset
```

Committed sample：

```text
samples/public_dataset_eval_sample.json
```

结果摘要：

- 50 conversations。
- 100 messages。
- 50 candidates。
- 10 controlled approvals。
- 10 local RAG chunks。
- 5 retrieval hits for the evaluation query。
- 1 Bad Case to pending-review draft。

报告：

```text
docs/14_PUBLIC_DATASET_EVAL_REPORT.md
```

## Legacy RAG 迁移

示例：

```text
samples/legacy_rag_export_sample.json
```

导入：

```powershell
$payload = Get-Content .\samples\legacy_rag_export_sample.json -Raw

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/legacy-rag/import `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

迁移规则：

- `source_type: legacy_rag`
- `extraction_method: legacy_rag_migration`
- `migration_mode: trusted_import | review_required`
- stable id from `source_name + legacy_id`
- duplicate imports do not create duplicate candidates

报告：

```text
docs/15_LEGACY_RAG_MIGRATION_REPORT.md
```

## 安全边界

- `backend/storage/` 被 Git ignored。
- 不提交真实客服聊天记录。
- 不提交 CustomerOpsAgent 私有 RAG 数据。
- 不提交 API Key、token、密码。
- 不提交 `.env`、`.venv`、`node_modules`。
- CustomerOpsAgent 不直接读 raw / sanitized / candidates。
- Bad Case 不直接修改 RAG。

## Roadmap

P1 已完成：

```text
Text Customer Service Knowledge Loop
-> Unified local DataHub RAG release
```

P2 Roadmap，未实现：

```text
AI Material Center & Multimodal Knowledge
```

P3 Roadmap，未实现：

```text
Sales training dataset export
Fine-tuning dataset export
```

P4 Roadmap，未实现：

```text
MCP Tools & Agent Cluster Integration
```

## FAQ

### DataHub 是否已经是生产级 RAG？

不是。P1-M11 使用 local JSON + keyword/mock retrieval，用于证明治理闭环和接口契约。

### 是否已经接入真实向量库或 embedding？

没有。Qdrant、pgvector、embedding model、database、ORM 都仍是候选。

### CustomerOpsAgent 仓库是否已被修改？

没有。本仓库只提供 DataHub 侧 API 和集成说明。

### Bad Case 是否会自动进入 RAG？

不会。Bad Case 只能转成 `pending_review` candidate，必须人工 approve 后才能通过 RAG build 进入 chunks。

### P2/P3/P4 是否完成？

没有。它们是正式 roadmap，但未实现。

## 术语表

- `raw_imported`：原始导入批次。
- `sanitized`：清洗脱敏后的数据。
- `knowledge candidate`：待审核知识候选。
- `pending_review`：候选知识待审核。
- `approved`：人工审核通过。
- `rag_chunked`：已生成本地 RAG chunk。
- `indexed`：保留给未来真实生产索引。
- `retrieval_id`：CustomerOpsAgent 检索 trace id，用于 Bad Case 绑定。
- `legacy_rag`：从 CustomerOpsAgent 原 RAG export 迁入的知识来源。

## 版本里程碑

- `m2-raw-json-import`
- `m3-cleaning-sanitization`
- `m4-knowledge-candidates`
- `m5-human-review-workflow`
- `m6-rag-builder`
- `m6.5-rag-quality-hardening`
- `m7-customerops-retrieval`
- `m7.5-retrieval-contract-polish`
- `m8-bad-case-feedback`
- `m8.5-bad-case-to-draft`
- `p1-m9-phase-one-release-freeze`
- `p1-m9.5-public-dataset-eval`
- `p1-m10-legacy-rag-migration`
- `p1-m11-unified-rag-release`

历史 tag 保持不改。从 P1-M9 开始，新 tag 使用 phase-prefixed 命名。

## 项目目录

```text
backend/
  app/
  tests/
docs/
frontend/
samples/
scripts/
```

关键文档：

- `docs/10_FINAL_VISION_AND_ROADMAP.md`
- `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`
- `docs/13_P1_RELEASE_FREEZE_REPORT.md`
- `docs/14_PUBLIC_DATASET_EVAL_REPORT.md`
- `docs/15_LEGACY_RAG_MIGRATION_REPORT.md`
- `docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md`
- `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md`
