# DataHub Development Status

## Current Stage

M6 completed. M6.1 final vision documentation completed. M6.2 documentation consistency completed. M6.5 RAG quality hardening completed. M7 CustomerOpsAgent restricted retrieval completed. M7.5 retrieval contract polish completed. M8 Bad Case feedback completed. M8.5 Bad Case resolution to draft completed. P1-M9 Phase-One Release Freeze completed. P1-M9.5 Public Dataset Evaluation completed. P1-M10 Legacy RAG Migration completed. P1-M11 Unified DataHub RAG Release completed. P1-M12 Advanced Data Cleaning completed. P1-M13 Chinese Admin Console & Manual Cleaning Workbench completed. P1-M14 Knowledge Review Quality Console completed. Current checkpoint: P1-M15 High-quality DataHub Final Release.

Current code remains Phase 1.

Phase 2, Phase 3, and Phase 4 are formal roadmap phases, but they must not be implemented early.

P1-M11 is no longer treated as the final high-quality DataHub release. It is the unified DataHub RAG release.
P1-M15 High-quality DataHub Final Release completed. P1 is now accepted as the high-quality text data governance and unified local RAG release.
Current cleanup checkpoint: P1-M15.5 Frontend UX Cleanup & Project Boundary Review. Current deployment checkpoint: P1-M15.6 Render Deployment Config. Current UX redesign checkpoint: P1-M15.7 Product UX Redesign & Deployment Link Fix. Current public surface cleanup checkpoint: P1-M15.8 Homepage UX Cleanup & Public Surface Cleanup.

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

## Completed In M7.5

- Added `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`.
- Added local development auth placeholder for CustomerOpsAgent retrieval APIs:
  - `X-DataHub-Client: CustomerOpsAgent`
- Required the auth placeholder on:
  - `POST /api/customer-ops-agent/retrieve`
  - `GET /api/customer-ops-agent/retrievals/{retrieval_id}`
- Unified CustomerOpsAgent retrieval API error responses into:
  - `success: false`
  - `error.code`
  - `error.message`
  - `error.details`
  - `requestId`
- Added test coverage for:
  - missing client header
  - invalid client header
  - valid client header
  - empty query
  - overlong query
  - `top_k` below 1
  - `top_k` above 10
  - missing retrieval trace
- Updated README, API contract, acceptance criteria, development status, and stage checklist.
- Confirmed M7.5 does not introduce API keys, real tokens, `.env` secrets, production auth, Bad Case, CustomerOpsAgent repository changes, vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning.

## Completed In M8

- Added CustomerOpsAgent Bad Case submission API: `POST /api/customer-ops-agent/bad-cases`.
- Added Bad Case queue APIs:
  - `GET /api/bad-cases`
  - `GET /api/bad-cases/{bad_case_id}`
  - `PATCH /api/bad-cases/{bad_case_id}`
- Reused the local CustomerOpsAgent auth placeholder:
  - `X-DataHub-Client: CustomerOpsAgent`
- Added Bad Case storage under `backend/storage/bad_cases/`.
- Required Bad Cases to bind to an existing `retrieval_id`.
- Saved retrieval trace metadata on Bad Cases:
  - `linked_chunk_ids`
  - `retrieval_result_count`
- Added Bad Case statuses:
  - `open`
  - `triaged`
  - `resolved`
  - `ignored`
- Added minimal React Bad Case submission and triage UI.
- Added lightweight M8 verification script under `backend/tests/`.
- Confirmed M8 does not create knowledge candidates, modify existing candidates, modify RAG chunks, rebuild RAG, re-index, modify the CustomerOpsAgent repository, or introduce vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning.

## Completed In M8.5

- Added Bad Case to pending-review draft API: `POST /api/bad-cases/{bad_case_id}/create-draft`.
- Created new `kc_badcase_*` knowledge candidates from human-provided Bad Case resolution fields.
- Added Bad Case source trace fields on generated candidates:
  - `source_type`
  - `source_bad_case_id`
  - `source_retrieval_id`
  - `source_chunk_ids`
