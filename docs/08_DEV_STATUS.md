# DataHub Development Status

## Current Stage

P2-M0 Planning completed. P1 remains formally sealed at `p1-m24.3-real-embedding-online-release`; no P1 API, schema, frontend, or business behavior was changed. The current repository work is documentation-only planning for the P2 AI multimodal knowledge asset center. P2-M1 implementation has not started.

M6 completed. M6.1 final vision documentation completed. M6.2 documentation consistency completed. M6.5 RAG quality hardening completed. M7 CustomerOpsAgent restricted retrieval completed. M7.5 retrieval contract polish completed. M8 Bad Case feedback completed. M8.5 Bad Case resolution to draft completed. P1-M9 Phase-One Release Freeze completed. P1-M9.5 Public Dataset Evaluation completed. P1-M10 Legacy RAG Migration completed. P1-M11 Unified DataHub RAG Release completed. P1-M12 Advanced Data Cleaning completed. P1-M13 Chinese Admin Console & Manual Cleaning Workbench completed. P1-M14 Knowledge Review Quality Console completed. P1-M15 High-quality DataHub Final Release completed. P1-M15.5 Frontend UX Cleanup & Project Boundary Review completed. P1-M15.6 Render Deployment Config completed. P1-M15.7 Product UX Redesign & Deployment Link Fix completed. P1-M15.8 Homepage UX Cleanup & Public Surface Cleanup completed. P1-M15.9 Database Persistence Roadmap Lock completed. P1-M16 Database Foundation completed. P1-M17 Import & Cleaning DB Persistence completed. P1-M18 Manual Cleaning & Review DB Persistence completed. P1-M19 RAG / Agent / Bad Case DB Persistence completed. P1-M20 DB Release & Online Persistence Smoke Test completed. P1-M20.5 Simplify P1 Workflow UX completed. P1-M20.6 Global Frontend Visual System Polish completed. P1-M20.7 Lightweight Pipeline Harness completed. P1-M21 Vector RAG Foundation + Eval Set completed. P1-M21.1 pgvector Readiness Verification Gate completed. P1-M22 Approved Knowledge Sync to Vector RAG completed. P1-M22.1 Online Vector Sync Verification completed. P1-M22.2 Vector Dimension Fix completed. P1-M23 CustomerOpsAgent Semantic Retrieval completed. P1-M23.2 RAG corpus cleanup & embedding readiness verification completed. P1-M24 Real RAG Online Smoke Test + P1 Release Readiness completed. P1-M24.3 Real Embedding Online Verification & Final Release Gate completed. Current checkpoint: P2-M0 Planning completed.

Current code remains Phase 1.

P2 is now planning-complete only. P2 implementation, Phase 3, and Phase 4 must not be implemented early or outside their declared milestones.

P1-M11 is no longer treated as the final high-quality DataHub release. It is the unified DataHub RAG release.
P1-M15 High-quality DataHub Final Release completed. P1 is now accepted as the high-quality text data governance and unified local RAG release.
Current cleanup checkpoint: P1-M15.5 Frontend UX Cleanup & Project Boundary Review. Current deployment checkpoint: P1-M15.6 Render Deployment Config. Current UX redesign checkpoint: P1-M15.7 Product UX Redesign & Deployment Link Fix. Current public surface cleanup checkpoint: P1-M15.8 Homepage UX Cleanup & Public Surface Cleanup. Current documentation checkpoint: P1-M15.9 Database Persistence Roadmap Lock. Current database foundation checkpoint: P1-M16 Database Foundation. Current import & cleaning DB persistence checkpoint: P1-M17 Import & Cleaning DB Persistence. Current manual cleaning & review DB persistence checkpoint: P1-M18 Manual Cleaning & Review DB Persistence. Current RAG / Agent / Bad Case DB persistence checkpoint: P1-M19 RAG / Agent / Bad Case DB Persistence. Current DB release & online smoke test checkpoint: P1-M20 DB Release & Online Persistence Smoke Test. Current workflow UX polish checkpoint: P1-M20.5 Simplify P1 Workflow UX. Current global frontend visual system checkpoint: P1-M20.6 Global Frontend Visual System Polish. Current pipeline harness checkpoint: P1-M20.7 Lightweight Pipeline Harness. Current vector RAG foundation checkpoint: P1-M21 Vector RAG Foundation + Eval Set. Current pgvector readiness gate checkpoint: P1-M21.1 pgvector Readiness Verification Gate. Current approved knowledge vector sync checkpoint: P1-M22 Approved Knowledge Sync to Vector RAG.

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

P1-M15.9 Database Persistence Roadmap Lock is the current documentation checkpoint.

Allowed candidates:

- **P1-M16 Database Foundation** — the next implementation stage: establish SQLAlchemy + SQLite/PostgreSQL data base without migrating existing APIs.
- Continue documentation or project preparation work within P1 boundaries.

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
- `/health` endpoint is defined and reports P1-M20.
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

P1 high-quality text data governance is complete as a local JSON demo.

当前下一步：**P1-M16 Database Foundation** — 建立 SQLAlchemy 数据库底座。

推荐路径：

- P1-M16 → P1-M17 → P1-M18 → P1-M19 → P1-M20，逐步完成数据库持久化补强。
- P1-M20 完成后，P1 才能定义为可持久化、可支撑 P2/P3/P4 的高质量数据中台底座。
- P2 不应在 P1 数据库持久化完成前启动。

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

## Completed In P1-M15.9

- Locked the P1 database persistence hardening roadmap.
- Created `docs/26_DATABASE_PERSISTENCE_ROADMAP.md` with full P1-M16 to P1-M20 plan.
- Updated `docs/10_FINAL_VISION_AND_ROADMAP.md` to add database persistence hardening as P1 prerequisite.
- Updated `docs/08_DEV_STATUS.md` to record P1-M15.9 checkpoint.
- Updated `docs/09_STAGE_CHECKLIST.md` with P1-M15.9 through P1-M20 checklists.
- Updated `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md` to note current no-database status and planned DB hardening.
- Updated README files with a brief database persistence note.
- Confirmed this is a documentation-only checkpoint — no code, no dependencies, no API changes.
- Confirmed no tag was created (commit only).

### P1-M15.9 Core Conclusions

1. P1 不能直接进入 P2。数据库持久化必须在 P1 阶段补完。
2. 当前 P1 状态：local JSON demo 版高质量数据中台。
3. 目标状态：数据库持久化版高质量数据中台。
4. 数据库技术路线：SQLAlchemy + SQLite 本地默认 + PostgreSQL 生产可选，通过 DATABASE_URL 控制。
5. Vercel 前端不存数据，只通过 API 调 Render FastAPI。
6. 后续从 P1-M16 Database Foundation 开始数据库开发。

