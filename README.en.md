# DataHub | Multi-source Data Governance And RAG Knowledge Platform For Agent Clusters

中文版：[README.md](./README.md)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![React](https://img.shields.io/badge/React-Frontend-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-UI-3178C6)
![RAG](https://img.shields.io/badge/RAG-local%20mock-orange)
![pytest](https://img.shields.io/badge/pytest-optional-lightgrey)
![Data Governance](https://img.shields.io/badge/Data%20Governance-P1--M12-blue)
![Agent-ready](https://img.shields.io/badge/Agent--ready-CustomerOpsAgent-brightgreen)

DataHub is a governed data asset center for AI Agent applications. It turns customer support chats, public support dataset samples, Bad Case correction drafts, and CustomerOpsAgent legacy RAG exports into unified knowledge candidates. Approved candidates become local RAG chunks and are served through a restricted CustomerOpsAgent retrieval API.

The repository is currently at **P1-M12 Advanced Data Cleaning**. P1-M11 completed the Unified DataHub RAG Release, but it is no longer treated as the final high-quality DataHub release. The final Phase 1 high-quality data platform release is now planned for **P1-M15 High-quality DataHub P1 Final Release**.

P1-M12 adds advanced deterministic machine cleaning, duplicate and near-duplicate detection, low-quality and noise flags, enhanced PII masking, message-level quality scores, quality levels, and suggested actions. P1-M13, P1-M14, and P1-M15 remain roadmap stages and have not been implemented.

## Quick Start

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "P1-M12"
}
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Default URL:

```text
http://localhost:5173
```

## P1-M12 To P1-M15 High-quality DataHub Route

- **P1-M12 Advanced Machine Cleaning & Data Quality Scoring**: advanced cleaning, duplicate and near-duplicate detection, low-quality/noise labels, enhanced PII masking, quality scores, and suggested actions.
- **P1-M13 Chinese Admin Console & Manual Cleaning Workbench**: Chinese-first admin console, reserved P1/P2/P3/P4 module entries, manual cleaning workbench, and cleaner guide.
- **P1-M14 Knowledge Review Quality Console**: Chinese review console, reviewer rules, source trace, quality_score, and risk_flags.
- **P1-M15 High-quality DataHub P1 Final Release**: validates machine cleaning -> manual cleaning -> extraction -> human review -> unified RAG -> CustomerOpsAgent retrieval -> Bad Case feedback.

P1-M12 proves DataHub can output governed sanitized data with machine quality labels. It does not implement the full manual cleaning workbench, the P1-M14 review console, or P2/P3/P4 features.

## STAR Breakdown

### Situation

AI customer service and Agent systems often suffer from scattered knowledge, noisy support data, weak privacy boundaries, and RAG knowledge that is hard to keep fresh. CustomerOpsAgent needs a governed and traceable source of knowledge instead of maintaining an isolated knowledge base.

### Task

Build a data governance and unified RAG knowledge platform for Agent clusters:

- Convert raw support chats into reviewable knowledge candidates.
- Prevent unsanitized or unreviewed data from reaching retrieval.
- Provide CustomerOpsAgent with a read-only, restricted, traceable retrieval API.
- Let Bad Cases flow back into DataHub as new review drafts.
- Migrate CustomerOpsAgent legacy RAG exports into DataHub's unified candidate and RAG chunk format.

### Action

Phase 1 implemented:

- JSON customer support chat import.
- Cleaning, basic sanitization, empty-content filtering, and role normalization.
- Advanced machine cleaning with duplicate detection, quality scoring, risk flags, and suggested actions.
- Rule-based mock knowledge candidate extraction.
- Human review with approve / reject / needs_revision states.
- Local RAG chunk building from approved candidates.
- Idempotent RAG build.
- CustomerOpsAgent restricted retrieval API.
- `retrieval_id` and retrieval trace.
- Bad Case submission, queue, and manual handling state.
- Bad Case to `pending_review` candidate draft.
- Public customer support dataset sample evaluation.
- CustomerOpsAgent legacy RAG export import.
- Unified DataHub RAG release test.

### Result

Verified metrics:

- Public dataset sample: 50 conversations / 100 messages.
- Public dataset evaluation: `candidate_count: 50`.
- Controlled approval: `approved_count: 10`.
- Local RAG build: `rag_chunk_count: 10`.
- Retrieval evaluation: `retrieval_hit_count: 5`.
- Bad Case loop: `bad_case_to_draft_count: 1`.
- P1 core flow test passed.
- Public dataset eval test passed.
- Legacy RAG migration test passed.
- Unified RAG release test passed.

These results prove the Phase 1 governance and feedback loop. They do not claim production-grade semantic retrieval quality.

## Why This Is Not Just A RAG Demo

DataHub focuses on a governed lifecycle, not simply searching text:

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

Hard boundaries:

- Raw data never enters extraction, RAG, or CustomerOpsAgent retrieval.
- Sanitized data cannot directly enter RAG.
- `pending_review`, `needs_revision`, and `rejected` candidates cannot enter RAG.
- Bad Cases cannot directly modify candidates or RAG chunks.
- CustomerOpsAgent retrieves through DataHub APIs only.

## Architecture And Workflow

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

P1-M11 unified RAG sources:

```text
chat_logs
public_dataset
bad_case
legacy_rag
manual (reserved)
```

Current implemented coverage:

- `chat_logs`: the main customer support chat loop.
- `public_dataset`: P1-M9.5 small public support dataset evaluation.
- `bad_case`: M8.5 Bad Case to pending-review draft; approved drafts can enter RAG.
- `legacy_rag`: P1-M10 legacy RAG migration.

## Tech Stack

Confirmed:

- Frontend: React + TypeScript.
- Backend: FastAPI + Python.
- Tests: Python `unittest` scripts with FastAPI `TestClient`.
- Current storage: local JSON files under `backend/storage/`.
- Current retrieval: local keyword/mock retrieval.

Still candidates:

- Database: SQLite / PostgreSQL.
- Vector store: pgvector / Qdrant.
- ORM: SQLAlchemy / SQLModel.
- RAG orchestration: lightweight service / LangChain / LlamaIndex.
- Background tasks: FastAPI BackgroundTasks / Celery / RQ.
- Deployment: local Docker Compose / later cloud deployment.

## Phase 1 Core Capabilities

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

Supported masking:

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

Current method:

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

Rules:

- Approved candidates only.
- Idempotent build.
- Stable chunk ids derived from candidate ids.
- Search returns `score`, `matched_terms`, and source trace.

### M7 / M7.5 CustomerOpsAgent Retrieval

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
```

Required header:

```text
X-DataHub-Client: CustomerOpsAgent
```

This header is a local development auth placeholder, not a production token.

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

The generated candidate must remain:

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

`trusted_import=true`:

```text
legacy item -> approved candidate
```

`trusted_import=false`:

```text
legacy item -> pending_review candidate
```

## Unified RAG And CustomerOpsAgent Integration

After P1-M11, the recommended CustomerOpsAgent path is DataHub-only retrieval:

```text
CustomerOpsAgent receives user query
-> POST /api/customer-ops-agent/retrieve
-> use returned answer / chunks / source trace
-> generate final customer-facing response
-> if answer is bad, submit Bad Case with retrieval_id
```

CustomerOpsAgent does not need to know whether a result came from chat logs, public data, Bad Case correction, or legacy RAG. DataHub keeps source trace for audit and feedback.

Retrieve:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Submit a Bad Case:

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

Integration guide:

```text
docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md
```

## Tests And Evaluation

Compile check:

```powershell
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py
```

P1 tests:

```powershell
python backend\tests\test_customerops_retrieval.py
python backend\tests\test_rag_quality.py
python backend\tests\test_bad_case_feedback.py
python backend\tests\test_phase_one_flow.py
python backend\tests\test_public_dataset_eval_flow.py
python backend\tests\test_legacy_rag_migration.py
python backend\tests\test_unified_rag_release.py
```

Coverage:

- Approved-only RAG chunking.
- RAG build idempotency.
- CustomerOpsAgent retrieval contract.
- Bad Case queue and draft creation.
- P1 full flow.
- Public dataset sample evaluation.
- Legacy RAG migration.
- Unified RAG release across multiple source types.

## Public Dataset Evaluation

Dataset:

```text
Bitext customer support dataset
```

Source:

```text
https://github.com/bitext/customer-support-llm-chatbot-training-dataset
```

Committed sample:

```text
samples/public_dataset_eval_sample.json
```

Result summary:

- 50 conversations.
- 100 messages.
- 50 candidates.
- 10 controlled approvals.
- 10 local RAG chunks.
- 5 retrieval hits for the evaluation query.
- 1 Bad Case to pending-review draft.

Report:

```text
docs/14_PUBLIC_DATASET_EVAL_REPORT.md
```

## Legacy RAG Migration

Sample:

```text
samples/legacy_rag_export_sample.json
```

Import:

```powershell
$payload = Get-Content .\samples\legacy_rag_export_sample.json -Raw

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/legacy-rag/import `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

Migration rules:

- `source_type: legacy_rag`
- `extraction_method: legacy_rag_migration`
- `migration_mode: trusted_import | review_required`
- stable id from `source_name + legacy_id`
- duplicate imports do not create duplicate candidates

Report:

```text
docs/15_LEGACY_RAG_MIGRATION_REPORT.md
```

## Safety Boundaries

- `backend/storage/` is ignored by Git.
- Real customer support logs are not committed.
- CustomerOpsAgent private RAG data is not committed.
- API keys, tokens, and passwords are not committed.
- `.env`, `.venv`, and `node_modules` are not committed.
- CustomerOpsAgent does not directly read raw data, sanitized data, or candidates.
- Bad Cases do not directly modify RAG.

## Roadmap

Completed P1:

```text
Text Customer Service Knowledge Loop
-> Unified local DataHub RAG release
```

P2 Roadmap, not implemented:

```text
AI Material Center & Multimodal Knowledge
```

P3 Roadmap, not implemented:

```text
Sales training dataset export
Fine-tuning dataset export
```

P4 Roadmap, not implemented:

```text
MCP Tools & Agent Cluster Integration
```

## FAQ

### Is DataHub production-grade RAG now?

No. P1-M11 uses local JSON plus keyword/mock retrieval to validate governance and contracts.

### Does it use a vector database or embeddings?

No. Qdrant, pgvector, embedding models, databases, and ORMs are still candidate choices.

### Was the CustomerOpsAgent repository modified?

No. This repository provides the DataHub-side APIs and integration guide only.

### Can a Bad Case automatically enter RAG?

No. A Bad Case can become a `pending_review` candidate. It must be approved before RAG build can include it.

### Are P2/P3/P4 complete?

No. They are formal roadmap phases and have not been implemented.

## Glossary

- `raw_imported`: imported raw batch.
- `sanitized`: cleaned and masked data.
- `knowledge candidate`: reviewable knowledge draft.
- `pending_review`: candidate awaiting review.
- `approved`: human-approved candidate.
- `rag_chunked`: local RAG chunk generated.
- `indexed`: reserved for future production index.
- `retrieval_id`: CustomerOpsAgent retrieval trace id for Bad Case binding.
- `legacy_rag`: knowledge imported from a CustomerOpsAgent legacy RAG export.

## Milestones

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

Historical tags are kept as-is. New tags from P1-M9 onward use phase-prefixed names.

## Project Structure

```text
backend/
  app/
  tests/
docs/
frontend/
samples/
scripts/
```

Key documents:

- `docs/10_FINAL_VISION_AND_ROADMAP.md`
- `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`
- `docs/13_P1_RELEASE_FREEZE_REPORT.md`
- `docs/14_PUBLIC_DATASET_EVAL_REPORT.md`
- `docs/15_LEGACY_RAG_MIGRATION_REPORT.md`
- `docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md`
- `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md`