- Generated candidates use:
  - `review_status: pending_review`
  - `extraction_method: bad_case_resolution`
- Updated the source Bad Case with:
  - `status: resolved`
  - `linked_candidate_id`
  - `resolution_type`
  - appended `review_note`
- Added minimal React controls to create pending-review drafts from selected Bad Cases.
- Extended Bad Case feedback tests to cover draft creation boundaries.
- Confirmed M8.5 does not auto-approve candidates, modify existing candidates, modify RAG chunks, rebuild RAG, re-index, modify the CustomerOpsAgent repository, or introduce vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning.

## Completed In P1-M9

- Added `backend/tests/test_phase_one_flow.py` for full P1 core loop verification.
- Added `docs/13_P1_RELEASE_FREEZE_REPORT.md`.
- Verified the P1 core loop:
  - JSON import
  - cleaning and sanitization
  - knowledge extraction
  - human approval
  - local RAG chunk build
  - CustomerOpsAgent restricted retrieval
  - Bad Case submission
  - Bad Case to `pending_review` draft
- Confirmed rejected and needs-revision candidates do not enter RAG.
- Confirmed Bad Case-generated drafts are not auto-approved and do not modify RAG chunks.
- Established phase-prefixed tag naming for new tags from P1-M9 onward.

## Completed In P1-M9.5

- Selected the Bitext customer support dataset for public small-sample evaluation.
- Recorded dataset source and license notes in `docs/14_PUBLIC_DATASET_EVAL_REPORT.md`.
- Added a safe converted sample at `samples/public_dataset_eval_sample.json`.
- Kept the full public CSV outside the repository.
- Added `scripts/prepare_public_dataset_sample.py` to convert a local CSV into DataHub import JSON.
- Added `scripts/run_public_dataset_eval.py` to run the public sample through the P1 pipeline and print metrics.
- Added `backend/tests/test_public_dataset_eval_flow.py` for automated public sample flow verification.
- Verified the public sample flow:
  - JSON import
  - cleaning and sanitization
  - knowledge extraction
  - controlled approval
  - local RAG chunk build
  - CustomerOpsAgent restricted retrieval
  - Bad Case submission
  - Bad Case to `pending_review` draft
- Confirmed P1-M9.5 does not migrate CustomerOpsAgent legacy RAG, switch unified RAG, implement P2/P3/P4, or introduce database, ORM, embedding, vector database, or real LLM integrations.

## Completed In P1-M10

- Added legacy RAG import API: `POST /api/legacy-rag/import`.
- Added legacy import listing API: `GET /api/legacy-rag/imports`.
- Added legacy import detail API: `GET /api/legacy-rag/imports/{import_id}`.
- Added fake legacy RAG export sample at `samples/legacy_rag_export_sample.json`.
- Added legacy import metadata storage under `backend/storage/legacy_rag_imports/`.
- Converted legacy RAG items into normal DataHub knowledge candidates.
- Added legacy candidate trace fields:
  - `source_type: legacy_rag`
  - `source_legacy_id`
  - `source_import_id`
  - `migration_mode`
  - `source_note`
- Added `trusted_import=true` mode for approved legacy candidates.
- Added `trusted_import=false` mode for pending-review legacy candidates.
- Added stable candidate ids derived from `source_name + legacy_id`.
- Added duplicate import protection so repeated imports do not create duplicate candidates.
- Propagated legacy source trace into RAG chunks and CustomerOpsAgent retrieval results.
- Added `backend/tests/test_legacy_rag_migration.py`.
- Added `docs/15_LEGACY_RAG_MIGRATION_REPORT.md`.
- Confirmed P1-M10 does not read or modify the CustomerOpsAgent repository.
- Confirmed P1-M10 does not switch CustomerOpsAgent to DataHub-only retrieval.
- Confirmed P1-M10 does not introduce database, ORM, embedding, vector database, real LLM, or P2/P3/P4 features.