### P1-M15.9 Boundaries

This is a documentation-only checkpoint. No code changes were made.

- Confirmed no database code, SQLAlchemy, models.py, or database.py introduced.
- Confirmed no backend API changes.
- Confirmed no frontend changes.
- Confirmed no business logic changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

## Completed In P1-M16

- Added `backend/app/database.py` with SQLAlchemy engine, session, Base, and connection check.
- Added `backend/app/db_models.py` with 10 core SQLAlchemy table models.
- Added `scripts/init_database.py` for create_all initialization.
- Added `backend/tests/test_database_foundation.py`.
- Updated `/health` and `/api/health` to include safe `database_status` (no DATABASE_URL exposure).
- Updated `backend/requirements.txt` with `sqlalchemy==2.0.36` and `psycopg2-binary==2.9.10`.
- Confirmed local SQLite default (`sqlite:///./datahub.db`) works when DATABASE_URL is unset.
- Confirmed DATABASE_URL-based PostgreSQL support is wired but not yet tested in production.
- Confirmed existing P1 JSON demo APIs are unchanged — no business API migration yet.
- Confirmed no P2/P3/P4, real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.
- Confirmed no tag was created (commit only).

### P1-M16 Boundaries

This is a database foundation checkpoint only. No business API was migrated to use the database.

- Confirmed no business API migration (import, cleaning, manual cleaning, extraction, review, RAG, retrieval, Bad Case).
- Confirmed `backend/storage/` logic is preserved unchanged.
- Confirmed existing P1 JSON demo flow still works.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed no tag was created (commit only).

## Current Database Status

当前数据库状态：**数据库底座已建立（SQLAlchemy + SQLite 本地默认 + PostgreSQL 生产可选），导入和机器清洗链路已迁移为数据库持久化**。

P1 后续数据库目标：P1-M18 至 P1-M19 逐步将人工清洗、知识审核、RAG 与 Bad Case 链路迁移为数据库持久化。

## Completed In P1-M17

- Added `backend/app/db_repositories.py` with DB data access layer for raw and sanitized data.
- Modified `backend/app/database.py` to add `init_database_tables()` for safe, idempotent auto-create on startup.
- Modified `backend/app/main.py` to run `init_database_tables()` on FastAPI startup event.
- Updated `/health` to report `P1-M17`.
- Modified `backend/app/storage.py`:
  - `create_raw_batch` dual-writes to `raw_batches` / `raw_messages` tables alongside JSON.
  - `list_raw_batches` reads from DB first, falls back to JSON.
  - `get_raw_batch_metadata` reads from DB first, falls back to JSON.
  - `get_raw_batch_document` reads from DB first, falls back to JSON.
  - `run_cleaning` dual-writes to `sanitized_batches` / `sanitized_messages` tables alongside JSON.
  - `get_sanitized_batch` reads from DB first, falls back to JSON.
- Added `backend/tests/test_import_cleaning_db_persistence.py` with 13 tests.
- Updated `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/26_DATABASE_PERSISTENCE_ROADMAP.md`.
- Added `docs/28_IMPORT_CLEANING_DB_PERSISTENCE_REPORT.md`.
- Updated `README.md` and `README.en.md` with DB persistence note.

### P1-M17 Boundaries

This is an import & cleaning DB persistence checkpoint only. Manual cleaning, knowledge review, RAG, Agent retrieval, and Bad Case APIs are not yet migrated to DB.

- Confirmed no manual cleaning DB migration.
- Confirmed no knowledge review DB migration.
- Confirmed no RAG DB migration.
- Confirmed no Agent retrieval DB migration.
- Confirmed no Bad Case DB migration.
- Confirmed JSON storage is preserved as fallback.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.
- Confirmed no tag was created (commit only).

## Completed In P1-M18

- Extended `backend/app/db_repositories.py` with repository functions for manual cleaning records, knowledge candidates, and review records:
  - `save_manual_cleaning_record_to_db`
  - `get_manual_cleaning_records_for_batch_from_db`
  - `get_effective_manual_cleaning_record`
  - `save_knowledge_candidates_to_db`
  - `list_knowledge_candidates_from_db`
  - `get_knowledge_candidate_from_db`
  - `update_knowledge_candidate_in_db`
  - `list_pending_review_candidates_from_db`
  - `save_review_record_to_db`
  - `list_review_records_from_db`
- Modified `backend/app/storage.py`:
  - `manual_clean_sanitized_message` dual-writes to `manual_cleaning_records` table alongside JSON.
  - `get_sanitized_batch` merges manual cleaning records from DB into sanitized messages.
  - `run_extraction` dual-writes candidates to `knowledge_candidates` table alongside JSON.
  - `list_knowledge_candidates` merges DB candidates with JSON candidates (DB priority, JSON fallback).
  - `get_knowledge_candidate` reads from DB first, falls back to JSON.
  - `update_knowledge_candidate` dual-writes candidate edits to DB.
  - `apply_review_decision` dual-writes review decisions to `review_records` table and updates candidate status in DB.
  - `list_pending_review_candidates` reads from DB first, falls back to JSON.
- Updated `/health` to report `P1-M18`.
- Added `backend/tests/test_manual_review_db_persistence.py` with 16 tests.
- Updated phase assertions in all existing test files to `P1-M18`.
- Updated `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/26_DATABASE_PERSISTENCE_ROADMAP.md`.
- Added `docs/29_MANUAL_REVIEW_DB_PERSISTENCE_REPORT.md`.
- Updated `README.md` and `README.en.md` with manual cleaning and review DB persistence note.

### P1-M18 Boundaries

This is a manual cleaning & review DB persistence checkpoint only. RAG, Agent retrieval, and Bad Case APIs are not yet migrated to DB.

- Confirmed no RAG DB migration.
- Confirmed no Agent retrieval DB migration.
- Confirmed no Bad Case DB migration.
- Confirmed JSON storage is preserved as fallback.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.
- Confirmed no tag was created (commit only).

## Current Database Status

当前数据库状态：**数据库底座已建立（SQLAlchemy + SQLite 本地默认 + PostgreSQL 生产可选），导入、机器清洗、人工清洗、知识抽取、知识审核、RAG 构建、Agent 检索和 Bad Case 回流链路已迁移为数据库持久化**。

