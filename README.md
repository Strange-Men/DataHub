# DataHub

DataHub is a lightweight data asset center for AI application projects.

Phase one focuses on the CustomerOpsAgent text knowledge loop. This repository is currently at M4 knowledge candidate extraction: JSON customer service chat records can be saved as raw batches, converted into sanitized batches, then transformed into pending-review knowledge candidates.

## Current Scope

Implemented through M4:

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
- Environment example file.
- Development status and stage checklist documents.

Not implemented yet:

- Cleaning and desensitization.
- Human review.
- Approved knowledge.
- RAG.
- CustomerOpsAgent integration.
- Bad Case feedback.
- Multimodal, MCP, or fine-tuning.

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
  "phase": "M4"
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