## Completed In P1-M11

- Completed the P1 final unified DataHub RAG release.
- Updated `/health` to report `P1-M11`.
- Defined the unified P1 source set:
  - `chat_logs`
  - `public_dataset`
  - `bad_case`
  - `legacy_rag`
  - `manual` as a reserved source type.
- Added source type propagation for new chat log and public dataset extractions.
- Confirmed all governed sources converge into the same DataHub candidate, approved candidate, local RAG chunk, and CustomerOpsAgent retrieval format.
- Added `backend/tests/test_unified_rag_release.py`.
- Added `docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md`.
- Added `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md`.
- Rewrote the Chinese `README.md` for P1-M11 release positioning with STAR structure.
- Added English `README.en.md`.
- Confirmed P1-M11 does not modify the CustomerOpsAgent repository.
- Confirmed P1-M11 does not introduce database, ORM, embedding, vector database, real LLM, MCP, or P2/P3/P4 features.

## Completed In P1-M12

- Updated the Phase 1 route so P1-M11 is the unified RAG release and P1-M15 is the final high-quality DataHub release.
- Documented P1-M12 to P1-M15:
  - P1-M12 Advanced Machine Cleaning & Data Quality Scoring.
  - P1-M13 Chinese Admin Console & Manual Cleaning Workbench.
  - P1-M14 Knowledge Review Quality Console.
  - P1-M15 High-quality DataHub P1 Final Release.
- Added advanced machine cleaning:
  - exact duplicate detection
  - near duplicate detection
  - low-quality text detection
  - repeated-character and symbol-noise detection
  - possible ad/noise/off-topic flags
  - weak question and weak answer flags
- Enhanced PII masking:
  - name-like text
  - ZIP/postal code
  - payment-like long digit sequences
- Added sanitized message governance fields:
  - `cleaning_issues`
  - `risk_flags`
  - `quality_score`
  - `quality_level`
  - `suggested_action`
- Added cleaning summary metrics:
  - `exact_duplicate_count`
  - `near_duplicate_count`
  - `low_quality_count`
  - `noise_count`
  - `review_recommended_count`
  - `drop_recommended_count`
  - `average_quality_score`
- Updated extraction so messages marked `suggested_action: drop` do not become candidates.
- Added `backend/tests/test_advanced_cleaning.py`.
- Added `docs/18_ADVANCED_CLEANING_RULES.md`.
- Confirmed P1-M12 does not implement the full manual cleaning frontend, P1-M14 review console, P1-M15 final release, CustomerOpsAgent repository changes, database, ORM, embedding, vector database, real LLM, MCP, or P2/P3/P4 features.

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
- M7.5 retrieval contract polish:
  - CustomerOpsAgent contract document
  - local auth placeholder header
  - unified CustomerOps retrieval error responses
  - PowerShell examples with headers
- M8 Bad Case feedback:
  - CustomerOpsAgent Bad Case submission
  - retrieval_id validation
  - local Bad Case queue storage
  - manual status and review note updates
- M8.5 Bad Case resolution to draft:
  - pending-review candidate creation from Bad Cases
  - Bad Case source trace on generated candidates
  - linked_candidate_id recorded on Bad Cases
- P1-M9 release freeze:
  - full-chain verification
  - release report
  - phase-prefixed tag naming rule
- P1-M9.5 public dataset evaluation:
  - small public support dataset sample
  - conversion script
  - evaluation runner
  - report and automated public sample flow test
- P1-M10 legacy RAG migration:
  - fake legacy RAG export sample
  - DataHub-side legacy import APIs
  - trusted and review-required migration modes
  - idempotent legacy candidate generation
  - legacy source trace through candidate, chunk, and retrieval
- P1-M11 unified DataHub RAG release:
  - multi-source candidate and chunk source trace
  - unified CustomerOpsAgent retrieval contract
  - DataHub-only integration guide
  - Chinese and English release README files
