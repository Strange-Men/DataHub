# DataHub Development Status

## Current Stage

M6 completed. M6.1 final vision documentation completed. M6.2 documentation consistency completed. M6.5 RAG quality hardening completed. Current checkpoint: M7 CustomerOpsAgent restricted retrieval.

Current code remains Phase 1.

Phase 2, Phase 3, and Phase 4 are formal roadmap phases, but they must not be implemented early.

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

## Completed In M5

- Added pending review API: `GET /api/review/pending`.
- Added candidate edit API: `PATCH /api/knowledge/candidates/{candidate_id}`.
- Added review decision APIs:
  - `POST /api/review/{candidate_id}/approve`
  - `POST /api/review/{candidate_id}/reject`
  - `POST /api/review/{candidate_id}/needs-revision`
- Added candidate review states:
  - `pending_review`
  - `needs_revision`
  - `approved`
  - `rejected`
- Added review metadata:
  - `reviewer`
  - `review_note`
  - `reviewed_at`
  - `updated_at`
- Added local review record storage under `backend/storage/review_records/`.
- Added React review queue, candidate editing, reviewer/note inputs, and Approve/Reject/Needs revision actions.

## Completed In M6

- Added local RAG build API: `POST /api/rag/build`.
- Added RAG chunk list API: `GET /api/rag/chunks`.
- Added RAG chunk detail API: `GET /api/rag/chunks/{chunk_id}`.
- Added local RAG search API: `POST /api/rag/search`.
- Added local RAG chunk storage under `backend/storage/rag_chunks/`.
- Added `local_json_mock_retrieval` build and search method.
- Added approved-only chunk generation:
  - `approved` candidates can become chunks.
  - `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- Added source traceability to every chunk:
  - `candidate_id`
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
- Added React controls to show approved candidate count, build chunks, list chunks, and test local search.

## Completed In M6.1

- Added `docs/10_FINAL_VISION_AND_ROADMAP.md`.
- Strengthened DataHub's final positioning:
  - DataHub is a multi-source data governance and RAG knowledge platform for Agent clusters.
  - DataHub is not only a CustomerOpsAgent customer service RAG tool.
- Documented the formal four-phase roadmap:
  - Phase 1: Text Customer Service Knowledge Loop.
  - Phase 2: AI Material Center and Multimodal Knowledge.
  - Phase 3: High-quality Dataset Export.
  - Phase 4: MCP Tools and Agent Cluster Integration.
- Updated scope, PRD, architecture, acceptance criteria, and README to align with the final vision.
- Confirmed that current code development remains Phase 1 only.
- Confirmed that Phase 2, Phase 3, and Phase 4 are roadmap phases and must not be implemented early.

## Completed In M6.2

- Aligned documentation phase status after M6.1.
- Replaced M0-era development rule wording with permanent guardrails.
- Clarified that `docs/08_DEV_STATUS.md` is the source of truth for the current milestone.
- Split API contract status into:
  - Implemented APIs: M2-M6.
  - Planned Phase 1 APIs: M7-M8.
  - Future Roadmap APIs: Phase 2-4.
- Added canonical state naming guidance.
- Clarified that M6 local RAG search is mock retrieval, not CustomerOpsAgent production retrieval.
- Confirmed that no business code changed in M6.2.

## Completed In M6.3

- Adjusted PRD Phase 1 target flow wording so CustomerOpsAgent retrieval and Bad Case feedback are not implied as already complete.
- Clarified canonical state flow:
  - `approved` does not mean RAG-ready.
  - `rag_chunked` is the current local RAG chunk state.
  - `indexed` is reserved for future production retrieval index work.
- Updated development rules so `docs/CHANGELOG.md` is optional unless explicitly needed.
- Updated M7 acceptance wording to allow approved `rag_chunked` records as retrieval-ready before production vector indexing exists.

## Completed In M6.5

- Hardened local RAG build idempotency.
- Prevented repeated builds from creating duplicate chunks.
- Added `updated_count` to RAG build results.
- Added query trimming, max length, and `top_k` validation for local RAG search.
- Added `matched_terms` to search results for local debugging.
- Added lightweight RAG quality verification script under `backend/tests/`.
- Confirmed M6.5 remains local JSON plus mock retrieval only.
- Confirmed M6.5 does not implement CustomerOpsAgent, Bad Case, vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning.

## Completed In M7

- Added CustomerOpsAgent restricted retrieval API: `POST /api/customer-ops-agent/retrieve`.
- Added retrieval trace lookup API: `GET /api/customer-ops-agent/retrievals/{retrieval_id}`.
- Added retrieval trace storage under `backend/storage/retrieval_logs/`.
- CustomerOpsAgent retrieval reads only local RAG chunks under `backend/storage/rag_chunks/`.
- CustomerOpsAgent retrieval returns approved local `rag_chunked` results only.
- Retrieval results include:
  - `retrieval_id`
  - `retrieval_mode`
  - `score`
  - `matched_terms`
  - `chunk_id`
  - `candidate_id`
  - source trace
- Retrieval traces store query, top_k, filters, result count, result chunk ids, optional conversation/session ids, created time, and retrieval mode.
- Added lightweight M7 verification script under `backend/tests/`.
- Updated React UI with a minimal CustomerOpsAgent Retrieval Test section.
- Confirmed M7 does not modify the CustomerOpsAgent repository.
- Confirmed M7 does not implement Bad Case, vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning.

## Current Boundaries

### Current Implemented Capabilities

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
- Human review of existing knowledge candidates.
- Candidate field editing.
- Review status transitions.
- Local review record storage.
- Local RAG chunk generation from approved candidates only.
- Local JSON chunk storage.
- Local keyword/mock retrieval for DataHub internal testing only.
- M6.1 documentation-only final vision and roadmap clarification.
- M6.2 documentation-only consistency fixes.
- M6.3 documentation micro-fixes.
- M6.5 local RAG quality hardening:
  - idempotent build
  - duplicate chunk prevention
  - query/top_k validation
  - matched_terms debug output
- M7 CustomerOpsAgent restricted retrieval:
  - retrieval API over approved local RAG chunks
  - retrieval trace lookup
  - local retrieval log storage
  - source trace in results

### Current Forbidden Work

- CSV import.
- Excel import.
- Database selection finalization.
- PostgreSQL integration.
- SQLite integration.
- ORM integration.
- Real LLM integration.
- Modifying the CustomerOpsAgent repository.
- Bad Case feedback.
- Bad Case API or UI.
- Human correction workflow.
- Treating local RAG test as CustomerOpsAgent production retrieval.
- Real vector database integration.
- Embedding model integration.
- Documentation-only stages do not permit business code changes.
- Phase 2, Phase 3, and Phase 4 must not be implemented unless explicitly started.
Forbidden from prior stages remains:
- CSV import.
- Excel import.
- Database selection finalization.
- PostgreSQL integration.
- SQLite integration.
- ORM integration.
- Real LLM integration.
- Knowledge version management.
- Embedding beyond local keyword/mock search.
- Vector database integration.
- Multimodal features.
- MCP.
- Fine-tuning.
- Database, vector database, ORM, or RAG framework finalization.

## Next Allowed Stage Candidates

The next implementation stage must still stay inside Phase 1.

Allowed candidates:

- M7.5 retrieval contract polish if another M7 hardening round is explicitly requested.
- M8 Bad Case Feedback.

Not allowed as the next immediate implementation stage unless explicitly approved later:

- Phase 2 AI Material Center or multimodal implementation.
- Phase 3 sales training export or fine-tuning dataset export.
- Phase 4 MCP Tools or Agent cluster integration.

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
- `/health` endpoint is defined and reports M6.5.
- M2 JSON import endpoints are defined.
- Raw batches are written to ignored local storage.
- M3 cleaning endpoints are defined.
- Sanitized batches are written to ignored local storage.
- Raw batches are not overwritten by cleaning.
- M4 extraction endpoints are defined.
- Knowledge candidates are written to ignored local storage.
- Extraction reads only sanitized batches.
- M5 review endpoints are defined.
- Review updates only existing knowledge candidates.
- M6 RAG endpoints are defined.
- RAG build reads only knowledge candidates.
- RAG chunks are built only from `approved` candidates.
- RAG build is idempotent and repeated builds do not create duplicate chunks.
- Pending, needs-revision, and rejected candidates are skipped.
- RAG search validates empty query, query length, and `top_k`.
- RAG search returns `matched_terms` and source trace.
- RAG chunks are written to ignored local storage.
- M7 CustomerOpsAgent retrieval endpoints are defined.
- CustomerOpsAgent retrieval reads only local RAG chunks.
- CustomerOpsAgent retrieval returns only approved local `rag_chunked` results.
- Retrieval traces are written to ignored local storage.
- No Bad Case workflow, database, ORM, vector store, embedding model, real LLM, or multimodal workflow has been implemented.
- Final vision is documented, but Phase 2/3/4 features have not been implemented.

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

Read pending review queue:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/review/pending
```

Approve a candidate:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/approve `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Approved."}'
```

Build local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/build `
  -Method Post
```

List RAG chunks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/rag/chunks
```

Search local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/search `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Retrieve through the CustomerOpsAgent restricted API:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Read retrieval trace:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/customer-ops-agent/retrievals/{retrieval_id}
```

## Next Suggested Stage

Continue Phase 1 only.

Recommended options:

- M7.5 retrieval contract polish if another M7 hardening round is explicitly requested.
- M8 Bad Case feedback planning.

Before M8 starts:

- Confirm Bad Case request and response contract.
- Confirm how M8 references `retrieval_id`.
- Confirm Bad Case status names and human review queue boundaries.
- Confirm that Bad Case fixes must re-enter the normal candidate and review workflow.

M8 must not implement multimodal retrieval, MCP, model fine-tuning, or Phase 2/3/4 unless explicitly approved later.

Phase 2 AI Material Center, Phase 3 dataset export, and Phase 4 MCP are now documented as formal roadmap phases, but they are not the next implementation stage.