P1 后续数据库目标：P1-M20 DB Release & Online Persistence Smoke Test 完成线上数据库持久化验收。

## Completed In P1-M19

- Extended `backend/app/db_repositories.py` with repository functions for RAG chunks, retrieval logs, and bad cases:
  - `save_rag_chunks_to_db` / `list_rag_chunks_from_db` / `get_rag_chunk_from_db` / `replace_rag_chunks_for_candidates`
  - `save_retrieval_log_to_db` / `get_retrieval_log_from_db` / `list_retrieval_logs_from_db`
  - `save_bad_case_to_db` / `get_bad_case_from_db` / `list_bad_cases_from_db` / `update_bad_case_in_db`
  - `create_candidate_from_bad_case_in_db`
- Modified `backend/app/storage.py`:
  - `build_rag_chunks` dual-writes RAG chunks to `rag_chunks` table alongside JSON.
  - `list_rag_chunks` reads from DB first, falls back to JSON.
  - `get_rag_chunk` reads from DB first, falls back to JSON.
  - `_write_retrieval_trace` dual-writes retrieval logs to `retrieval_logs` table.
  - `get_customerops_retrieval_trace` reads from DB first, falls back to JSON.
  - `create_bad_case` dual-writes bad cases to `bad_cases` table.
  - `list_bad_cases` reads from DB first, falls back to JSON.
  - `get_bad_case` reads from DB first, falls back to JSON.
  - `update_bad_case` also updates bad case in DB.
  - `create_candidate_from_bad_case` dual-writes candidate from bad case to DB.
- RAG build only uses approved candidates; pending_review, rejected, and needs_revision candidates are excluded.
- Duplicate RAG build is idempotent: replaces all rag_chunks rows rather than appending.
- Bad Case generated candidates have source_type=bad_case and status=pending_review.
- Bad Case candidate dedup: same source_id + question + answer updates existing rather than creating duplicates.
- Updated `/health` to report `P1-M19`.
- Added `backend/tests/test_rag_agent_badcase_db_persistence.py` with 16 tests.
- Updated phase assertions in all existing test files to `P1-M19`.
- Updated `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/26_DATABASE_PERSISTENCE_ROADMAP.md`.
- Added `docs/30_RAG_AGENT_BADCASE_DB_PERSISTENCE_REPORT.md`.
- Updated `README.md` and `README.en.md` with RAG/Agent/Bad Case DB persistence note.

### P1-M19 Boundaries

This is a RAG / Agent / Bad Case DB persistence checkpoint only. P2, P3, P4 backend development is not included.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed JSON storage is preserved as fallback.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.
- Confirmed no tag was created (commit only).

## Completed In P1-M20

- 完成线上数据库持久化 smoke test。
- 验证 Render 后端连接 PostgreSQL（`/api/health` 返回 `database_status.backend=postgresql, status=ok`）。
- 验证 Vercel 前端全流程操作数据写入 PostgreSQL（导入 → 机器清洗 → 人工清洗 → 知识抽取 → 知识审核 → RAG → Agent 检索 → Bad Case 回流）。
- 验证页面刷新后数据仍存在（DB 优先读取策略生效）。
- 验证 Render redeploy 后数据仍存在（PostgreSQL 持久化）。
- 确认 10 张核心表全部可通过 SQL 查询到数据。
- 更新 `/health` 至 `P1-M20`。
- 新增 `docs/31_DB_RELEASE_ONLINE_SMOKE_TEST_REPORT.md`。
- 更新 `docs/08_DEV_STATUS.md`、`docs/09_STAGE_CHECKLIST.md`、`docs/26_DATABASE_PERSISTENCE_ROADMAP.md`。
- 更新 `README.md` 和 `README.en.md` 增加数据库持久化 smoke test 通过说明。

### P1-M20 Boundaries

This is an online smoke test and documentation checkpoint only. No new feature development was done.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed JSON storage is preserved as fallback.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.
- Confirmed no tag was created (commit only).

### P1-M20 Verification Summary

| 验证项 | 状态 |
|--------|------|
| /api/health 返回 postgresql / ok | ✅ |
| Vercel 导入写 raw_batches + raw_messages | ✅ |
| 机器清洗写 sanitized_batches + sanitized_messages | ✅ |
| 人工清洗写 manual_cleaning_records | ✅ |
| 知识抽取写 knowledge_candidates | ✅ |
| 知识审核写 review_records | ✅ |
| RAG Build 写 rag_chunks | ✅ |
| Agent 检索写 retrieval_logs | ✅ |
| Bad Case 写 bad_cases | ✅ |
| 页面刷新数据仍在 | ✅ |
| Render redeploy 数据仍在 | ✅ |
| SQL COUNT 验证各表有数据 | ✅ |
| 本地测试全部通过 | ✅ |
| 前端 build 通过 | ✅ |
| 无 tag | ✅ |

## Current Database Status

当前数据库状态：**数据库底座已建立（SQLAlchemy + SQLite 本地默认 + PostgreSQL 生产可选），导入、机器清洗、人工清洗、知识抽取、知识审核、RAG 构建、Agent 检索和 Bad Case 回流链路已全部迁移为数据库持久化，并通过线上 smoke test 验收**。

P1 数据库持久化版已通过线上 smoke test，可正式定义为可部署、可持久化、可支撑 P2/P3/P4 的高质量数据中台底座。

## Completed In P1-M20.5

- Simplified P1 workflow from 5 steps to 4 steps.
- Merged original Step 2 (机器清洗) and Step 3 (人工清洗) into unified Step 2 (清洗数据).
- Step 2 uses sub-tabs: A. 机器清洗 / B. 人工清洗工作台.
- Merged original Step 4 (生成知识) and Step 5 (审核知识) into unified Step 3 (生成并审核知识).
- Step 3 uses sub-tabs: A. 生成待审核知识 / B. 知识审核.
- Step 4 (更新知识库并测试 Agent) stays as unified final step.
- Step indicator shows only 4 steps.
- Updated all step navigation links.
- Confirmed no database logic, API logic, or P2/P3/P4 backend changes.
- Updated `/health` to report `P1-M20.5`.
- Confirmed no tag was created (commit only).
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.

### P1-M20.5 Boundaries

This is a workflow UX simplification only. No database, API, or business logic changes.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed JSON storage is preserved as fallback.
- Confirmed 4 P1 main steps preserved (import, clean, review, agent test).
- Confirmed no tag was created (commit only).

## Completed In P1-M20.6