- P1-M12 advanced data cleaning:
  - quality scoring and issue labels on sanitized messages
  - enhanced PII masking
  - duplicate and near-duplicate detection
  - extraction boundary that skips drop-recommended messages

### Current Forbidden Work

- CSV import.
- Excel import.
- Database selection finalization.
- PostgreSQL integration.
- SQLite integration.
- ORM integration.
- Real LLM integration.
- Modifying the CustomerOpsAgent repository.
- Automatic Bad Case to approved knowledge generation.
- Direct Bad Case modification of existing candidates.
- Automatic Bad Case to RAG chunk modification.
- Automatic RAG rebuild or re-index from Bad Case resolution.
- Human correction workflow beyond pending-review draft creation.
- Production authentication.
- API key or real token introduction.
- `.env` secret introduction.
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

P1-M11 is the unified DataHub RAG release. P1-M15 is the high-quality DataHub final Phase 1 release and is now complete.

Allowed candidates:

- Pause development for project review, resume packaging, and architecture retrospective.
- Prepare P1-P4 architecture explanation materials.
- Start P2-M1 only after separate scope approval.

Not allowed as the next immediate implementation stage unless explicitly approved later:

- Phase 2 AI Material Center or multimodal implementation without explicit approval.
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
- `/health` endpoint is defined and reports P1-M15.
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
- CustomerOpsAgent retrieval requires `X-DataHub-Client: CustomerOpsAgent`.
- CustomerOpsAgent retrieval errors use the unified safe error shape.
- Retrieval traces are written to ignored local storage.
- M8 Bad Case submission and queue management APIs are defined.
- Bad Cases are written to ignored local storage.
- Bad Cases bind to existing retrieval traces through `retrieval_id`.
- Bad Case PATCH updates only the Bad Case record.
- M8.5 Bad Case to pending-review draft API is defined.
- Bad Case-generated candidates are written to ignored local candidate storage.
- Bad Case-generated candidates remain `pending_review`.
- P1-M9 full-chain verification test is defined.
- P1-M9.5 public dataset evaluation test is defined.
- `samples/public_dataset_eval_sample.json` contains only a small public converted sample.
- Full public dataset files are not committed.
- P1-M10 legacy RAG import endpoints are defined.
- Legacy candidates are written to ignored local candidate storage.
- Legacy import metadata is written to ignored local storage.
- Trusted legacy candidates can become local RAG chunks.
- Review-required legacy candidates remain out of RAG.
- CustomerOpsAgent retrieval can return legacy chunks with source trace.
- Unified release verification confirms CustomerOpsAgent retrieval can return approved `chat_logs`, `public_dataset`, `legacy_rag`, and approved `bad_case` chunks through one response shape.
- P1-M12 advanced cleaning verification confirms sanitized messages include quality fields and summary metrics.
- P1-M12 extraction skips messages marked `suggested_action: drop`.
- P1-M13 manual cleaning verification confirms sanitized messages can be manually kept, edited, dropped, or marked needs-review without modifying raw batches.
- P1-M14 review console verification confirms candidate editing and approve/reject/needs-revision boundaries.
- P1-M15 final release verification confirms the full high-quality loop from import through Bad Case draft creation.
- No Bad Case automatic approval, direct existing candidate mutation, RAG chunk mutation, RAG rebuild, database, ORM, vector store, embedding model, real LLM, or multimodal workflow has been implemented.
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

Submit a Bad Case:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/bad-cases `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"retrieval_id":"retrieval_xxx","user_query":"Where is my order?","agent_answer":"Your package should arrive soon.","issue_type":"wrong_answer","severity":"medium"}'
```

List Bad Cases:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/bad-cases
```

Update a Bad Case:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/bad-cases/{bad_case_id} `
  -Method Patch `
  -ContentType 'application/json' `
  -Body '{"status":"triaged","review_note":"Confirmed retrieval miss.","resolution_type":"retrieval_tuning"}'
