# DataHub

DataHub is a multi-source data governance and RAG knowledge platform for Agent clusters.

DataHub is not only a customer service RAG tool. The final product direction is a governed data asset center that can turn customer service records, product docs, Bad Cases, human corrections, and future AI Material Center assets into reviewed text and multimodal knowledge for CustomerOpsAgent, SalesAgent, OpsAgent, MaterialAgent, and future MCP tool consumers.

Phase one still focuses on the CustomerOpsAgent text knowledge loop. This repository is currently at M6 local RAG builder plus M6.2 documentation consistency alignment: JSON customer service chat records can be saved as raw batches, converted into sanitized batches, transformed into pending-review knowledge candidates, reviewed by a human, and built into local RAG chunks when approved.

## Current Scope

Implemented through M6:

- React + TypeScript frontend skeleton.
- FastAPI + Python backend skeleton.
- Frontend base page.
- Backend `/health` endpoint.
- JSON customer service chat import.
- Raw batch metadata listing and lookup.
- Raw batch cleaning and PII masking.
- Sanitized batch lookup.
- Rule-based mock knowledge candidate extraction.
- Pending-review knowledge candidate lookup.
- Human review state transitions for knowledge candidates.
- Local JSON RAG chunk building from approved candidates only.
- Internal keyword/mock RAG search.
- Final vision and four-phase roadmap documentation.
- Documentation consistency fixes for phase status, API roadmap, and canonical state names.
- Environment example file.
- Development status and stage checklist documents.

Not implemented yet:

- Separate approved knowledge/version management.
- CustomerOpsAgent integration.
- Bad Case feedback.
- Multimodal material ingestion and understanding.
- Sales training dataset export.
- Fine-tuning dataset export.
- MCP tools and Agent cluster integration.

## Final Roadmap

```text
Phase 1: Text Customer Service Knowledge Loop
Phase 2: AI Material Center & Multimodal Knowledge
Phase 3: High-quality Dataset Export
Phase 4: MCP Tools & Agent Cluster Integration
```

Current code development remains Phase 1 only. Phase 2, Phase 3, and Phase 4 are formal roadmap phases, not completed features.

Detailed final vision:

```text
docs/10_FINAL_VISION_AND_ROADMAP.md
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Default local URL:

```text
http://localhost:5173
```

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```text
GET http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "M6"
}
```

## M2 JSON Import

Sample file:

```text
samples/customer_chat_sample.json
```

Raw batches are saved locally under:

```text
backend/storage/raw_batches/
```

The storage directory is ignored by Git and must not contain real committed customer records.

### API Verification

Start the backend, then run from the repository root:

```powershell
$payload = Get-Content .\samples\customer_chat_sample.json -Raw
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/sources/import-json `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

List imported batches:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sources
```

Get one batch by id:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sources/{batch_id}
```

### Frontend Verification

Start both backend and frontend.

1. Open `http://localhost:5173`.
2. Paste the sample JSON from `samples/customer_chat_sample.json`.
3. Keep or edit the source name.
4. Click `Import raw JSON`.
5. Confirm the page shows `batch_id`, `message_count`, `conversation_count`, and `raw_imported`.

## M3 Cleaning And Sanitization

Sanitized batches are saved locally under:

```text
backend/storage/sanitized_batches/
```

Cleaning jobs are saved locally under:

```text
backend/storage/cleaning_jobs/
```

Both directories are ignored by Git through `backend/storage/`.

Supported masking:

- Email -> `[EMAIL]`
- Phone or mobile number -> `[PHONE]`
- Order id -> `[ORDER_ID]`
- Tracking id -> `[TRACKING_ID]`
- Obvious address text -> `[ADDRESS]`

Run cleaning by API:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/cleaning/run/{batch_id} `
  -Method Post
```

Get cleaning job status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/cleaning/jobs/{job_id}
```

Get sanitized batch:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sanitized/{batch_id}
```

Frontend M3 verification:

1. Start both backend and frontend.
2. Import `samples/customer_chat_sample.json`.
3. In Raw batches, click `Run cleaning`.
4. Confirm summary counts are shown.
5. Confirm sanitized messages show `[EMAIL]`, `[PHONE]`, `[ORDER_ID]`, `[TRACKING_ID]`, and `[ADDRESS]` for the fake sample data.

M3 does not create knowledge drafts, approved knowledge, RAG indexes, embeddings, CustomerOpsAgent integrations, or Bad Case workflows.

## M4 Knowledge Candidate Extraction