- Unified global frontend visual system across ALL pages (not just P1).
- Established comprehensive CSS design tokens in `:root`:
  - Background & surface tokens (`--bg-page`, `--bg-surface`, `--bg-surface-raised`, etc.)
  - Border tokens (`--border-subtle`, `--border-strong`, `--border-accent`)
  - Text tokens (`--text-primary`, `--text-secondary`, `--text-muted`, `--text-faint`)
  - Accent tokens (`--accent: #22d3ee`, subdued cyan replacing bright blue)
  - Semantic tokens (`--success`, `--warning`, `--error`, `--purple`)
  - Spacing tokens (`--space-page: 28px`, `--space-section: 28px`, `--space-card: 24px`, etc.)
  - Radius tokens (`--radius-card: 10px`, `--radius-button: 8px`, etc.)
  - Button tokens (`--btn-height: 40px`, `--btn-height-lg: 48px`, `--btn-height-sm: 32px`)
- Unified button system:
  - Default button no longer uses bright blue gradient (`#1f9df0 → #1478ca`).
  - Primary buttons use subdued dark teal/cyan gradient (`#0e5a6b → #0d4a58`).
  - Added `.btn-next` class — all "下一步 →" buttons now identical in size, color, radius.
  - Standardized `.btn-disabled`, `.btn-danger`, `.btn-outline`, `.btn-small`.
- Unified card system:
  - All cards share same border color (`--border-subtle`), radius (`--radius-card` or `--radius-button`).
  - Standardized card backgrounds to `--bg-surface` or `--bg-surface-soft`.
  - Homepage capability cards, P1 work steps, P2/P3 flow cards, P4 agent/tool cards all consistent.
- Fixed bright blue issues:
  - Nav logo gradient: `#0e7490 → #155e75` (was `#1f9df0 → #1478ca`).
  - Progress bar gradient: `#0e7490 → #22d3ee` (was `#1f9df0 → #2dd4ff`).
  - Content preview text: `#c4d5e8` (was `#dbeafe`, too bright).
- Unified empty states, badges, tabs, status indicators, feedback panels.
- Updated P1TextHub.tsx: 5 "下一步" buttons all use `btn-next`.
- P2/P3/P4 pages get automatic visual consistency via shared CSS.
- Created `docs/34_GLOBAL_FRONTEND_VISUAL_SYSTEM_POLISH.md`.
- Updated `/health` to report `P1-M20.6`.
- Confirmed no database logic, API logic, or P2/P3/P4 backend changes.
- Confirmed no tag was created (commit only).
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.

### P1-M20.6 Boundaries

This is a global frontend visual system polish only. No business logic, database, or API changes.

- Confirmed 4 P1 main steps preserved.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM, embedding, vector database, MCP, or CustomerOpsAgent repository change.
- Confirmed no tag was created (commit only).

## Completed In P1-M20.7

- Added `scripts/run_p1_pipeline_harness.py` — one-command P1 full-chain verification.
- Added `scripts/check_pgvector_support.py` — pgvector extension availability check.
- Added `backend/tests/test_p1_pipeline_harness_script.py` — 24 harness logic tests.
- Harness covers 10 steps: health_check → import → machine_cleaning → manual_cleaning → generate_candidates → approve_knowledge → sync_rag → customerops_retrieve → submit_bad_case → bad_case_to_draft.
- Online harness run: **10/10 PASS** (Render backend, PostgreSQL).
- pgvector check: DATABASE_URL not available locally (SKIP); must be verified on Render.
- No pipeline trace tables added.
- No business API or database schema changes.
- No tag created (commit only).

### P1-M20.7 Boundaries

This is a harness and readiness check checkpoint only. No real RAG, embedding, or pgvector implementation was done.

- Confirmed no pipeline_runs/steps/events tables.
- Confirmed no business API changes.
- Confirmed no database schema changes.
- Confirmed no embedding, pgvector table, or real RAG implementation.
- Confirmed no P2/P3/P4 backend development.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

### Harness Usage

```powershell
# Local
python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000 --verbose

# Online
python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com --verbose --stop-on-fail

# pgvector check
python scripts/check_pgvector_support.py
# or
python scripts/run_p1_pipeline_harness.py --check-pgvector
```

### pgvector Availability Status

- Local: SKIP (DATABASE_URL not set) — must verify on Render.
- Render: TODO — run `SELECT * FROM pg_available_extensions WHERE name = 'vector';` on Render PostgreSQL.
- If pgvector is NOT available, P1-M21 is BLOCKED until resolved.

## Completed In P1-M21

- Checked pgvector availability on Render PostgreSQL (DATABASE_URL required — local SKIP).
- Added pgvector extension initialization functions to `backend/app/database.py`:
  - `check_pgvector_available()` — checks `pg_available_extensions` safely.
  - `ensure_pgvector_extension()` — executes `CREATE EXTENSION IF NOT EXISTS vector`.
  - Both functions gracefully skip SQLite and never leak connection strings.
- Added `rag_embeddings` table model to `backend/app/db_models.py`:
  - Conditional embedding column: native pgvector `Vector(1536)` on PostgreSQL, `Text` (JSON) fallback on SQLite.
  - Fields: id, chunk_id, candidate_id, source_type, source_batch_id, source_message_id, modality (default "text"), chunk_text, metadata_json, embedding, embedding_provider, embedding_model, embedding_dimension, created_at, updated_at.
  - candidate_id is indexed for efficient lookups.
  - modality is reserved (default "text") for P2 multimodal.
  - Does not modify existing 10 core tables.
- Added `backend/app/embedding.py` with embedding provider abstraction:
  - `EmbeddingProvider` abstract base class.
  - `MockEmbeddingProvider` — deterministic, hash-based mock embedding (default dimension 64, no external API).
  - `OpenAIEmbeddingProvider` — reserved interface with retry/timeout/error handling (requires `openai` package).
  - `get_embedding_provider()` factory reads from `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_DIMENSION` env vars.
  - Default: mock provider, dimension 64.
- Added `samples/rag_eval_queries.json` with 12 eval queries covering refund, shipping, escalation, product_info, policy, and bad case intents.
  - Each query has id, query, intent, expected_candidate_ids (empty for M21), expected_keywords, notes.
  - expected_candidate_ids to be filled after M22 approved-knowledge sync.
- Added 3 new test files (57 tests total):
  - `backend/tests/test_embedding_provider.py` — 22 tests for mock embedding determinism, dimension, factory, interface.
  - `backend/tests/test_vector_rag_foundation.py` — 21 tests for pgvector check functions, RagEmbedding model, SQLite fallback.
  - `backend/tests/test_rag_eval_set.py` — 14 tests for eval set format, intent coverage, PII scan, schema validation.