```

Create a pending-review draft from a Bad Case:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/bad-cases/{bad_case_id}/create-draft `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"question":"Where is my order?","answer":"Please provide your order number or tracking number. If tracking is unavailable, we will escalate this to a human agent.","intent":"order_status","tags":["order","tracking","handoff"],"risk_level":"medium","quality_score":0.7,"knowledge_type":"faq"}'
```

## Phase-Prefixed Tag Naming Rule

Historical tags are kept as-is. Do not rewrite old tags.

Starting from P1-M9, all new tags must use phase-prefixed naming.

P1:

- `p1-m9-phase-one-release-freeze`
- `p1-m9.5-public-dataset-eval`
- `p1-m10-legacy-rag-migration`
- `p1-m11-unified-rag-release`
- `p1-m12-advanced-data-cleaning`
- `p1-m13-chinese-admin-console`
- `p1-m14-review-quality-console`
- `p1-m15-high-quality-datahub-release`
- `p1-m15.5-frontend-ux-cleanup-boundary-review`
- `p1-m15.6-render-deployment-config`

P2:

- `p2-m1-material-ingestion`
- `p2-m2-multimodal-understanding`
- `p2-m3-multimodal-review`
- `p2-m4-multimodal-rag`

P3:

- `p3-m1-training-dataset-export`
- `p3-m2-finetune-dataset-export`

P4:

- `p4-m1-mcp-tool-layer`
- `p4-m2-agent-cluster-integration`

## Next Suggested Stage

P1 high-quality text data governance is complete.

Recommended option:

- Pause feature development.
- Prepare P1-P4 project retrospective, architecture walkthrough, and resume/project explanation materials.

Before P2 starts:

- Confirm Phase 2 material ingestion scope.
- Confirm whether multimodal storage, OCR, Caption, and SKU binding are still only roadmap or ready to implement.
- Confirm the next phase-prefixed tag name.

P1-M11 does not implement multimodal retrieval, MCP, model fine-tuning, or Phase 2/3/4.

Phase 2 AI Material Center, Phase 3 dataset export, and Phase 4 MCP are now documented as formal roadmap phases, but they are not the next implementation stage.

## P1-M13 Chinese Admin Console And Manual Cleaning Workbench

Completed in this checkpoint:

- Chinese DataHub admin console.
- P1/P2/P3/P4 capability cards.
- P2/P3/P4 cards marked as Roadmap / not connected.
- Manual cleaning workbench for sanitized messages.
- Manual cleaning API:
  - `PATCH /api/sanitized/{batch_id}/messages/{message_id}/manual-clean`
- Manual cleaning records under `backend/storage/manual_cleaning_records/`.
- Extraction uses manual cleaning actions:
  - `drop` and `needs_review` are skipped.
  - `keep_edited` uses manually cleaned content.
  - `keep` uses current sanitized content.
- Cleaner-facing guide added at `docs/19_MANUAL_CLEANING_GUIDE.md`.

Still forbidden:

- Do not implement P1-M14 full knowledge review quality console before it is explicitly started.
- Do not implement P1-M15 final acceptance before it is explicitly started.
- Do not implement Phase 2, Phase 3, or Phase 4 early.
- Do not connect real vector databases, embeddings, ORM, real LLM, MCP, or multimodal pipelines in this checkpoint.

Next recommended stage:

- P1-M14 Knowledge Review Quality Console.

## P1-M14 Knowledge Review Quality Console

Completed in this checkpoint:

- Chinese knowledge review workbench in the DataHub admin console.
- Local frontend filtering for knowledge candidates by status, source type, quality level, intent, and keyword.
- Candidate editing through existing candidate APIs.
- Review actions through existing review APIs:
  - approve
  - reject
  - needs_revision
- Reviewer and review note support.
- Source trace, quality score, cleaning issues, and risk flags displayed in the UI.
- Reviewer-facing guide added at `docs/20_KNOWLEDGE_REVIEW_GUIDE.md`.

Still forbidden:

- Do not implement P1-M15 final high-quality release before explicitly started.
- Do not implement Phase 2, Phase 3, or Phase 4 early.
- Do not connect real vector databases, embeddings, ORM, database, real LLM, MCP, or multimodal pipelines.

Next recommended stage:

- P1-M15 High-quality DataHub Final Release.

## Completed In P1-M15

- Added final P1 high-quality release verification.
- Updated `/health` to report `P1-M15`.
- Added `backend/tests/test_p1_high_quality_datahub_release.py`.
- Verified the full high-quality loop:
  - import
  - advanced machine cleaning
  - manual cleaning
  - knowledge extraction
  - knowledge review
  - local RAG build
  - CustomerOpsAgent restricted retrieval
  - Bad Case feedback
  - Bad Case to pending-review draft
  - legacy RAG trusted import
- Upgraded the Chinese admin console to a unified dark AgentOps / data governance product style.
- Kept P1/P2/P3/P4 capability cards visible.
- Kept P2/P3/P4 marked as Roadmap / not connected.
- Added final report at `docs/21_P1_HIGH_QUALITY_DATAHUB_RELEASE_REPORT.md`.
- Confirmed P1-M15 does not implement Phase 2, Phase 3, Phase 4, real vector database, embedding, database, ORM, real LLM, MCP, or CustomerOpsAgent repository changes.

## Current Final P1 Status

P1 is complete as a high-quality text customer service data governance platform with unified local RAG.

Recommended next move:

- Pause feature development.
- Manually browse the simplified Chinese dark frontend and capture screenshots if needed.
- Use `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md` as the project capability and boundary source of truth.
- Start P2-M1 only after a separate scope confirmation.

## Completed In P1-M15.5

- Simplified the Chinese dark admin console from a dense debugging-style page into a step-based workflow.
- Added frontend backend-connection status:
  - checking
  - connected
  - disconnected
- Added `/api/health` as a frontend-friendly health-check alias through the existing `/api` proxy path.
- Replaced the misleading P1 "enter module" behavior with a real scroll to the main workflow.
- Kept P2/P3/P4 buttons disabled and labeled as not connected Roadmap entries.
- Moved internal technical cards into a lower-priority advanced information section.
- Added project review and boundary documentation at `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md`.
- Confirmed no interview packaging, resume packaging, P2/P3/P4 implementation, vector database, embedding, database, ORM, real LLM, MCP, or CustomerOpsAgent repository change is included.

## Completed In P1-M15.6

- Fixed Render deployment configuration issue where Render could not find `requirements.txt`.
  - Root cause: Render Build Command `pip install -r requirements.txt` looked in the repository root, but DataHub keeps requirements at `backend/requirements.txt`.
- Created `.python-version` at repository root to pin Python to `3.11.9` (Render defaulted to 3.14.x which is untested).
- Added `pydantic` to `backend/requirements.txt` as an explicit dependency (directly imported by `backend/app/schemas.py`).
- Created `docs/23_RENDER_DEPLOYMENT_GUIDE.md` with the correct Render configuration.
- Updated `docs/08_DEV_STATUS.md` and `docs/09_STAGE_CHECKLIST.md`.
- Added Render deployment doc link to `README.md` and `README.en.md`.

### Correct Render Configuration

| Setting | Value |
|---|---|
| **Build Command** | `pip install -r backend/requirements.txt` |
| **Start Command** | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| **Root Directory** | (leave empty) |
| **Branch** | `main` |
| **Python Version** | 3.11.9 (via `.python-version`) |

### P1-M15.6 Boundaries

This is a deployment configuration fix only. No business logic, frontend, or backend API changes were made.

- Confirmed no business logic change.
- Confirmed no frontend change.
- Confirmed no P2/P3/P4 implementation.
- Confirmed no database, ORM, vector database, embedding, real LLM, MCP, or CustomerOpsAgent repository change.
- Confirmed no tag was created for this checkpoint (commit only).
- Confirmed `backend/storage/`, `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.

