# DataHub Development Status

## Current Stage

M2 Data Import.

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

## Current Boundaries

Allowed in M2:

- JSON customer service chat import only.
- Local raw batch file storage only.
- Metadata listing and lookup.
- Minimal frontend import form.
- Fake sample data only.

Forbidden in M2:

- Cleaning and desensitization.
- CSV import.
- Excel import.
- Database selection finalization.
- PostgreSQL integration.
- SQLite integration.
- ORM integration.
- Knowledge extraction.
- Human review.
- RAG implementation.
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
- `/health` endpoint is defined and reports M2.
- M2 JSON import endpoints are defined.
- Raw batches are written to ignored local storage.
- No cleaning, desensitization, extraction, RAG, CustomerOpsAgent integration, Bad Case workflow, or multimodal workflow has been implemented.

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

## Next Suggested Stage

M3 Cleaning And Desensitization planning.

Before M3 starts:

- Confirm exactly which fields and patterns will be cleaned or desensitized first.
- Keep raw and sanitized data separated.
- Do not implement knowledge extraction, RAG, CustomerOpsAgent integration, or Bad Case feedback in M3 unless explicitly approved later.

M3 must not finalize database, vector database, ORM, or RAG framework choices unless a separate technology decision is requested.