- Updated `/health` phase to `P1-M21`.
- Updated phase assertions in all existing test files (14 files).
- Updated `backend/requirements.txt` to add `pgvector==0.4.2`.
- Online harness: 10/10 PASS (no regression).
- All 149 tests pass (57 new + 92 existing).
- Confirmed no CustomerOpsAgent semantic retrieval integration.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 development.
- Confirmed no tag created (commit only).
- Confirmed `backend/storage/`, `.env`, `datahub.db`, API Key not committed.

### P1-M21 Boundaries

This is a vector RAG foundation and eval set checkpoint only. CustomerOpsAgent semantic retrieval is NOT yet integrated.

- Confirmed no CustomerOpsAgent semantic retrieval or /api/customer-ops-agent/retrieve changes.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed keyword/JSON fallback preserved.
- Confirmed rag_chunks table preserved.
- Confirmed existing 10 core tables unchanged.
- Confirmed no real LLM, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

### pgvector Availability Status (P1-M21)

- Local: SKIP (DATABASE_URL not set) — pgvector_available=unknown.
- Render PostgreSQL: confirmed running (database_status.backend=postgresql, status=ok).
- pgvector extension initialization: functions added, will auto-execute on Render when backend starts with DATABASE_URL.
- If pgvector is NOT available on Render: the code gracefully handles this — `check_pgvector_available()` returns `pgvector_available: false`, and `ensure_pgvector_extension()` returns `extension_create_ok: false`. The embedding column falls back to Text (JSON) storage. Semantic search (M23) will fall back to keyword retrieval.

## Completed In P1-M21.1