## Completed In P1-M15.7

- Completely redesigned the DataHub frontend from a single-page developer debug console into a multi-page product demo platform.
- Added React Router v6 with 6 pages:
  - 首页 (Home)
  - 客服文本中台 (P1, connected to real backend)
  - AI 素材中心 (P2, product shell, disabled)
  - 数据资产复用 (P3, product shell, disabled)
  - MCP + Agent 集群 (P4, product shell, disabled)
  - 高级信息 (Advanced, developer info)
- Added top navigation bar with backend connection status indicator.
- Redesigned P1 page as a 5-step user workflow with step indicator.
- Added file upload support via file picker and drag-and-drop.
- Added "使用示例数据" (Use Sample Data) button for one-click demo.
- Added "高级模式：粘贴 JSON" (Advanced: Paste JSON) as a collapsed option.
- Fixed Vercel → Render API connection:
  - Created `api.ts` with dynamic `API_BASE_URL` detection.
  - Production: reads `VITE_API_BASE_URL` env var → falls back to `https://datahub-jr8x.onrender.com`.
  - Local: automatically uses `http://127.0.0.1:8000`.
- Added CORS middleware to FastAPI backend allowing localhost and Vercel origins.
- Designed P2/P3/P4 pages as complete product shells with disabled buttons labeled "P2 后接入" / "P3 后接入" / "P4 后接入".
- Moved developer/technical info to the separate "高级信息" page.
- Updated README.md and README.en.md with live demo URLs.
- Created docs/24_FRONTEND_PRODUCT_UX_REDESIGN.md and docs/25_VERCEL_DEPLOYMENT_GUIDE.md.
- Updated docs/08_DEV_STATUS.md and docs/09_STAGE_CHECKLIST.md.

