# DataHub Development Status

## Current Stage

M4 Knowledge Candidate Extraction.

## Completed Through M1

- Created minimal React + TypeScript frontend scaffold.
- Created minimal FastAPI + Python backend scaffold.
- Added a frontend DataHub baseline page.
- Added backend `/health` endpoint.
- Added `.gitignore`.
- Added `.env.example`.
- Added root `README.md` with frontend and backend startup instructions.
- Added this development status document.
- Added `docs/09_STAGE_CHECKLIST.md`.

## Completed In M2

- Added JSON customer service chat import API: `POST /api/sources/import-json`.
- Added raw source batch listing API: `GET /api/sources`.
- Added raw source batch metadata API: `GET /api/sources/{batch_id}`.
- Added local raw batch storage under `backend/storage/raw_batches/`.
- Added raw batch metadata:
  - `batch_id`
  - `source_name`
  - `message_count`
  - `conversation_count`
  - `created_at`
  - `status`
- Added React JSON import form.
- Added fake sample chat data at `samples/customer_chat_sample.json`.
- Updated `.gitignore` to exclude storage.
- Updated API contract and validation instructions.

## Completed In M3

- Added cleaning and sanitization API: `POST /api/cleaning/run/{batch_id}`.
- Added cleaning job lookup API: `GET /api/cleaning/jobs/{job_id}`.
- Added sanitized batch lookup API: `GET /api/sanitized/{batch_id}`.
- Added sanitized batch storage under `backend/storage/sanitized_batches/`.
- Added cleaning job storage under `backend/storage/cleaning_jobs/`.
- Added minimal cleaning rules:
  - Trim message content.
  - Drop empty message content.
  - Standardize role to `customer`, `agent`, or `system`.
  - Add safe fallback values for missing fields.
- Added minimal PII masking:
  - Email
  - Phone
  - Order id
  - Tracking id
  - Obvious address text
- Added React controls to list raw batches, run cleaning, show cleaning summaries, and view sanitized messages.
- Updated fake sample data with fake PII for validation.
- Updated README, API contract, and stage checklist.

## Completed In M4

- Added knowledge candidate extraction API: `POST /api/extraction/run/{batch_id}`.
- Added extraction job lookup API: `GET /api/extraction/jobs/{job_id}`.
- Added knowledge candidate list API: `GET /api/knowledge/candidates`.
- Added knowledge candidate detail API: `GET /api/knowledge/candidates/{candidate_id}`.
- Added extraction job storage under `backend/storage/extraction_jobs/`.
- Added knowledge candidate storage under `backend/storage/knowledge_candidates/`.
- Added `rule_based_mock` extraction from sanitized customer -> agent question-answer pairs.
- Added candidate fields:
  - `candidate_id`
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
  - `knowledge_type`
  - `question`
  - `answer`
  - `intent`
  - `tags`
  - `risk_level`
  - `review_status`
  - `quality_score`
  - `extraction_method`
  - `created_at`
- Added React controls to list sanitized batches, run extraction, show extraction summary, and show pending-review candidates.

## Current Boundaries

Allowed in M4:

- JSON customer service chat import only.
- Local raw batch file storage only.
- Metadata listing and lookup.
- Minimal frontend import form.
- Fake sample data only.
- Raw batch to sanitized batch conversion.
- Local sanitized batch storage.
- Minimal cleaning and PII masking.
- Sanitized batch to pending-review knowledge candidate extraction.
- Rule-based mock extraction only.
- Local knowledge candidate storage.
- Candidate list and detail APIs.

Forbidden in M4:

- CSV import.
- Excel import.
- Database selection finalization.
- PostgreSQL integration.
- SQLite integration.
- ORM integration.
- Real LLM integration.
- Human review.
- Approved knowledge.
- Knowledge version management.
- RAG implementation.
- Embedding.
- Vector database integration.
- CustomerOpsAgent integration.
- Bad Case feedback.
- Multimodal features.
- MCP.
- Fine-tuning.
- Database, vector database, ORM, or RAG framework finalization.

## Current Technical Direction

Confirmed:

- Frontend: React + TypeScript.
- Backend: FastAPI + Python.

Still candidates:

- Database.
- Vector store.
- ORM.
- RAG orchestration.
- Background task system.
- Deployment platform.

## Verification Status

- Frontend scaffold files are present.
- Backend scaffold files are present.
- `/health` endpoint is defined and reports M4.
- M2 JSON import endpoints are defined.
- Raw batches are written to ignored local storage.
- M3 cleaning endpoints are defined.
- Sanitized batches are written to ignored local storage.
- Raw batches are not overwritten by cleaning.
- M4 extraction endpoints are defined.
- Knowledge candidates are written to ignored local storage.
- Extraction reads only sanitized batches.
- Candidates use `pending_review` only.
- No human review, approved status, RAG, CustomerOpsAgent integration, Bad Case workflow, database, ORM, vector store, real LLM, or multimodal workflow has been implemented.

Manual verification:

```powershell
$payload = Get-Content .\samples\customer_chat_sample.json -Raw
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/sources/import-json `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

Then list sources:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sources
```

Run cleaning:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/cleaning/run/{batch_id} `
  -Method Post
```

Read sanitized batch:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sanitized/{batch_id}
```

Run extraction:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/extraction/run/{batch_id} `
  -Method Post
```

Read knowledge candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates
```

## Next Suggested Stage

M5 Human Review planning.

Before M5 starts:

- Confirm review decision model.
- Confirm candidate edit fields.
- Confirm approve/reject/needs_revision transitions.
- Keep approved knowledge out of RAG until M6.

M5 must not implement RAG, CustomerOpsAgent integration, Bad Case feedback, vector storage, or model fine-tuning unless explicitly approved later.
