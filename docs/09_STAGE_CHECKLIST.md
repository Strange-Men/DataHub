# DataHub Stage Checklist

Use this checklist before every development stage.

## 1. Required Reading

Before starting work, read:

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

## 2. Stage Declaration

Before editing files, state:

- Current milestone.
- Allowed work.
- Forbidden work.
- Expected files to modify.
- Whether the work violates existing project boundaries.

## 3. Scope Check

Confirm:

- The task belongs to the current milestone.
- The task is small enough for one development round.
- The task does not implement future extension points early.
- The task does not change API contracts without updating documentation.
- The task does not introduce unnecessary infrastructure.

## 4. Safety Check

Confirm:

- No real customer private data is committed.
- No API keys or secrets are committed.
- `.env` files are ignored.
- Logs do not expose private data.
- Raw data, sanitized data, drafts, approved knowledge, RAG index, and Bad Cases remain logically separated once implemented.

## 5. CustomerOpsAgent Boundary Check

Confirm:

- CustomerOpsAgent only uses DataHub APIs.
- CustomerOpsAgent does not access the database directly.
- CustomerOpsAgent does not modify knowledge directly.
- CustomerOpsAgent does not retrieve raw data or unapproved drafts.

## 6. Technology Decision Check

Confirmed stack:

- React + TypeScript frontend.
- FastAPI + Python backend.

Do not finalize without explicit approval:

- Database.
- Vector database.
- ORM.
- RAG framework.
- Background task queue.
- Cloud deployment platform.

## 7. Verification Check

At the end of each stage, verify:

- The implemented work matches the milestone acceptance criteria.
- Relevant startup or test commands are documented.
- No forbidden scope was implemented.
- `docs/08_DEV_STATUS.md` is updated.
- API, architecture, or acceptance docs are updated if behavior changed.

## 8. M1 Completion Check

M1 is complete when:

- React + TypeScript frontend scaffold exists.
- FastAPI + Python backend scaffold exists.
- Frontend can show a DataHub base page after dependencies are installed.
- Backend exposes `/health`.
- `.gitignore` exists.
- `.env.example` exists.
- `README.md` explains startup.
- `docs/08_DEV_STATUS.md` exists.
- `docs/09_STAGE_CHECKLIST.md` exists.
- No business feature is implemented.

## 9. M2 Completion Check

M2 is complete when:

- `POST /api/sources/import-json` exists.
- `GET /api/sources` exists.
- `GET /api/sources/{batch_id}` exists.
- Only JSON customer service chat input is supported.
- Each import creates a `batch_id`.
- Raw batch files are saved under `backend/storage/raw_batches/`.
- `storage/` and `backend/storage/` are ignored by Git.
- Batch metadata includes:
  - `batch_id`
  - `source_name`
  - `message_count`
  - `conversation_count`
  - `created_at`
  - `status`
- Imported batches use `raw_imported` status only.
- Frontend can paste JSON, submit import, and display result metadata.
- `samples/customer_chat_sample.json` uses fake data only.
- No CSV, Excel, database, ORM, cleaning, deduplication, desensitization, extraction, review, RAG, CustomerOpsAgent, Bad Case, multimodal, MCP, or fine-tuning work is implemented.
- `docs/04_API_CONTRACT.md` and `docs/08_DEV_STATUS.md` are updated.

## 10. M3 Completion Check

M3 is complete when:

- `POST /api/cleaning/run/{batch_id}` exists.
- `GET /api/cleaning/jobs/{job_id}` exists.
- `GET /api/sanitized/{batch_id}` exists.
- Cleaning reads from `backend/storage/raw_batches/`.
- Cleaning does not overwrite raw batch files.
- Sanitized batches are saved under `backend/storage/sanitized_batches/`.
- Cleaning job metadata is saved under `backend/storage/cleaning_jobs/`.
- Sanitized messages include:
  - `source_batch_id`
  - `conversation_id`
  - `message_id`
  - `source_message_id`
  - `role`
  - `content`
  - `pii_detected`
  - `pii_types`
  - `cleaning_notes`
- Summary includes:
  - `raw_message_count`
  - `sanitized_message_count`
  - `dropped_message_count`
  - `pii_detected_count`
  - `status`
- PII masking supports:
  - Email
  - Phone
  - Order id
  - Tracking id
  - Obvious address text
- Frontend can list raw batches.
- Frontend can run cleaning for a raw batch.
- Frontend can show the cleaning summary.
- Frontend can show sanitized messages without showing full raw sensitive content.
- Sanitized data is not marked as `approved`.
- Sanitized data is not indexed.
- No knowledge extraction, FAQ generation, standard answer generation, business rule generation, human review, RAG, embedding, vector database, CustomerOpsAgent integration, Bad Case, multimodal, MCP, fine-tuning, database, or ORM work is implemented.
- `docs/04_API_CONTRACT.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, and `README.md` are updated.