### P1-M15.7 Boundaries

This is a frontend UX redesign and deployment link fix. No P2/P3/P4 backend development was done.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no real multimodal, sales export, fine-tuning export, MCP, vector database, embedding, real LLM, database, or ORM.
- Confirmed no CustomerOpsAgent repository change.
- Confirmed no tag was created (commit only).
- Confirmed `backend/storage/`, `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.

## Completed In P1-M15.8

- Simplified homepage Hero section:
  - Removed three duplicate action buttons (开始体验, 上传客服数据, 使用示例数据).
  - Hero now only communicates what DataHub is and its value proposition.
  - Added a concise status indicator area showing current access, future roadmap, and backend service state.
- Unified homepage entry points:
  - Four capability cards are now the sole entry points into workspaces.
  - P1 card ("客服文本中台") is active with "进入工作台" button.
  - P2/P3/P4 cards are disabled with "暂未接入" labels.
- Removed "高级信息" from public navigation:
  - Deleted the `/advanced` route from the React Router.
  - The AdvancedPage component is no longer imported or routed.
- Removed developer technical details from public UI:
  - API Base URL no longer displayed in any public-facing page.
  - local JSON storage, mock retrieval, no vector DB, no embedding, no real LLM, no DB/ORM, no MCP details removed from public view.
  - Backend status now shows user-friendly text only: 服务正常 / 连接中 / 服务暂不可用，可能正在冷启动.
- P1 workbench (`/p1-text-hub`) remains fully functional.
- P2/P3/P4 pages retain complete product shells with all buttons disabled and marked as future access.
- Updated README.md, README.en.md, and docs to reflect homepage UX changes.
- Technical boundaries remain documented in docs, not exposed in public frontend.

### P1-M15.8 Boundaries

This is a homepage UX cleanup and public surface cleanup only. No business logic, backend API, or P2/P3/P4 backend development was done.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no real multimodal, sales export, fine-tuning export, MCP, vector database, embedding, real LLM, database, or ORM.
- Confirmed no CustomerOpsAgent repository change.
- Confirmed no tag was created (commit only).
- Confirmed `backend/storage/`, `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed P1 workbench remains fully operational.
- Confirmed P2/P3/P4 pages retain complete product shells.
- Confirmed README was not turned into a stage log.