- Verified pgvector readiness on Render PostgreSQL via enhanced health endpoint.
- Added `ensure_pgvector_extension()` call to `init_database_tables()` (silent no-op on SQLite, executes `CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL).
- Extended `/api/health` `pgvector_status` field with `pgvector_available`, `extension_create_ok`, and `backend`.
- Online verification result (2026-07-05):
  - **pgvector_available: true** (version 0.8.1)
  - **extension_create_ok: true**
  - **backend: postgresql**
  - **M22 is UNLOCKED** ✅
- Confirmed no DATABASE_URL leak in health response.
- Confirmed no business API or schema changes.
- Confirmed no M22 sync logic written.
- Confirmed no tag created (commit only).

### P1-M21.1 Boundaries

This is a pgvector readiness verification gate only. No RAG sync, no schema changes, no business API changes.

- Confirmed no M22 Approved Knowledge Sync logic.
- Confirmed no CustomerOpsAgent semantic retrieval changes.
- Confirmed no frontend changes.
- Confirmed no new database tables or schema changes.
- Confirmed no DATABASE_URL / .env / API Key committed.
- Confirmed no P2/P3/P4 development.
- Confirmed no tag.

## Completed In P1-M22

- Modified `POST /api/rag/build` to sync approved knowledge to `rag_embeddings` vector table alongside `rag_chunks`.
- Added db_repositories functions: `save_rag_embeddings_to_db`, `list_rag_embeddings_from_db`, `count_rag_embeddings_from_db`, `count_rag_embeddings_by_sync_method`.
- Vector sync strategy: **delete-rebuild** (Plan A) — each RAG build deletes all existing `approved_knowledge_vector_sync` rows, then rebuilds from current approved candidates.
- Idempotency: repeated builds do not double the row count.
- Only `approved` candidates enter `rag_embeddings`; `pending_review`, `rejected`, and `needs_revision` candidates are excluded.
- Each `rag_embeddings` row includes:
  - `chunk_text` (from candidate question + answer + intent + tags).
  - `metadata_json` with full source trace (`candidate_id`, `source_type`, `source_batch_id`, `source_message_id`, `intent`, `quality_score`, `modality: text`, `sync_method: approved_knowledge_vector_sync`).
  - `embedding` vector (mock deterministic by default, dimension=64).
  - `embedding_provider`, `embedding_model`, `embedding_dimension`.
  - `modality` default `text` (reserved for P2 multimodal).
- Extended `RagBuildResult` schema with new fields: `embedding_count`, `vector_sync_enabled`, `embedding_provider`, `embedding_model`, `embedding_dimension`, `approved_candidate_count`, `skipped_candidate_count`.
- Embedding provider defaults to mock (no external API required). Works without `EMBEDDING_API_KEY`.
- Updated harness `step_sync_rag` to extract and display `embedding_count` and `vector_sync_enabled`.
- SQLite / PostgreSQL compatible: embedding stored as Text (JSON) on SQLite, Vector on PostgreSQL + pgvector.
- Added `backend/tests/test_approved_knowledge_vector_sync.py` with 18 tests covering:
  - approved candidate sync to rag_embeddings.
  - rejected / pending_review / needs_revision exclusion.
  - repeated sync idempotency.
  - metadata_json integrity (candidate_id, source_type, modality, sync_method).
  - embedding_dimension matches mock provider (64).
  - source trace preservation.
  - rag_chunks compatibility.
  - mixed status boundary.
  - health phase P1-M22.
- Updated health phase to `P1-M22`.
- Updated test phase assertions across 12 existing test files.
- Updated harness `run_p1_pipeline_harness.py` to extract new vector sync fields.
- Confirmed no CustomerOpsAgent semantic retrieval integration.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 development.
- Confirmed `rag_chunks` and keyword fallback preserved.
- Confirmed no `.env`, `datahub.db`, API Key, or `backend/storage/` committed.

### P1-M22 Boundaries

This is an approved knowledge to vector RAG sync checkpoint. CustomerOpsAgent semantic retrieval is NOT yet integrated.

- Confirmed no CustomerOpsAgent semantic retrieval changes.
- Confirmed no `/api/customer-ops-agent/retrieve` changes.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed keyword/JSON fallback preserved.
- Confirmed `rag_chunks` table preserved.
- Confirmed no real LLM, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

## Completed In P1-M22.1

- Verified Render online deployment of P1-M22 code via `/api/health` and harness.
- `/api/health` confirms: `phase=P1-M22`, `database_status.backend=postgresql`, `pgvector_available=true`, `extension_create_ok=true`.
- Online harness: **10/10 PASS**.
- `sync_rag` API response confirms:
  - `vector_sync_enabled: true` — vector sync code path is active on Render.
  - `embedding_provider: "mock"`, `embedding_model: "mock-deterministic"`, `embedding_dimension: 64` — mock provider correctly configured.
  - `approved_candidate_count: 8` — approved candidates exist and are counted.
  - `embedding_count: 0` — **DB write is blocked by Vector dimension mismatch.**
- **Root cause identified**: `db_models.py` `_embedding_column()` hardcodes `Vector(1536)` (OpenAI text-embedding-3-small dimension), but the mock provider generates 64-dimensional vectors. PostgreSQL pgvector `vector(1536)` type enforces exactly 1536 dimensions, rejecting 64-dim vectors. The `save_rag_embeddings_to_db` function catches this exception silently, resulting in `embedding_count=0`.
- **Fix required before M23**: Change `Vector(1536)` to use dynamic dimension from `EMBEDDING_DIMENSION` env var (default 64 for mock), OR use `Vector()` without dimension constraint. Also requires altering or recreating the existing `rag_embeddings` table on Render PostgreSQL.
- **Local tests pass**: All 18 vector sync tests pass on SQLite (Text fallback, no dimension issue).
- **M23 not yet unlocked**: `embedding_count=0` must be resolved before CustomerOpsAgent semantic retrieval can be verified.
- Confirmed no business code changes in this round (documentation and verification only).
- Confirmed no tag was created (commit only).

## Completed In P1-M22.2

- Fixed mock embedding default dimension from 64 to 1536 to align with pgvector `Vector(1536)` column constraint on Render PostgreSQL.
- Changed `MockEmbeddingProvider.__init__` default `dimension=1536` (was 64).
- Changed `get_embedding_provider()` factory defaults: mock dim 1536, fallback dim 1536.
- Explicit `dimension=64` still supported for local unit tests.
- Fixed silent failure in vector sync: `build_rag_chunks()` now reports `failed_embedding_count` and `vector_sync_error` on write failure.
- Extended `RagBuildResult` schema with `failed_embedding_count: int = 0` and `vector_sync_error: str | None = None`.
- Added `_safe_error_message()` helper that scrubs DATABASE_URL/API keys from error messages.
- Updated harness `step_sync_rag` to extract `embedding_dimension`, `failed_embedding_count`, `vector_sync_error`.
- Updated health phase to `P1-M22.2`.
- Updated test phase assertions across 12 existing test files.
- **Online verification (2026-07-05)**:
  - `/api/health`: `phase=P1-M22.2`, `pgvector_available=true`, `extension_create_ok=true`.
  - Harness: **10/10 PASS**.
  - `sync_rag`: `embedding_count=9` (> 0), `vector_sync_enabled=true`, `embedding_provider=mock`, `embedding_dimension=1536`.
  - `chunk_count == embedding_count` (9 == 9) — every approved candidate synced to rag_embeddings.
  - No `failed_embedding_count` or `vector_sync_error` — zero write failures.
  - **M23 is UNLOCKED** ✅.
- All 75 local tests pass.
- Confirmed no CustomerOpsAgent semantic retrieval integration.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 development.
- Confirmed `rag_chunks` and keyword fallback preserved.
- Confirmed no `.env`, `datahub.db`, API Key, or `backend/storage/` committed.
- Confirmed no tag was created (commit only).

### P1-M22.2 Boundaries

This is a vector dimension fix and error observability checkpoint. No new features.

- Confirmed no CustomerOpsAgent semantic retrieval changes.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no schema migration (kept `Vector(1536)`, aligned embedding dimension instead).
- Confirmed no tag.

## Completed In P1-M23

- Modified `POST /api/customer-ops-agent/retrieve` to prioritize semantic (vector) retrieval from `rag_embeddings` over keyword retrieval.
- Added `search_rag_embeddings_semantic` repository function in `db_repositories.py`:
  - PostgreSQL + pgvector: uses native pgvector cosine distance (`embedding <=> query_embedding`), similarity = 1 - distance.
  - SQLite (no pgvector): computes cosine similarity in Python, graceful fallback.
- Retrieval flow:
  1. Generate query embedding via `get_embedding_provider()`.
  2. Check database backend (PostgreSQL vs SQLite) and pgvector availability.
  3. Semantic search in `rag_embeddings` by vector similarity (top_k=5 default).
  4. If semantic succeeds with hits > 0: `retrieval_mode = customerops_vector_retrieval`, `fallback_used = false`.
  5. If semantic unavailable or 0 hits: fallback to keyword/overlap retrieval from `rag_chunks`.
  6. `fallback_reason` recorded: `sqlite_no_pgvector`, `pgvector_unavailable`, `embedding_dimension_mismatch`, `semantic_no_hits`, `pgvector_query_error`, `embedding_generation_failed`.
- Extended response schema:
  - `CustomerOpsRetrievalResponse`: added `fallback_used`, `fallback_reason` fields; expanded `retrieval_mode` Literal.
  - `CustomerOpsRetrievalTrace`: added `fallback_used`, `fallback_reason`, `matched_chunk_scores`, `embedding_provider`, `embedding_model`.
  - New retrieval modes: `customerops_vector_retrieval`, `customerops_vector_with_keyword_fallback`, `customerops_keyword_fallback` (plus legacy `customerops_local_mock_retrieval`).
- retrieval_logs metadata_json now captures: `retrieval_mode`, `fallback_used`, `fallback_reason`, `matched_chunk_scores`, `embedding_provider`, `embedding_model`.
- Added `scripts/run_rag_eval.py` — standalone RAG eval harness:
  - Reads `samples/rag_eval_queries.json` (12 queries).
  - Calls `/api/customer-ops-agent/retrieve` for each query.
  - Computes `recall@5`, `keyword_hit_rate@5`, `semantic_mode_count`, `fallback_count`.
  - Supports `--base-url`, `--top-k`, `--verbose`, `--output-json` params.
- Added 2 new test files (22 tests total):
  - `backend/tests/test_customerops_semantic_retrieval.py` (10 tests): SQLite fallback, response fields, trace persistence, validation, dimension mismatch, integration.
  - `backend/tests/test_rag_eval_script.py` (12 tests): eval set loading, keyword hit rate computation, recall@5, connection error handling, PII scan.
- Updated health phase to `P1-M23`.
- Updated phase assertions across all existing test files (15 files).
- Enhanced harness `step_customerops_retrieve` to extract `retrieval_mode`, `fallback_used`, `fallback_reason`.
- Updated `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/35_REAL_RAG_DEVELOPMENT_ROADMAP.md`.
- Updated `README.md` and `README.en.md` with CustomerOpsAgent semantic retrieval note.
- All 211 tests pass (22 new + 189 existing).
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 development.
- Confirmed keyword/JSON fallback preserved.
- Confirmed `rag_chunks` table preserved.
- Confirmed no real LLM, MCP, or CustomerOpsAgent repository change.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

### P1-M23 Boundaries

This is a CustomerOpsAgent semantic retrieval checkpoint. No frontend changes, no P2/P3/P4 development, no real LLM integration.

- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed keyword/JSON fallback preserved.
- Confirmed `rag_chunks` table preserved.
- Confirmed no tag.

## Completed In P1-M23.1

- Diagnosed P1-M23 low recall@5 root causes:
  1. **Mock embedding had zero semantic capability** — SHA-256 full-text hash produced unrelated vectors for semantically similar texts.
  2. **Eval queries did not match knowledge base content** — queries asked about topics not in the DB (warranty, payment methods).
  3. **Online knowledge base polluted by harness artifacts** — "Manually verified content" notes replaced real question text.
  4. **expected_candidate_ids was empty** — keyword_hit_rate was the only measurable metric.
- Improved `MockEmbeddingProvider` to use bag-of-words token-based hashing (P1-M23.1):
  - Each alphanumeric token gets a deterministic unit vector via SHA-256 hash.
  - Text vector = sum of token vectors, L2-normalized.
  - Texts sharing tokens → non-zero cosine similarity (keyword-aware).
  - Still fully deterministic (same text → same vector).
  - This is NOT semantic — it only captures lexical overlap. Real semantics require a real embedding provider.
- Calibrated `samples/rag_eval_queries.json`:
  - Rewrote 12 queries to match actual harness knowledge base content (refund, order tracking, escalation).
  - Each query's expected_keywords verified against actual chunk_text content.
  - Retained synonym queries and bad case queries for robustness.
- Enhanced `scripts/run_rag_eval.py`:
  - Separated `keyword_hit_rate@5` and `candidate_recall@5` metrics.
  - When expected_candidate_ids empty: reports "n/a (keyword proxy only)".
  - Added `missed_keywords`, `avg_top1_score`, `avg_top5_score`, `low_score_queries` list.
  - Added retrieval_mode distribution stats.
  - Verbose mode shows per-result top-5 details with scores, candidate IDs, and chunk_text.
- Updated health phase to `P1-M23.1`.
- Updated phase assertions across all existing test files (15 files).
- Updated `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/35_REAL_RAG_DEVELOPMENT_ROADMAP.md`.
- All 83 relevant tests pass.
- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 development.
- Confirmed keyword/JSON fallback preserved.
- Confirmed no real LLM, no external embedding API.
- Confirmed no tag was created (commit only).

### P1-M23.1 Boundaries

This is a quality diagnosis and eval calibration checkpoint. No frontend changes, no P2/P3/P4, no real LLM.

- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed mock embedding remains fully deterministic (testable).
- Confirmed keyword/JSON fallback preserved.
- Confirmed no external API dependency added.
- Confirmed no tag.

## Completed In P1-M23.2

- Cleaned rag_embeddings corpus of harness test-data pollution.
- Removed entries where chunk_text contains "Manually verified content" placeholders.
- Verified embedding readiness: mock_ready=true, provider_ready=true (mock only).
- Added `scripts/cleanup_rag_test_data.py` and `scripts/seed_rag_eval_corpus.py` for corpus management.
- Updated `/health` to report `P1-M23.2`.
- Confirmed no frontend changes, no P2/P3/P4, no external API.

### P1-M23.2 Boundaries

This is a corpus cleanup and embedding readiness checkpoint. No new features.

- Confirmed no frontend changes.
- Confirmed no P2/P3/P4 backend development.
- Confirmed no real LLM / external embedding API.
- Confirmed no tag was created (commit only).

## Completed In P1-M24

- Completed P1 Real RAG Online Smoke Test + Release Readiness verification.
- Online health check: status=ok, phase=P1-M24, pgvector_available=true, extension_create_ok=true.
- Online harness: **10/10 PASS** — embedding_count=18, vector_sync_enabled=true, retrieval_mode=customerops_vector_retrieval.
- Online eval:
  - `keyword_hit_rate@5`: **0.7694** (≥ 0.6 ✅)
  - `keyword_query_hit_rate@5`: **0.9167** (≥ 0.75 ✅)
  - `semantic_mode_count`: 12/12 (100% customerops_vector_retrieval)
  - `fallback_count`: 0
  - `avg_top1_score`: 0.5718, `avg_top5_score`: 0.4100
- Corpus inspect: SKIP (DATABASE_URL not set locally) — indirect assessment via eval.
- Embedding provider check: mock_ready=true, provider_ready=true (mock only), real_embedding_ready=false.
- Bad Case 回流: harness step 09+10 PASS, full trace verified.
- Added `docs/36_P1_REAL_RAG_ONLINE_RELEASE_READINESS_REPORT.md`.
- Updated `/health` phase to `P1-M24`.
- Phase assertions updated in test files (test_approved_knowledge_vector_sync.py, test_customerops_semantic_retrieval.py).
- All 93 tests pass (same suite as M23.1 plus phase assertion updates).
- README updated with P1 real vector RAG readiness note.

### P1-M24 Release Readiness Conclusion

P1 已具备真实向量 RAG 工程闭环（导入 → 清洗 → 审核 → 向量同步 → pgvector 语义检索 → Bad Case 回流）。所有核心指标达标。适合作为 **Demo / 工程验收版**。

**但当前线上 embedding provider 仍为 mock/deterministic (token-based bag-of-words)**，不是生产级真实语义 embedding。真实语义检索需要接入真实 embedding provider（如 OpenAI text-embedding-3-small），标记为 P1-M24.1（可选后续）。

### P1-M24 Boundaries

This is a smoke test, verification, and documentation checkpoint. No new features.

- Confirmed no P2/P3/P4 backend development.
- Confirmed no frontend changes.
- Confirmed no real LLM / real embedding API.
- Confirmed `backend/storage/`, `.env`, `datahub.db`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` remain git-ignored.
- Confirmed no tag was created (commit only).

## Completed In P1-M24.1

- Added comprehensive `.env.example` with LLM and embedding provider configuration.
- LLM provider: DeepSeek (OpenAI-compatible) with `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`.
- Embedding provider: mock as safe default with `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_MAX_RETRIES`.
- Reserved embedding options: SiliconFlow (BAAI/bge-large-zh-v1.5, 1024 dim) and Jina (jina-embeddings-v4, 2048 dim) — both commented out with dimension compatibility warnings.
- Added `.env.local.example` for personal secret overrides.
- Created local `.env` from template with placeholders only (no real API keys).
- Updated `.gitignore` to ignore `.env`, `.env.local`, `.env.*.local`, `*.env` while allowing `.env.example` and `.env.local.example`.
- Added local environment variable setup instructions to `README.md` and `README.en.md`.
- Confirmed no business code, no LLM integration, no embedding integration, no API, no database schema, no frontend changes.
- Confirmed no real API keys committed.
- Confirmed no tag was created (commit only).

### P1-M24.1 Boundaries

This is an env template and configuration checkpoint only. No business logic changes.

- Confirmed no `backend/app/llm.py` created.
- Confirmed no `backend/app/embedding.py` modified.
- Confirmed no CustomerOpsAgent retrieve logic changes.
- Confirmed no frontend changes.
- Confirmed no database schema changes.
- Confirmed no new dependencies.
- Confirmed no real API keys committed.
- Confirmed no P2/P3/P4 development.
- Confirmed no tag.

## Completed In P1-M24.2

- Completed real embedding provider verification and vector rebuild.
- Updated `backend/app/embedding.py`: siliconflow, jina, openai_compatible provider support in factory. DeepSeek explicitly excluded from embedding. EMBEDDING_TIMEOUT_SECONDS and EMBEDDING_MAX_RETRIES now read from env.
- Updated `scripts/check_embedding_provider.py`: BLOCKED_DIMENSION_MISMATCH detection, safe URL/key display, --verify with dimension validation, real_embedding_provider field.
- Added `scripts/rebuild_vector_rag.py`: blocked rebuild on provider not ready or dimension mismatch, remote/local rebuild, safe error messages.
- Added 70 new tests across 3 test files. All pass.
- Current status: mock provider active, real embedding code ready (pending API key configuration).
- Confirmed no frontend, no P2/P3/P4, no schema changes, no API keys committed, no tag.

## Next Suggested Stage

P1 is now release-ready (engineering verification version).

Options after user confirmation:
- **Tag P1 release**: `p1-m24-real-rag-online-release` (after user confirms).
- **P1-M24.1** (optional): Real Embedding Provider Verification — configure OpenAI/other provider and re-verify eval metrics with real semantic retrieval.
- **P2-M1**: Material Ingestion — NOT to be started before user confirms P1 final release.

P2 不应在 P1 真实 RAG 闭环最终收版且用户确认前启动。

## Completed In P1-M24.3

- Local SiliconFlow configuration loaded safely from the ignored root `.env`; existing process and Render environment variables retain priority.
- A real SiliconFlow embedding request succeeded with model `Qwen/Qwen3-Embedding-4B` and returned exactly 1536 dimensions, matching `Vector(1536)`.
- Render health verified PostgreSQL, pgvector availability, and extension creation; phase is `P1-M24.3`.
- Render vector rebuild completed with 24 approved candidates, 24 embeddings, 0 failed embeddings, provider `siliconflow`, model `Qwen/Qwen3-Embedding-4B`, dimension 1536.
- Online harness completed 10/10 PASS, including CustomerOpsAgent vector retrieval and Bad Case feedback/draft flow.
- Online eval completed with 12/12 semantic-mode queries, 0 fallbacks, `keyword_hit_rate@5=0.8181`, `keyword_query_hit_rate@5=0.9167`, `avg_top1_score=0.7051`, and `avg_top5_score=0.6592`.
- Semantic paraphrase smoke test passed 5/5 topics: return/refund, shipping/tracking, escalation, cancellation, and warranty.
- A real DeepSeek short-answer API call succeeded with the configured `LLM_*` provider settings. The current DataHub retrieval schema has no `answer_generation_mode` and does not integrate LLM answer generation; provider connectivity and retrieval are recorded separately.
- Local SQLite corpus inspection found 614 historical mock embeddings and no explicit pollution matches. It is not the Render corpus. Online rebuild replaced the active approved-knowledge sync corpus with SiliconFlow embeddings.
- The online harness introduced a clearly marked test placeholder. No online cleanup was applied because this environment has no safe Render PostgreSQL direct connection and no scoped deletion API.
- No API key, `.env`, database URL, frontend change, P2/P3/P4 work, tag, force push, or history rewrite is included.

### P1-M24.3 Release Gate

**P1 FINAL RELEASE SEALED** for the verified DataHub retrieval scope under tag `p1-m24.3-real-embedding-online-release`. The final gate passed 249/249 repository tests, the online harness passed 10/10, and the online eval retained 12/12 vector retrieval with zero fallbacks. DataHub-internal LLM answer generation is not part of the current retrieval contract and must not be claimed as implemented. The next stage is limited to P2-M0 Planning.

## Completed In P2-M0

- Added `docs/40_P2_MULTIMODAL_KNOWLEDGE_CENTER_PLANNING.md`.
- Defined P2 as an AI multimodal knowledge asset center, not a file drive or simple image upload feature.
- Defined the user flow: upload -> automatic processing -> human review -> approved knowledge asset -> Agent consumption.
- Planned four core P2 aggregates: Asset, Asset Extraction, Review, and Knowledge Link; avoided separate OCR/Caption/Tag/SKU table proliferation.
- Planned object storage for binaries and PostgreSQL for governed metadata/source trace; no binary storage in PostgreSQL, Git, or `backend/storage/`.
- Planned P1/P2 integration as isolated write paths plus unified query-time retrieval, preserving the frozen P1 index/API/schema.
- Planned a text-bridge MVP using reviewed OCR/Caption/tags/SKU evidence before native visual embeddings.
- Planned staged APIs, three dark-console pages, MVP boundaries, milestone gates, and risk controls.
- Referenced Databricks quality layering, LlamaIndex ingestion idempotency, Airbyte connector contracts, and multimodal RAG enrichment principles without adopting their full platforms.
- Confirmed no business code, database, schema, API, frontend, dependency, secret, or P2-M1 implementation change.

### P2-M0 Boundaries

This is a planning and documentation checkpoint only.

- P1 remains sealed at `p1-m24.3-real-embedding-online-release`.
- No P1 API, schema, frontend, retrieval contract, or CustomerOpsAgent repository change.
- No P2 backend, database, frontend, object storage, OCR, Caption, embedding, or unified retrieval implementation.
- The next allowed stage is P2-M1 Material Ingestion, starting with an object-storage ADR and additive Asset foundation only.