Knowledge candidates are saved locally under:

```text
backend/storage/knowledge_candidates/
```

Extraction jobs are saved locally under:

```text
backend/storage/extraction_jobs/
```

Both directories are ignored by Git through `backend/storage/`.

Extraction method:

```text
rule_based_mock
```

The first version only extracts simple sanitized customer -> agent question-answer pairs. It does not call a real LLM.

Run extraction by API:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/extraction/run/{batch_id} `
  -Method Post
```

Get extraction job status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/extraction/jobs/{job_id}
```

List knowledge candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates
```

Get one candidate:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates/{candidate_id}
```

Frontend M4 verification:

1. Start both backend and frontend.
2. Import `samples/customer_chat_sample.json`.
3. Run cleaning for the raw batch.
4. In Sanitized batches, click `Run extraction`.
5. Confirm extraction summary shows `candidate_count`.
6. Confirm candidates show question, answer, intent, tags, quality score, and `pending_review`.

M4 does not create approved knowledge, RAG indexes, embeddings, CustomerOpsAgent integrations, or Bad Case workflows.

## M5 Human Review

Review records are saved locally under:

```text
backend/storage/review_records/
```

Review updates existing knowledge candidates under:

```text
backend/storage/knowledge_candidates/
```

Both directories are ignored by Git through `backend/storage/`.

Supported review states:

- `pending_review`
- `needs_revision`
- `approved`
- `rejected`

Approved candidates are human-reviewed candidates only. They are not indexed, embedded, or available to CustomerOpsAgent.

List pending review candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/review/pending
```

Edit a candidate:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/knowledge/candidates/{candidate_id} `
  -Method Patch `
  -ContentType 'application/json' `
  -Body '{"question":"Updated question?","answer":"Updated answer.","intent":"shipping","tags":["shipping"],"risk_level":"low","quality_score":0.82}'
```

Approve:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/approve `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Approved."}'
```

Reject:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/reject `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Rejected."}'
```

Needs revision:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/needs-revision `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Needs a clearer answer."}'
```

Frontend M5 verification:

1. Start both backend and frontend.
2. Import sample JSON.
3. Run cleaning.
4. Run extraction.
5. Open the review queue.
6. Edit candidate fields.
7. Enter reviewer and review note.
8. Approve, reject, or mark needs revision.
9. Confirm status updates in the UI.

M5 does not create RAG chunks, embeddings, vector records, CustomerOpsAgent integrations, or Bad Case workflows.

## M6 Local RAG Builder

RAG chunks are saved locally under:

```text
backend/storage/rag_chunks/
```

This directory is ignored by Git through `backend/storage/`.

M6 uses:

```text
local_json_mock_retrieval
```

Rules:

- Only `approved` candidates can become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- RAG chunks preserve candidate and source traceability.
- Search uses local JSON plus simple keyword scoring.
- Current RAG search is local mock retrieval for DataHub internal testing only.
- This is not CustomerOpsAgent integration.
- This is not production vector retrieval.
- This is not a real vector database, embedding model, database, ORM, or RAG framework.

Build local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/build `
  -Method Post
```

List local RAG chunks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/rag/chunks
```

Get one chunk:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/rag/chunks/{chunk_id}
```

Search local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/search `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Frontend M6 verification:

1. Start both backend and frontend.
2. Import sample JSON.
3. Run cleaning.
4. Run extraction.
5. Approve at least one candidate.
6. In Local RAG test, click `Build RAG chunks`.
7. Confirm build summary shows `built_count`, `skipped_count`, `chunk_count`, and `status`.
8. Confirm RAG chunks list shows approved chunks only.
9. Enter a query and click `Search RAG`.
10. Confirm results show score, chunk text, chunk id, candidate id, source conversation id, and tags.

M6 does not create CustomerOpsAgent APIs, Bad Case workflows, embeddings, vector records, database/ORM integrations, real LLM calls, multimodal workflows, MCP, or fine-tuning.

## Development Rules

Before each development round, read:

- `docs/00_PROJECT_SCOPE.md`
- `docs/01_IDEA_PRESSURE_TEST.md`
- `docs/02_PRD.md`
- `docs/03_ARCHITECTURE.md`
- `docs/04_API_CONTRACT.md`
- `docs/05_DEV_RULES.md`
- `docs/06_TECH_STACK_CANDIDATES.md`
- `docs/07_ACCEPTANCE_CRITERIA.md`
- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/10_FINAL_VISION_AND_ROADMAP.md`
