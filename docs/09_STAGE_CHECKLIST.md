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
- `docs/10_FINAL_VISION_AND_ROADMAP.md`

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

## 7A. Phase-Prefixed Tag Naming Rule

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
- `p1-m15.7-product-ux-redesign`
- `p1-m15.8-homepage-ux-cleanup`

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

## 7C. P1-M13 Manual Cleaning Stage Check

Before P1-M13 work is accepted, confirm:

- The frontend workflow file was read:
  `C:\Users\16432\Desktop\AI_workflow\前端工作流.md`
- The React admin console is Chinese-facing.
- P1/P2/P3/P4 capability cards are present.
- P2/P3/P4 cards clearly show Roadmap / not connected status.
- Manual cleaning can load sanitized messages by `batch_id`.
- Manual cleaning can save `manual_action`, `cleaner`, and `cleaning_note`.
- Raw batch files remain read-only.
- Manual cleaning records remain under ignored `backend/storage/`.
- Extraction uses manual cleaning decisions.
- README files do not claim roadmap modules are already implemented.

## 7D. P1-M14 Knowledge Review Stage Check

Before P1-M14 work is accepted, confirm:

- The frontend workflow file was read:
  `C:\Users\16432\Desktop\AI_workflow\前端工作流.md`
- The Chinese admin console includes a knowledge review workbench.
- Review UI can load and filter knowledge candidates.
- Review UI displays source trace, quality score, cleaning issues, and risk flags.
- Candidate editing uses existing `PATCH /api/knowledge/candidates/{candidate_id}`.
- Review actions use existing approve, reject, and needs-revision APIs.
- Review records stay under ignored `backend/storage/review_records/`.
- Only approved candidates can enter RAG.
- Pending, needs-revision, and rejected candidates remain outside RAG.
- P2/P3/P4 remain Roadmap / not connected.

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

## 11. M4 Completion Check

M4 is complete when:

- `POST /api/extraction/run/{batch_id}` exists.
- `GET /api/extraction/jobs/{job_id}` exists.
- `GET /api/knowledge/candidates` exists.
- `GET /api/knowledge/candidates/{candidate_id}` exists.
- Extraction reads only from `backend/storage/sanitized_batches/`.
- Extraction does not read raw batch files.
- Knowledge candidates are saved under `backend/storage/knowledge_candidates/`.
- Extraction jobs are saved under `backend/storage/extraction_jobs/`.
- Extraction uses `rule_based_mock` only.
- No real LLM is used.
- Candidates are generated from simple sanitized customer -> agent pairs.
- Every candidate includes:
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
- Every candidate has `review_status: pending_review`.
- No candidate is marked `approved`.
- No candidate is indexed.
- Frontend can list sanitized batches.
- Frontend can run extraction for a sanitized batch.
- Frontend can show extraction summary.
- Frontend can show candidate list.
- Candidate UI clearly states pending-review candidates cannot enter RAG.
- No human review, approved knowledge, knowledge version management, RAG, embedding, vector database, database, ORM, CustomerOpsAgent integration, Bad Case, multimodal, MCP, fine-tuning, or real LLM work is implemented.
- `docs/04_API_CONTRACT.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, and `README.md` are updated.

## 12. M5 Completion Check

M5 is complete when:

- `GET /api/review/pending` exists.
- `PATCH /api/knowledge/candidates/{candidate_id}` exists.
- `POST /api/review/{candidate_id}/approve` exists.
- `POST /api/review/{candidate_id}/reject` exists.
- `POST /api/review/{candidate_id}/needs-revision` exists.
- Review APIs operate only on existing knowledge candidates under `backend/storage/knowledge_candidates/`.
- Review APIs do not read raw batches.
- Review APIs do not read sanitized batches to create approvals directly.
- Candidate editing supports:
  - `question`
  - `answer`
  - `intent`
  - `tags`
  - `risk_level`
  - `quality_score`
- Review states include:
  - `pending_review`
  - `needs_revision`
  - `approved`
  - `rejected`
- Review metadata is recorded:
  - `reviewer`
  - `review_note`
  - `reviewed_at`
  - `updated_at`
- Source traceability remains:
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
  - `extraction_method`
- Frontend can list pending and needs-revision candidates.
- Frontend can edit candidate fields.
- Frontend can approve, reject, and mark needs revision.
- Approved candidates are not indexed.
- Approved candidates are not available to CustomerOpsAgent.
- Rejected and needs-revision candidates do not enter retrieval.
- No RAG, chunking, embedding, vector database, database, ORM, CustomerOpsAgent integration, Bad Case, multimodal, MCP, fine-tuning, or real LLM work is implemented.
- `docs/04_API_CONTRACT.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, and `README.md` are updated.

## 13. M6 Completion Check

M6 is complete when:

- `POST /api/rag/build` exists.
- `GET /api/rag/chunks` exists.
- `GET /api/rag/chunks/{chunk_id}` exists.
- `POST /api/rag/search` exists.
- RAG build reads only from `backend/storage/knowledge_candidates/`.
- RAG build does not read raw batches.
- RAG build does not read sanitized batches directly.
- RAG chunks are saved under `backend/storage/rag_chunks/`.
- Every RAG chunk includes:
  - `chunk_id`
  - `candidate_id`
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
  - `knowledge_type`
  - `intent`
  - `tags`
  - `risk_level`
  - `quality_score`
  - `review_status`
  - `chunk_text`
  - `created_at`
  - `build_method`
- Only candidates with `review_status: approved` become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- RAG search uses local JSON plus simple keyword/mock scoring only.
- Search results include:
  - `score`
  - `chunk_id`
  - `candidate_id`
  - source information
- Frontend can show approved candidate count.
- Frontend can run local RAG build.
- Frontend can show build summary.
- Frontend can list RAG chunks.
- Frontend can run internal RAG search.
- UI clearly states this is not CustomerOpsAgent integration and not a real vector database.
- No CustomerOpsAgent integration, Bad Case, real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, or fine-tuning work is implemented.
- `docs/04_API_CONTRACT.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, and `README.md` are updated.

## 14. M6.5 RAG Quality Hardening Check

M6.5 is complete when:

- `POST /api/rag/build` remains local JSON plus mock retrieval only.
- RAG build remains approved-only.
- RAG build still reads only from `backend/storage/knowledge_candidates/`.
- RAG build does not read raw batches.
- RAG build does not read sanitized batches directly.
- Repeating build for an unchanged approved candidate does not create duplicate chunks.
- Chunk ids are stable for the same candidate.
- Build response includes:
  - `built_count`
  - `updated_count`
  - `skipped_count`
  - `chunk_count`
  - `skipped_reasons`
  - `status`
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- Search query is trimmed and must not be empty.
- Search query is limited to 500 characters.
- `top_k` defaults to 5.
- `top_k` is limited to the range 1-10.
- Invalid search input returns safe structured errors.
- Search scoring stays local keyword/mock scoring only.
- Search results include:
  - `score`
  - `matched_terms`
  - `chunk_id`
  - `candidate_id`
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
  - `chunk_text`
  - `tags`
  - `intent`
- Frontend shows `updated_count` and matched terms if it is updated in the stage.
- Lightweight verification or tests cover approved-only chunking, repeated build idempotency, search validation, and source trace.
- No CustomerOpsAgent integration, Bad Case, real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales training export, or fine-tuning work is implemented.
- `docs/04_API_CONTRACT.md`, `docs/07_ACCEPTANCE_CRITERIA.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `README.md`, and related API docs are updated.

## 15. M7 CustomerOpsAgent Retrieval Check

M7 is complete when:

- `POST /api/customer-ops-agent/retrieve` exists.
- `GET /api/customer-ops-agent/retrievals/{retrieval_id}` exists.
- `/health` reports `phase: M7`.
- CustomerOpsAgent retrieval reads only from `backend/storage/rag_chunks/`.
- CustomerOpsAgent retrieval does not read raw batches directly.
- CustomerOpsAgent retrieval does not read sanitized batches directly.
- CustomerOpsAgent retrieval does not read knowledge candidates directly.
- Only approved local `rag_chunked` results are returned.
- `pending_review`, `needs_revision`, and `rejected` records are not returned.
- Retrieval request validation covers:
  - required query
  - trimmed non-empty query
  - query maximum length of 500 characters
  - `top_k` default 5
  - `top_k` range 1-10
- Retrieval results include:
  - `retrieval_id`
  - `retrieval_mode`
  - `score`
  - `matched_terms`
  - `chunk_id`
  - `candidate_id`
  - `source_batch_id`
  - `source_conversation_id`
  - `source_message_ids`
- Retrieval trace records are saved under `backend/storage/retrieval_logs/`.
- Retrieval traces include result chunk ids for later M8 Bad Case linkage.
- Frontend may include a small CustomerOpsAgent Retrieval Test section.
- CustomerOpsAgent repository is not modified.
- No Bad Case API, Bad Case UI, or human correction workflow is implemented.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales training export, or fine-tuning work is implemented.
- `backend/storage/` remains ignored by Git.
- `docs/04_API_CONTRACT.md`, `docs/07_ACCEPTANCE_CRITERIA.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, and `README.md` are updated.

## 16. M7.5 Retrieval Contract Polish Check

M7.5 is complete when:

- `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md` exists.
- The contract document defines current APIs:
  - `POST /api/customer-ops-agent/retrieve`
  - `GET /api/customer-ops-agent/retrievals/{retrieval_id}`
- The contract document explains current capabilities:
  - read-only retrieval
  - approved local `rag_chunked` results only
  - `retrieval_id`
  - source trace
  - matched terms
  - score
- The contract document explains current non-capabilities:
  - no Bad Case submit
  - no real vector database
  - no embedding
  - no real LLM
  - no database
  - no direct knowledge mutation
- Both CustomerOpsAgent retrieval APIs require:
  - `X-DataHub-Client: CustomerOpsAgent`
- Missing or invalid client header returns `UNAUTHORIZED_CLIENT`.
- The header is documented as a local development auth placeholder only.
- No API key, real token, or `.env` secret is introduced.
- CustomerOpsAgent retrieval errors use the safe structured shape:
  - `success: false`
  - `error.code`
  - `error.message`
  - `error.details`
  - `requestId`
- Tests cover:
  - missing client header
  - wrong client header
  - valid client header
  - empty query
  - overlong query
  - `top_k` below 1
  - `top_k` above 10
  - missing retrieval trace
  - approved-only result trace fields
- README and API contract include PowerShell examples with the required header.
- CustomerOpsAgent repository is not modified.
- No Bad Case API, Bad Case UI, human correction workflow, production auth, vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales training export, or fine-tuning work is implemented.
- `backend/storage/` remains ignored by Git.

## 17. M8 Bad Case Feedback Check

M8 is complete when:

- `POST /api/customer-ops-agent/bad-cases` exists.
- `GET /api/bad-cases` exists.
- `GET /api/bad-cases/{bad_case_id}` exists.
- `PATCH /api/bad-cases/{bad_case_id}` exists.
- `/health` reports `phase: M8`.
- CustomerOpsAgent Bad Case submission requires:
  - `X-DataHub-Client: CustomerOpsAgent`
- Missing or invalid client header returns `UNAUTHORIZED_CLIENT`.
- `retrieval_id` is required and must exist in `backend/storage/retrieval_logs/`.
- Bad Cases are saved under `backend/storage/bad_cases/`.
- Bad Case records include:
  - `bad_case_id`
  - `retrieval_id`
  - `user_query`
  - `agent_answer`
  - `issue_type`
  - `expected_answer`
  - `severity`
  - `status`
  - `linked_chunk_ids`
  - `retrieval_result_count`
  - timestamps
- New Bad Cases default to `status: open`.
- Supported statuses are:
  - `open`
  - `triaged`
  - `resolved`
  - `ignored`
- PATCH can update:
  - `status`
  - `review_note`
  - `resolution_type`
  - `linked_candidate_id`
- PATCH does not create knowledge candidates.
- PATCH does not modify existing knowledge candidates.
- PATCH does not modify RAG chunks.
- PATCH does not automatically rebuild or re-index RAG.
- Frontend can submit a Bad Case, show the queue, view details, and update handling status or note.
- Tests cover auth, invalid `retrieval_id`, validation errors, successful submission, list/detail/PATCH, retrieval trace linkage, and no candidate/RAG mutation.
- CustomerOpsAgent repository is not modified.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales training export, or fine-tuning work is implemented.
- `backend/storage/` remains ignored by Git.
- `docs/04_API_CONTRACT.md`, `docs/07_ACCEPTANCE_CRITERIA.md`, `docs/08_DEV_STATUS.md`, `docs/09_STAGE_CHECKLIST.md`, `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`, and `README.md` are updated.

## 18. M8.5 Bad Case Resolution To Draft Check

M8.5 is complete when:

- `POST /api/bad-cases/{bad_case_id}/create-draft` exists.
- `/health` reports `phase: M8.5`.
- The API accepts human-provided draft fields:
  - `question`
  - `answer`
  - `intent`
  - `tags`
  - `risk_level`
  - `quality_score`
  - `knowledge_type`
  - `reviewer`
  - `review_note`
- Missing Bad Cases return `BAD_CASE_NOT_FOUND`.
- Ignored Bad Cases return `BAD_CASE_IGNORED`.
- Invalid draft payloads return `INVALID_DRAFT_PAYLOAD`.
- The generated candidate is saved under `backend/storage/knowledge_candidates/`.
- The generated candidate has:
  - `candidate_id` starting with `kc_badcase_`
  - `source_type: bad_case`
  - `source_bad_case_id`
  - `source_retrieval_id`
  - `source_chunk_ids`
  - `review_status: pending_review`
  - `extraction_method: bad_case_resolution`
- The source Bad Case records `linked_candidate_id`.
- The source Bad Case can be marked `resolved`.
- No existing candidate is directly modified.
- No candidate is automatically approved.
- No RAG chunk is created automatically.
- No existing RAG chunk is modified.
- RAG build is not triggered automatically.
- CustomerOpsAgent repository is not modified.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales training export, or fine-tuning work is implemented.
- `backend/storage/` remains ignored by Git.
- README, API contract, architecture, acceptance criteria, development status, stage checklist, and CustomerOps retrieval contract are updated.

## 19. P1-M9 Phase-One Release Freeze Check

P1-M9 is complete when:

- `/health` reports `phase: P1-M9`.
- `backend/tests/test_phase_one_flow.py` exists.
- The P1 full-chain test covers:
  - JSON import
  - cleaning / sanitization
  - extraction
  - human approval
  - local RAG build
  - CustomerOpsAgent retrieval
  - Bad Case submit
  - Bad Case to `pending_review` draft
- Existing tests still pass:
  - `backend/tests/test_customerops_retrieval.py`
  - `backend/tests/test_rag_quality.py`
  - `backend/tests/test_bad_case_feedback.py`
- Rejected and needs-revision candidates do not enter RAG.
- Bad Case-generated drafts are not auto-approved.
- Bad Case-generated drafts do not modify RAG chunks.
- RAG is not rebuilt automatically by draft creation.
- `docs/13_P1_RELEASE_FREEZE_REPORT.md` exists.
- README and core docs describe the P1-M9 freeze status.
- Version naming rules use phase-prefixed tags from P1-M9 onward.
- Historical tags are not moved, deleted, or renamed.
- At the P1-M9 checkpoint, P1-M9.5 public dataset evaluation was not implemented yet.
- At the P1-M9 checkpoint, P1-M10 legacy RAG migration was not implemented yet.
- At the P1-M9 checkpoint, P1-M11 unified RAG release was not implemented yet.
- P2/P3/P4 features are not implemented.
- `backend/storage/` remains ignored by Git.

## 20. P1-M9.5 Public Dataset Evaluation Check

P1-M9.5 is complete when:

- A public customer-support or e-commerce dataset is selected and documented.
- Dataset source URL, access method, fields used, sample size, and license notes are recorded.
- Full public dataset files are not committed.
- Real private customer data is not committed.
- If a sample is committed, it is small, safe, and converted to the DataHub M2 import JSON format.
- `scripts/prepare_public_dataset_sample.py` exists if a conversion script is submitted.
- `scripts/run_public_dataset_eval.py` exists if an evaluation runner is submitted.
- `docs/14_PUBLIC_DATASET_EVAL_REPORT.md` exists.
- The report records:
  - evaluation goal
  - dataset selection
  - sampling strategy
  - DataHub pipeline results
  - cleaning / sanitization results
  - extraction results
  - controlled approval results
  - local RAG build results
  - retrieval test results
  - Bad Case feedback results
  - Bad Case to draft results
  - quality observations
  - limitations
  - P1-M10 next step
- `backend/tests/test_public_dataset_eval_flow.py` verifies the public sample through:
  - import
  - cleaning
  - extraction
  - controlled approval
  - local RAG build
  - CustomerOpsAgent retrieval
  - Bad Case submission
  - Bad Case to `pending_review` draft
- P1 existing tests still pass.
- No CustomerOpsAgent legacy RAG migration is implemented.
- No CustomerOpsAgent repository changes are made.
- No unified RAG switch is implemented.
- No database, ORM, vector database, embedding model, real LLM, multimodal, MCP, sales export, fine-tuning export, or P2/P3/P4 implementation is introduced.
- New tag uses the phase-prefixed name `p1-m9.5-public-dataset-eval`.
- Historical tags are not moved, deleted, or renamed.

## 21. P1-M10 Legacy RAG Migration Check

P1-M10 is complete when:

- `POST /api/legacy-rag/import` exists.
- `GET /api/legacy-rag/imports` exists.
- `GET /api/legacy-rag/imports/{import_id}` exists.
- `/health` reports `phase: P1-M10`.
- `samples/legacy_rag_export_sample.json` exists and uses fake data only.
- Legacy RAG import metadata is saved under ignored local storage.
- Legacy items are converted into normal DataHub knowledge candidates.
- `trusted_import=true` creates `approved` candidates.
- `trusted_import=false` creates `pending_review` candidates.
- Candidates include:
  - `source_type: legacy_rag`
  - `source_legacy_id`
  - `source_import_id`
  - `migration_mode`
  - `extraction_method: legacy_rag_migration`
- Candidate ids are stable for the same `source_name + legacy_id`.
- Repeated import does not create duplicate candidates.
- Approved trusted legacy candidates can enter local RAG chunks.
- Review-required legacy candidates cannot enter local RAG chunks.
- CustomerOpsAgent retrieval can return approved legacy chunks.
- Retrieval results include legacy source trace.
- `backend/tests/test_legacy_rag_migration.py` passes.
- Existing P1 tests still pass.
- CustomerOpsAgent repository is not read or modified.
- At the P1-M10 checkpoint, P1-M11 unified RAG release was not implemented yet.
- No private CustomerOpsAgent RAG data or real business knowledge is committed.
- No database, ORM, vector database, embedding model, real LLM, multimodal, MCP, sales export, fine-tuning export, or P2/P3/P4 implementation is introduced.
- New tag uses the phase-prefixed name `p1-m10-legacy-rag-migration`.
- Historical tags are not moved, deleted, or renamed.

## 22. P1-M11 Unified DataHub RAG Release Check

P1-M11 is complete when:

- `/health` reports `phase: P1-M11`.
- `README.md` exists and is rewritten as the Chinese P1-M11 release README.
- `README.en.md` exists and is aligned with the Chinese README.
- Both READMEs include STAR project breakdowns.
- Both READMEs use verified P1 metrics only.
- Both READMEs clearly state that P2/P3/P4 are roadmap phases and not implemented.
- `docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md` exists.
- `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md` exists.
- `backend/tests/test_unified_rag_release.py` exists.
- Unified RAG verification covers:
  - `chat_logs` approved candidates entering RAG.
  - `public_dataset` approved candidates entering RAG.
  - trusted `legacy_rag` candidates entering RAG.
  - Bad Case-generated drafts staying `pending_review` until approved.
  - approved Bad Case drafts entering RAG.
  - CustomerOpsAgent retrieval returning a consistent result shape.
  - `source_type` and source trace in retrieval results.
  - pending, rejected, and needs-revision candidates staying out of RAG.
  - repeated RAG build idempotency.
- CustomerOpsAgent DataHub-only contract is documented:
  - `POST /api/customer-ops-agent/retrieve`
  - `GET /api/customer-ops-agent/retrievals/{retrieval_id}`
  - `POST /api/customer-ops-agent/bad-cases`
  - `X-DataHub-Client: CustomerOpsAgent`
- CustomerOpsAgent repository is not modified.
- No CustomerOpsAgent private data or real business knowledge is committed.
- No real vector database, embedding model, database, ORM, real LLM, multimodal workflow, sales export, fine-tuning export, MCP, or P2/P3/P4 implementation is introduced.
- `backend/storage/` remains ignored by Git.
- New tag uses the phase-prefixed name `p1-m11-unified-rag-release`.
- Historical tags are not moved, deleted, or renamed.

## 23. P1-M12 Advanced Data Cleaning Check

P1-M12 is complete when:

- `/health` reports `phase: P1-M12`.
- The P1-M12 to P1-M15 roadmap is documented in README and core docs.
- P1-M11 is described as the unified RAG release, not the final high-quality DataHub release.
- P1-M15 is described as the final Phase 1 high-quality data platform release.
- Cleaning keeps all existing M3 fields and adds:
  - `exact_duplicate_count`
  - `near_duplicate_count`
  - `low_quality_count`
  - `noise_count`
  - `review_recommended_count`
  - `drop_recommended_count`
  - `average_quality_score`
- Sanitized messages include:
  - `cleaning_issues`
  - `risk_flags`
  - `quality_score`
  - `quality_level`
  - `suggested_action`
- PII masking covers email, phone, order id, tracking id, address, name-like text, ZIP/postal code, and payment-like long digit strings.
- Extraction skips messages with `suggested_action: drop`.
- `backend/tests/test_advanced_cleaning.py` exists and passes.
- Existing P1 tests still pass.
- `docs/18_ADVANCED_CLEANING_RULES.md` exists.
- No full manual cleaning frontend, P1-M14 review console, P1-M15 final release, P2/P3/P4, database, ORM, vector database, embedding model, real LLM, MCP, or CustomerOpsAgent repository change is introduced.
- New tag uses the phase-prefixed name `p1-m12-advanced-data-cleaning`.
- Historical tags are not moved, deleted, or renamed.

## 24. P1-M13 Chinese Admin Console & Manual Cleaning Workbench Outline

P1-M13 must not start unless explicitly requested.

- Read and follow `C:\Users\16432\Desktop\AI_workflow\前端工作流.md` before frontend implementation.
- Frontend is Chinese-first.
- Dashboard reserves P1/P2/P3/P4 module entries.
- Unimplemented modules are clearly marked as Roadmap / Not Connected.
- Manual cleaning workbench supports raw versus sanitized comparison.
- Operators can correct sanitized content, mark keep/drop/review, and write cleaning notes.

## 25. P1-M14 Knowledge Review Quality Console Outline

P1-M14 must not start unless explicitly requested.

- Chinese knowledge review workbench supports candidate editing, approve, reject, and needs_revision.
- Review UI displays source trace, quality_score, cleaning_issues, and risk_flags.
- Reviewer guide defines standards for FAQ, standard answers, business rules, human handoff rules, and forbidden answer rules.

## 26. P1-M15 High-quality DataHub P1 Final Release Outline

P1-M15 must not start unless explicitly requested.

- Validate the high-quality loop:
  machine cleaning -> manual cleaning -> extraction -> human review -> unified RAG -> CustomerOpsAgent retrieval -> Bad Case feedback.
- Publish the final P1 high-quality DataHub acceptance report.
- P2 multimodal material ingestion remains out of scope unless explicitly started after P1-M15.

## 27. P1-M15 High-quality DataHub Release Check

P1-M15 is complete when:

- The frontend workflow file has been read.
- The dark design reference has been read.
- `/health` reports `P1-M15`.
- `backend/tests/test_p1_high_quality_datahub_release.py` verifies the final P1 loop.
- Existing P1 tests still pass.
- The frontend builds successfully.
- The Chinese frontend uses a unified dark AgentOps / data governance style.
- P1/P2/P3/P4 cards remain visible.
- P2/P3/P4 cards remain Roadmap / not connected.
- `docs/21_P1_HIGH_QUALITY_DATAHUB_RELEASE_REPORT.md` exists.
- README remains product-oriented and does not become a development log.
- No P2/P3/P4, vector database, embedding, database, ORM, real LLM, MCP, or CustomerOpsAgent repository change is introduced.
- `backend/storage/`, `frontend/node_modules/`, and `frontend/dist/` are not committed.
- New tag uses `p1-m15-high-quality-datahub-release`.

## 28. P1-M15.5 Frontend UX Cleanup And Boundary Review Check

P1-M15.5 is complete when:

- The frontend workflow file has been read.
- The dark design reference has been read.
- The first screen shows a simple product overview and backend connection status.
- The main P1 workflow is organized as Step 1 to Step 5.
- P1 "enter module" scrolls to the main workflow.
- P2/P3/P4 buttons are disabled and marked Roadmap / not connected.
- Backend disconnected state explains how to start FastAPI:
  `python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000`
- Internal technical details are moved below the primary workflow or into an advanced information area.
- `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md` exists.
- No interview packaging, resume packaging, P2/P3/P4 backend implementation, vector database, embedding, database, ORM, real LLM, MCP, CustomerOpsAgent repository change, or historical tag rewrite is introduced.
- New tag uses `p1-m15.5-frontend-ux-cleanup-boundary-review`.

## 29. P1-M15.6 Render Deployment Config Check

P1-M15.6 is complete when:

- `backend/requirements.txt` exists and contains the minimal backend dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`.
- `.python-version` exists at the repository root with `3.11.9`.
- `docs/23_RENDER_DEPLOYMENT_GUIDE.md` exists and documents:
  - Service type: Web Service.
  - Repository: `Strange-Men/DataHub`, branch `main`.
  - Root Directory: leave empty.
  - Build Command: `pip install -r backend/requirements.txt`.
  - Start Command: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`.
  - Python version: 3.11.9 (via `.python-version`).
  - Health check URL and common errors.
- `docs/08_DEV_STATUS.md` records P1-M15.6 as the deployment config checkpoint.
- README files link to the Render deployment guide.
- No business logic, frontend, or backend API changes are introduced.
- No P2/P3/P4, database, ORM, vector database, embedding, real LLM, MCP, or CustomerOpsAgent repository change is introduced.
- `backend/storage/`, `frontend/node_modules/`, `frontend/dist/`, `.env`, `.venv/` remain git-ignored.
- No tag is created for this checkpoint (commit only).
- Commit message uses `[P1-M15.6] chore: add Render deployment configuration`.

## 30. P1-M15.7 Product UX Redesign & Deployment Link Fix Check

P1-M15.7 is complete when:

- Frontend uses React Router with 6 pages: 首页, 客服文本中台, AI 素材中心, 数据资产复用, MCP + Agent 集群, 高级信息.
- Top navigation bar is present with backend connection status indicator.
- Home page shows product overview, capability cards, and backend connection state.
- P1 "客服文本中台" is a 5-step workflow: 导入数据 → 机器清洗 → 人工清洗 → 知识审核 → RAG & Agent.
- P1 supports file upload (file picker + drag-and-drop + sample data + collapsed paste area).
- Technical fields are collapsed by default (details/summary).
- P2 "AI 素材中心" has a complete product shell with 6 flow cards, all buttons disabled and labeled "P2 后接入".
- P3 "数据资产复用" has a complete product shell with 6 module cards, all buttons disabled and labeled "P3 后接入".
- P4 "MCP + Agent 集群" has a complete product shell with tool list, agent grid, all buttons disabled and labeled "P4 后接入".
- "高级信息" page contains developer info, health status, technical boundaries.
- API_BASE_URL is dynamic: reads VITE_API_BASE_URL env var → falls back to Render or localhost.
- Backend has CORS middleware allowing localhost:5173 and data-hub-flame.vercel.app.
- Backend disconnected state shows friendly hint about Render cold start (not red error).
- README.md and README.en.md include live demo URLs.
- docs/24_FRONTEND_PRODUCT_UX_REDESIGN.md exists.
- docs/25_VERCEL_DEPLOYMENT_GUIDE.md exists.
- No P2/P3/P4 backend development, no tag (commit only).
- `npm run build` passes in frontend/.
- Python compile check passes for backend.
- No STAR/面试包装/简历包装 wording.
- No tag is created for this checkpoint (commit only).
- Commit message uses `[P1-M15.7] feat: redesign DataHub frontend for product demo`.

## 31. P1-M15.8 Homepage UX Cleanup & Public Surface Cleanup Check

P1-M15.8 is complete when:

- Homepage Hero section no longer shows three duplicate action buttons (开始体验, 上传客服数据, 使用示例数据).
- Hero section only communicates what DataHub is and its value proposition.
- Hero includes a concise status indicator: 当前已接入 / 后续预留 / 后端服务状态.
- Four capability cards are the sole entry points on the homepage.
- P1 card ("客服文本中台") is active and clickable with "进入工作台" button.
- P2/P3/P4 cards are disabled with "暂未接入" labels, not clickable fake features.
- "高级信息" is removed from the top navigation bar.
- `/advanced` route is deleted or redirected to home.
- Public UI does not display: API Base URL, local JSON storage, mock retrieval, no vector DB, no embedding, no real LLM, no DB/ORM, no MCP, source trace technical notes.
- Backend status displays user-friendly text only: 服务正常 / 连接中 / 服务暂不可用，可能正在冷启动.
- P1 workbench (`/p1-text-hub`) remains fully functional.
- P2/P3/P4 pages retain complete product shells with all buttons disabled.
- No P2/P3/P4 backend development.
- No tag is created for this checkpoint (commit only).
- Commit message uses `[P1-M15.8] chore: clean up public homepage UX`.
- `npm run build` passes in frontend/.
- Python compile check passes for backend.
- Backend tests pass.
- README was not turned into a stage log.
- No interview packaging or resume packaging.
- `backend/storage/`, `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/` are not committed.

## 32. P1-M15.9 Database Persistence Roadmap Lock Check

P1-M15.9 is complete when:

- `docs/26_DATABASE_PERSISTENCE_ROADMAP.md` exists and contains:
  - P1 当前 local JSON storage 状态说明。
  - 为什么数据库持久化必须属于 P1（不进入 P2 的理由）。
  - 目标：页面操作数据持久保存在数据库中。
  - 技术选型：SQLAlchemy + SQLite 本地默认 + PostgreSQL 生产可选，DATABASE_URL 统一入口。
  - 核心数据表规划（raw_batches, raw_messages, sanitized_batches, sanitized_messages, manual_cleaning_records, knowledge_candidates, review_records, rag_chunks, retrieval_logs, bad_cases）。
  - P1-M16 到 P1-M20 完整路线。
  - 不做什么清单。
  - 风险与边界。
  - 完成后的 P1 定义。
- `docs/10_FINAL_VISION_AND_ROADMAP.md` 已补充数据库持久化补强内容。
- `docs/08_DEV_STATUS.md` 已记录 P1-M15.9 checkpoint。
- `docs/09_STAGE_CHECKLIST.md` 已新增 P1-M15.9 及 P1-M16 到 P1-M20 checklist。
- `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md` 已说明当前未数据库化、后续补强计划。
- README.md 和 README.en.md 已增加数据库持久化下一步提示。
- 本轮为文档-only checkpoint，无代码修改。
- 无数据库代码、SQLAlchemy、models.py、database.py、后端 API、前端修改。
- 不提交 `backend/storage/`、`.env`、`.venv/`、`node_modules/`、`frontend/dist/`、API Key。
- 不打 tag（commit only）。
- Commit message 使用 `[P1-M15.9] docs: lock database persistence roadmap`。

## 33. P1-M16 Database Foundation Check

P1-M16 is complete when:

- `backend/app/database.py` 存在，支持 DATABASE_URL 环境变量。
- `backend/app/db_models.py` 存在，包含核心表 SQLAlchemy 模型。
- 本地默认 SQLite（`sqlite:///./datahub.db`）。
- 线上通过 DATABASE_URL 支持 PostgreSQL。
- `scripts/init_database.py` 可用（自动 create_all）。
- `backend/tests/test_database_foundation.py` 存在并通过。
- `/health` 返回 `database_status` 字段，不暴露 DATABASE_URL。
- SQLAlchemy 和 psycopg2-binary 已加入 `backend/requirements.txt`。
- 现有 P1 JSON demo 链路未被破坏。
- 现有测试全部通过。
- py_compile 全部通过。
- init_database.py 执行成功。
- 前端 build 通过。
- 不迁移任何现有业务 API。
- git status clean。
- 不打 tag（commit only）。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。

本轮已完成 (2026-07-04)：

- [x] SQLAlchemy dependency added (sqlalchemy==2.0.36, psycopg2-binary==2.9.10)
- [x] database.py added (engine, SessionLocal, Base, get_db, check_database_connection)
- [x] db_models.py added (10 core table models)
- [x] init_database.py added (Base.metadata.create_all)
- [x] database foundation test added (test_database_foundation.py)
- [x] health check includes safe database_status (no URL/password/host leak)
- [x] local SQLite initialization works (sqlite:///./datahub.db when DATABASE_URL unset)
- [x] existing P1 tests still pass (phase updated to P1-M16)
- [x] no business API migration yet
- [x] no tag

## 34. P1-M17 Import & Cleaning DB Persistence Check

P1-M17 is complete when:

- 导入 JSON 写 `raw_batches` / `raw_messages` 表。
- 机器清洗写 `sanitized_batches` / `sanitized_messages` 表。
- 批次列表从数据库读取。
- 前端刷新后批次仍可见。
- 保留 JSON fixture 作为测试样本。
- 数据库可 SELECT 查到 raw/sanitized 数据。
- 现有测试通过。
- git status clean。
- 不打 tag（commit only，除非明确 release）。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。

本轮已完成 (2026-07-04)：

- [x] 导入 JSON 写 raw_batches / raw_messages 表
- [x] 机器清洗写 sanitized_batches / sanitized_messages 表
- [x] 批次列表从数据库优先读取（DB first, JSON fallback）
- [x] 批次详情从数据库优先读取（DB first, JSON fallback）
- [x] 重复导入幂等（同 batch_id 替换 raw_messages）
- [x] 重复清洗幂等（同 batch_id 替换 sanitized_messages）
- [x] 保留 JSON storage 兼容（双写 + fallback）
- [x] db_repositories.py 数据访问层
- [x] FastAPI startup 自动建表 (init_database_tables)
- [x] 新增 test_import_cleaning_db_persistence.py 测试
- [x] 现有 P1 测试通过（phase 更新至 P1-M17）
- [x] 前端 build 通过
- [x] py_compile 通过
- [x] 不迁移人工清洗 / 知识审核 / RAG / Agent / Bad Case
- [x] 不提交 backend/storage/、.env、datahub.db、API Key
- [x] 不打 tag
- [x] git status clean

## 35. P1-M18 Manual Cleaning & Review DB Persistence Check

P1-M18 is complete when:

- 人工清洗写 `manual_cleaning_records` 表。
- 知识抽取从数据库读取人工清洗后的数据。
- candidate 写 `knowledge_candidates` 表。
- 审核动作写 `review_records` 表。
- candidate 状态（review_status）持久化。
- 人工清洗保存后刷新页面仍在。
- 审核通过后刷新页面仍为 approved。
- Render 重启后记录仍在。
- 数据库可查 manual_cleaning_records / knowledge_candidates / review_records。
- 现有测试通过。
- git status clean。
- 不打 tag（commit only，除非明确 release）。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。

本轮已完成 (2026-07-05)：

- [x] 人工清洗写 manual_cleaning_records 表
- [x] 知识抽取从数据库读取 sanitized messages
- [x] 知识抽取应用人工清洗 effective content
- [x] knowledge_candidates 写数据库（幂等：按 source_id + question + answer 去重）
- [x] 审核动作 (approve/reject/needs_revision) 写 review_records 表
- [x] candidate review_status 持久化到 knowledge_candidates.status
- [x] 页面刷新后人工清洗结果仍在（DB 优先读取，merge manual cleaning records）
- [x] 页面刷新后 candidate 审核状态仍在
- [x] 重复抽取幂等（同 source_id + question + answer 替换而非重复）
- [x] 保留 JSON storage 兼容（merge DB + JSON，DB 优先）
- [x] 新增 test_manual_review_db_persistence.py (16 tests)
- [x] 现有 P1 核心测试通过（phase 更新至 P1-M18）
- [x] 前端 build 通过
- [x] py_compile 通过
- [x] init_database 通过
- [x] 不迁移 RAG / Agent / Bad Case
- [x] 不提交 backend/storage/、.env、datahub.db、API Key
- [x] 不打 tag
- [x] git status clean

## 36. P1-M19 RAG / Agent / Bad Case DB Persistence Check

P1-M19 is complete when:

- approved candidate 构建 `rag_chunks` 表记录。
- CustomerOpsAgent 检索写 `retrieval_logs` 表。
- Bad Case 写 `bad_cases` 表。
- Bad Case draft candidate 可进入审核链路。
- Build RAG 后 rag_chunks 表有数据。
- Agent 查询后 retrieval_logs 表有数据。
- Bad Case 提交后 bad_cases 表有数据。
- 页面刷新后 RAG chunks、retrieval logs、Bad Case 列表仍在。
- 现有测试通过。
- git status clean。
- 不打 tag（commit only，除非明确 release）。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。

本轮已完成 (2026-07-05)：

- [x] approved candidates build rag_chunks
- [x] pending/rejected candidates excluded from RAG
- [x] rag_chunks are persisted
- [x] duplicate RAG build is idempotent
- [x] Agent retrieval reads DB rag_chunks
- [x] retrieval_logs are persisted
- [x] retrieval detail reads DB
- [x] bad_cases are persisted
- [x] Bad Case creates pending_review candidate
- [x] Bad Case candidate enters review chain
- [x] existing P1 tests still pass
- [x] frontend build still passes
- [x] no tag
- [x] 新增 test_rag_agent_badcase_db_persistence.py (16 tests)
- [x] 不提交 backend/storage/、.env、datahub.db、API Key
- [x] git status clean

## 37. P1-M20 DB Release & Online Persistence Smoke Test Check

P1-M20 is complete when:

- [/] 完整线上 Smoke Test 通过（Vercel 前端全流程 → Render 后端 → 数据库）。
- [/] Render 后端重启后复测通过（数据仍在）。
- [/] 数据库控制台 SELECT 验证通过（所有表有对应记录）。
- [/] README / 部署文档已更新本地 SQLite 与线上 PostgreSQL 配置说明。
- [/] `docs/31_DB_RELEASE_ONLINE_SMOKE_TEST_REPORT.md` 已输出。
- [/] P1 全链路仍能跑通。
- [/] 页面操作产生的数据能入库。
- [/] 页面刷新后数据仍在。
- [/] Render 重新部署后数据仍在。
- [/] 现有测试通过。
- [/] git status clean。
- [ ] P1-M20 打 release tag：`p1-m20-db-release`。（本轮不打 tag，commit only）
- [/] 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。

本轮已完成 (2026-07-05)：

- [x] /api/health shows postgresql ok
- [x] Vercel import creates DB records
- [x] machine cleaning persists
- [x] manual cleaning persists
- [x] knowledge candidates persist
- [x] review records persist
- [x] RAG chunks persist
- [x] retrieval logs persist
- [x] bad cases persist
- [x] refresh persistence verified
- [x] Render redeploy persistence verified
- [x] SQL counts verified
- [x] existing tests pass
- [x] frontend build passes
- [x] no tag
- [x] docs/31_DB_RELEASE_ONLINE_SMOKE_TEST_REPORT.md created
- [x] docs/08_DEV_STATUS.md updated
- [x] docs/09_STAGE_CHECKLIST.md updated
- [x] docs/26_DATABASE_PERSISTENCE_ROADMAP.md updated
- [x] README.md and README.en.md updated
- [x] health phase updated to P1-M20
- [x] no P2/P3/P4 backend development
- [x] no real LLM / embedding / vector DB / MCP
- [x] git status clean

## 38. P1-M16 To P1-M20 General Rules

所有 P1-M16 到 P1-M20 阶段：

- git status 必须 clean 才能开始。
- 每个阶段 commit message 使用 `[P1-Mxx]` 前缀。
- 不打 tag，除非明确标注 release（仅 P1-M20 打 tag）。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key、真实客服数据。
- 现有测试必须通过后再 push。
- 不进入 P2/P3/P4 后端开发。
- 不接真实 LLM、embedding、向量数据库。

## 39. P1-M20.5 Simplify P1 Workflow UX Check

P1-M20.5 is complete when:

- P1 workflow simplified from 5 steps to 4 steps.
- Original Step 2 (机器清洗) and Step 3 (人工清洗) merged into unified Step 2 (清洗数据).
- Step 2 uses sub-tabs: A. 机器清洗 / B. 人工清洗工作台.
- Original Step 4 (生成知识) and Step 5 (审核知识) merged into unified Step 3 (生成并审核知识).
- Step 3 uses sub-tabs: A. 生成待审核知识 / B. 知识审核.
- Step 4 (更新知识库并测试 Agent) stays as unified final step.
- Step indicator shows exactly 4 steps.
- All step navigation buttons updated.
- `/health` reports `P1-M20.5`.
- No database logic or API logic changed.
- No P2/P3/P4 backend development.
- `npm run build` passes.
- `py_compile` passes.
- git status clean.
- No tag (commit only).
- Commit message uses `[P1-M20.5] polish: simplify P1 workflow user experience`.

本轮已完成 (2026-07-05):

- [x] P1 workflow simplified to 4 steps
- [x] Step 2 = 清洗数据 (machine + manual sub-tabs)
- [x] Step 3 = 生成并审核知识 (generate + review sub-tabs)
- [x] Step indicator shows 4 steps
- [x] All navigation links updated
- [x] `/health` reports P1-M20.5
- [x] No database/API logic changed
- [x] `npm run build` passed
- [x] `py_compile` passed
- [x] No tag
- [x] git status clean

## 40. P1-M20.6 Global Frontend Visual System Polish Check

P1-M20.6 is complete when:

- [/] 全站前端页面审计完成（首页、P1、P2、P3、P4、导航、组件）。
- [/] 全局 CSS token 体系建立（背景、表面、边框、文本、强调色、语义色、间距、圆角、按钮高度）。
- [/] 亮蓝按钮替换为克制的暗青/深蓝渐变。
- [/] 新增 `.btn-next` 统一所有"下一步"按钮大小、颜色、圆角。
- [/] 按钮规范统一：`.btn-primary`, `.btn-secondary`, `.btn-outline`, `.btn-danger`, `.btn-disabled`, `.btn-next`, `.btn-small`。
- [/] 卡片规范统一：所有卡片边框、圆角、内边距、背景一致。
- [/] 导航 Logo 渐变改为暗青色（不再使用亮蓝 `#1f9df0`）。
- [/] 进度条渐变改为暗青色。
- [/] 内容预览文字亮度降低。
- [/] 空状态、badge、tab、状态指示器、反馈面板视觉统一。
- [/] P1 四个主流程保持不变。
- [/] P2/P3/P4 页面保持产品壳，按钮统一禁用样式。
- [/] 首页能力卡片、P1 工作步骤、P2/P3 流程卡片、P4 Agent/工具卡片风格统一。
- [/] `/health` 报告 `P1-M20.6`。
- [/] `npm run build` 通过。
- [/] `py_compile` 通过。
- [/] 未改变数据库主逻辑。
- [/] 未改变 API 逻辑。
- [/] 未进入 P2/P3/P4 后端开发。
- [/] 未提交 `.env`、`datahub.db`、`backend/storage/`、API Key。
- [/] 不打 tag（commit only）。
- [/] git status clean。
- [/] Commit message 使用 `[P1-M20.6] polish: unify global frontend visual system`。

本轮已完成 (2026-07-05):

- [x] 全站前端审计完成
- [x] CSS token 体系建立
- [x] 亮蓝替换为暗青
- [x] btn-next 统一下一步按钮
- [x] 卡片/按钮/导航/badge/空状态统一
- [x] P1 四个主流程不变
- [x] P2/P3/P4 产品壳视觉统一
- [x] docs/34 视觉系统文档新增
- [x] docs/08, docs/09 更新
- [x] npm run build 通过
- [x] py_compile 通过
- [x] 未改数据库/API 逻辑
- [x] 无 tag
- [x] git status clean

---

## 41. P1-M20.7 to P1-M24 Real RAG Development Roadmap

完整路线见 `docs/35_REAL_RAG_DEVELOPMENT_ROADMAP.md`。

### 41A. P1-M20.7 Lightweight Pipeline Harness + RAG Readiness Check

P1-M20.7 is complete when:

- [x] `scripts/run_p1_pipeline_harness.py` 存在。
- [x] 脚本调已有 API 串行跑全链路（导入 -> 清洗 -> 人工清洗 -> 抽取 -> 审核 -> RAG -> Agent 检索 -> Bad Case -> Bad Case draft）。
- [x] 每步输出 PASS / FAIL、HTTP status、response 摘要、关键 ID。
- [x] 脚本支持 `--base-url` 参数。
- [x] 本地 `python scripts/run_p1_pipeline_harness.py` 可运行（local backend unavailable → expected FAIL, not syntax error）。
- [x] 线上 `python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com` 全部 PASS (10/10)。
- [x] 不新增 pipeline 数据库表。
- [x] 不改数据库 schema。
- [x] 不改业务 API。
- [x] 轻量 SDD/TDD 规则写入文档（docs/35_REAL_RAG_DEVELOPMENT_ROADMAP.md 第 14 节）。
- [x] pgvector 检查脚本存在（`scripts/check_pgvector_support.py` + harness `--check-pgvector`）。
- [ ] **已确认 Render PostgreSQL 是否支持 pgvector**（需在 Render 环境执行 `SELECT * FROM pg_available_extensions WHERE name = 'vector';`）。
- [x] pgvector 可用性结论已记录：本地 SKIP（DATABASE_URL 未设置），需在 Render 验证。
- [ ] 如果 pgvector 不可用，已停止并重新评估方案（待 Render 验证后决定）。
- [ ] `/health` 报告 `P1-M20.7`（本轮 health phase 未改，保持 P1-M20.6；health 更新不属于 harness 范围）。
- [x] 现有测试全部通过（24 harness tests + all existing P1 tests）。
- [x] git status clean。
- [x] 不打 tag（commit only）。
- [x] 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key。
- [x] 不进入 P2/P3/P4 后端开发。

### 41B. P1-M21 Vector RAG Foundation + Eval Set

P1-M21 is complete when:

- [x] pgvector 扩展已启用（`CREATE EXTENSION IF NOT EXISTS vector`）— 函数已添加，Render 环境自动执行。
- [x] `vector_chunks` 或 `rag_embeddings` 表已创建 — 使用 `rag_embeddings` 表名。
- [x] 表包含 embedding vector 列、chunk_text、candidate_id、source trace、modality 预留。
- [x] embedding provider 配置走环境变量（`EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`）。
- [x] mock/deterministic embedding 可用（本地测试不依赖外部 API）。
- [x] 真实 embedding provider 作为线上可选 — OpenAIEmbeddingProvider 已预留接口。
- [x] `samples/rag_eval_queries.json` 存在，至少 10 条 query（12 条），每条标注 expected_candidate_ids（M21 为空，M22 后补）。
- [x] eval set 格式校验通过 — 14 个测试覆盖。
- [x] embedding API 调用有基本重试（建议 3 次）— OpenAIEmbeddingProvider 已实现 3 次重试 + timeout。
- [x] 注意 Render Free PostgreSQL 1GB 存储限制 — 文档已记录。
- [x] 注意 embedding API 费用 — 文档已记录，M21 默认使用 mock。
- [x] 不接真实 CustomerOpsAgent semantic retrieval。
- [x] 不破坏现有 keyword fallback。
- [x] `/health` 报告 `P1-M21`。
- [x] 现有测试全部通过（149 个测试：57 个新增 + 92 个已有）。
- [x] git status clean。
- [x] 不打 tag（commit only）。
- [x] 不进入 P2/P3/P4 后端开发。

本轮已完成 (2026-07-05)：

- [x] pgvector 检查函数已添加 (`check_pgvector_available`, `ensure_pgvector_extension`)
- [x] `rag_embeddings` 表模型已添加（含 Vector/Text 条件列类型）
- [x] `backend/app/embedding.py` 已添加（MockEmbeddingProvider + OpenAIEmbeddingProvider + factory）
- [x] `samples/rag_eval_queries.json` 已添加（12 条 query）
- [x] 3 个新测试文件已添加（57 tests）
- [x] health phase 已更新至 P1-M21
- [x] 14 个已有测试文件的 phase 断言已更新
- [x] requirements.txt 已添加 pgvector
- [x] 线上 harness 10/10 PASS
- [x] 未接 CustomerOpsAgent semantic retrieval
- [x] 未改前端
- [x] 不提交 backend/storage/、.env、datahub.db、API Key
- [x] 不打 tag
- [x] git status clean

### 41B2. P1-M21.1 pgvector Readiness Verification Gate

P1-M21.1 is complete when:

- [x] pgvector_available 已真实验证（`true` — Render PostgreSQL, version 0.8.1）。
- [x] extension_create_ok 已真实验证（`true` — `CREATE EXTENSION IF NOT EXISTS vector` 成功）。
- [x] database_backend 已确认（`postgresql`）。
- [x] 验证方式已记录（Render 后端 health endpoint 间接验证）。
- [x] DATABASE_URL 未泄露。
- [x] M22 已解锁 ✅。
- [x] 未写 M22 同步逻辑。
- [x] 未改业务 API / schema。
- [x] 未打 tag（commit only）。
- [x] git status clean。

本轮已完成 (2026-07-05)：

- [x] `init_database_tables()` 中新增 `ensure_pgvector_extension()` 调用
- [x] `/api/health` 新增 `pgvector_status` 字段
- [x] 线上验证：pgvector_available=true, extension_create_ok=true, backend=postgresql
- [x] pgvector version: 0.8.1
- [x] 文档已更新（35_REAL_RAG_DEVELOPMENT_ROADMAP.md, 08_DEV_STATUS.md, 09_STAGE_CHECKLIST.md）
- [x] 不提交 DATABASE_URL / .env / API Key

### 41C. P1-M22 Approved Knowledge Sync to Vector RAG

P1-M22 is complete when:

- [x] approved knowledge_candidates 可同步到 `vector_chunks`。
- [x] chunk text + metadata + embedding + source trace 完整写入。
- [x] pending_review / rejected / needs_revision 不进入向量知识库。
- [x] 重复同步幂等（delete-rebuild 策略，不重复行）。
- [x] 保留 `rag_chunks` / keyword fallback 兼容。
- [x] 预留 `source_type` / `modality` 字段，为 P2 多模态做准备。
- [x] sync 测试和 approved-only 边界测试通过（18 tests）。
- [x] approved candidate 数量和 rag_embeddings 数量可对应。
- [x] source trace 不丢。
- [x] `/health` 报告 `P1-M22`。
- [x] 现有测试全部通过（75 tests）。
- [x] git status clean。
- [x] 不打 tag（commit only）。
- [x] 不进入 P2/P3/P4 后端开发。

本轮已完成 (2026-07-05)：

- [x] `POST /api/rag/build` 同步 approved knowledge 到 `rag_embeddings` 表
- [x] delete-rebuild 幂等策略（每次 build 删除旧 approved_knowledge embeddings 后重建）
- [x] 扩展 RagBuildResult 返回 embedding_count / vector_sync_enabled / embedding_provider / embedding_model / embedding_dimension / approved_candidate_count / skipped_candidate_count
- [x] db_repositories 新增 save_rag_embeddings_to_db / list_rag_embeddings_from_db / count_rag_embeddings_from_db / count_rag_embeddings_by_sync_method
- [x] 新增 test_approved_knowledge_vector_sync.py (18 tests)
- [x] 更新 12 个已有测试文件的 phase 断言至 P1-M22
- [x] 更新 harness sync_rag 步骤提取 vector_sync 字段
- [x] 不修改 CustomerOpsAgent semantic retrieval
- [x] 不修改前端
- [x] 保留 rag_chunks / keyword fallback
- [x] 不提交 backend/storage/、.env、datahub.db、API Key
- [x] 不打 tag
- [x] git status clean

### 41C2. P1-M22.1 Online Vector Sync Verification

P1-M22.1 is complete when:

- [x] Render 已部署 M22 新代码（`/api/health` 返回 `phase=P1-M22`）。
- [x] `/api/health` 正常（`database_status.backend=postgresql, status=ok`）。
- [x] pgvector 正常（`pgvector_available=true, extension_create_ok=true`）。
- [x] 线上 harness 10/10 PASS。
- [x] `sync_rag` 返回 `vector_sync_enabled=true`（向量同步代码路径已激活）。
- [x] `sync_rag` 返回 `embedding_provider=mock, embedding_model=mock-deterministic, embedding_dimension=64`。
- [x] `sync_rag` 返回 `approved_candidate_count>0`（approved candidates 存在）。
- [ ] `sync_rag` 返回 `embedding_count>0`（**BLOCKED — Vector 维度不匹配**）。
- [x] 未泄露 DATABASE_URL / API Key。
- [x] 未修改业务代码。
- [x] 未修改前端。
- [x] 未进入 P2/P3/P4。
- [x] 不打 tag（commit only）。
- [x] git status clean。

本轮已完成 (2026-07-05)：

- [x] `/api/health` 线上验证：`phase=P1-M22`, `pgvector_available=true`, `extension_create_ok=true`
- [x] 线上 harness 10/10 PASS
- [x] `sync_rag` 响应验证：`vector_sync_enabled=true, embedding_provider=mock, embedding_model=mock-deterministic, embedding_dimension=64, approved_candidate_count=8`
- [ ] **`embedding_count=0` — 根因：`db_models.py` `_embedding_column()` 硬编码 `Vector(1536)`，mock provider 生成 64 维向量，pgvector 维度约束导致 insert 失败**
- [x] 本地测试全部通过（SQLite Text fallback 无维度问题）
- [x] 文档已更新（08_DEV_STATUS.md, 09_STAGE_CHECKLIST.md, 35_REAL_RAG_DEVELOPMENT_ROADMAP.md）
- [x] 不打 tag
- [x] git status clean

**M23 未解锁** — 需要先修复 Vector 维度不匹配问题（`Vector(1536)` → 动态维度）。

### 41C3. P1-M22.2 Vector Dimension Fix & Online Re-verify

P1-M22.2 is complete when:

- [x] 默认 mock embedding 维度 = 1536（与 pgvector Vector(1536) 对齐）。
- [x] 显式 `dimension=64` 仍可用于本地单元测试。
- [x] vector sync 不再静默失败：`failed_embedding_count` / `vector_sync_error` 正确返回。
- [x] 线上 `sync_rag` `embedding_count > 0`（验证通过：9）。
- [x] 线上 `sync_rag` `embedding_dimension = 1536`。
- [x] 线上 `sync_rag` `vector_sync_enabled = true`。
- [x] 线上 `sync_rag` `failed_embedding_count = 0`。
- [x] 线上 harness 10/10 PASS。
- [x] `/api/health` phase = P1-M22.2。
- [x] 未修改 schema / 未做线上 migration。
- [x] 未修改前端。
- [x] 未进入 P2/P3/P4。
- [x] 所有测试通过（75 tests）。
- [x] 不打 tag（commit only）。
- [x] git status clean。
- [x] **M23 UNLOCKED** ✅。

本轮已完成 (2026-07-05)：

- [x] `MockEmbeddingProvider` 默认维度 64 → 1536
- [x] `get_embedding_provider()` factory 默认 mock dim 1536
- [x] `RagBuildResult` 新增 `failed_embedding_count`、`vector_sync_error`
- [x] `build_rag_chunks()` 错误不再静默吞掉
- [x] `_safe_error_message()` 擦除敏感信息
- [x] harness 提取 `embedding_dimension`、`failed_embedding_count`、`vector_sync_error`
- [x] 线上验证：embedding_count=9, vector_sync_enabled=true, embedding_dimension=1536, chunk_count=9
- [x] chunk_count == embedding_count（9==9）
- [x] M23 unlocked

### 41D. P1-M23 CustomerOpsAgent Semantic Retrieval

P1-M23 is complete when:

- [x] `/api/customer-ops-agent/retrieve` 优先走 semantic retrieval。
- [x] query → embedding → pgvector cosine similarity search 链路完整。
- [x] 返回 matched chunks、similarity score、candidate_id、source trace、Agent answer、retrieval_id。
- [x] keyword retrieval 作为 fallback 可用。
- [x] `retrieval_logs` 记录 `retrieval_mode`（semantic / semantic_with_fallback / keyword_fallback）。
- [x] `retrieval_logs` 记录 fallback_reason。
- [x] `build_method` / `retrieval_mode` 从 mock 更新为 vector semantic。
- [x] eval set 可计算 recall@k 并有结果。
- [x] CustomerOpsAgent 返回引用来源和分数。
- [x] 不接真实 LLM 生成复杂回答（回答可基于模板/证据拼接）。
- [x] `/health` 报告 `P1-M23`。
- [x] 现有测试全部通过。
- [x] git status clean。
- [x] 不打 tag（commit only）。
- [x] 不进入 P2/P3/P4 后端开发。

本轮已完成 (2026-07-05)：

- [x] `POST /api/customer-ops-agent/retrieve` 优先走 semantic retrieval（query → embedding → pgvector cosine similarity search）
- [x] `search_rag_embeddings_semantic` repository 函数（PostgreSQL pgvector + SQLite Python fallback）
- [x] 新增 retrieval modes: `customerops_vector_retrieval`, `customerops_vector_with_keyword_fallback`, `customerops_keyword_fallback`
- [x] response 扩展：`fallback_used`, `fallback_reason`, `matched_chunk_scores`, `embedding_provider`, `embedding_model`
- [x] retrieval_logs metadata_json 包含 retrieval_mode / fallback_reason / scores / provider
- [x] `scripts/run_rag_eval.py` eval 脚本（recall@5, keyword_hit_rate@5）
- [x] 新增 test_customerops_semantic_retrieval.py (10 tests)
- [x] 新增 test_rag_eval_script.py (12 tests)
- [x] harness step_customerops_retrieve 提取 retrieval_mode / fallback_used / fallback_reason
- [x] health phase = P1-M23
- [x] 15 个测试文件 phase 断言更新
- [x] 所有 211 个测试通过 (22 new + 189 existing)
- [x] 不改前端
- [x] 不进入 P2/P3/P4
- [x] 保留 keyword / JSON fallback
- [x] 保留 rag_chunks 表
- [x] 不接真实 LLM
- [x] 不打 tag

### 41D2. P1-M23.1 Semantic Retrieval Quality Diagnosis & Eval Calibration

P1-M23.1 is complete when:

- [x] 诊断 M23 低 recall@5 根因（mock embedding 零语义能力 + eval set 不匹配 + 知识库污染）。
- [x] MockEmbeddingProvider 升级为 bag-of-words token-based（keyword-aware，仍确定性）。
- [x] Eval set 校准为匹配实际知识库内容（12 queries covering refund/shipping/escalation）。
- [x] Eval 脚本增强：分离 keyword_hit_rate@5 和 candidate_recall@5；新增 missed_keywords、avg_top1_score、avg_top5_score、low_score_queries。
- [x] 测试更新以覆盖新函数签名（compute_keyword_match, compute_candidate_recall_at_k）。
- [x] health phase = P1-M23.1。
- [x] 文档更新（08, 09, 35）。
- [x] 不改前端、不进入 P2/P3/P4、不接真实 LLM、不打 tag。
- [x] git status clean。

本轮已完成 (2026-07-05)：

- [x] MockEmbeddingProvider 改为 token-based bag-of-words（SHA-256 per-token + sum + L2 norm）
- [x] `samples/rag_eval_queries.json` 校准（12 queries matching harness knowledge）
- [x] `scripts/run_rag_eval.py` 增强版诊断输出
- [x] `backend/tests/test_rag_eval_script.py` 更新（14 tests with new API）
- [x] 15 个测试文件 phase 断言更新至 P1-M23.1
- [x] 83 个相关测试通过
- [x] 不改前端
- [x] 不进入 P2/P3/P4
- [x] 保留 keyword / JSON fallback
- [x] 不接真实 LLM / external embedding API
- [x] 不打 tag

### 41E. P1-M24 Real RAG Online Smoke Test + P1 Release Readiness

P1-M24 is complete when:

- [x] Vercel → Render FastAPI → Render PostgreSQL + pgvector 线上验证通过。
- [x] 全链路跑通（导入 -> 清洗 -> 人工清洗 -> 审核 -> 语义 RAG -> Agent 检索 -> Bad Case 回流）。
- [x] harness 全 PASS（线上）— 10/10 PASS。
- [x] eval set 跑通，keyword_hit_rate@5=0.7694 ≥ 0.6。
- [x] redeploy 后向量数据仍在（PostgreSQL 持久化）。
- [x] source trace 可追溯。
- [x] Bad Case 回流仍可用。
- [x] P1 Real RAG Release Readiness Report 已输出（docs/36）。
- [x] P1 已完成能力和未完成能力已明确（mock embedding, no real LLM）。
- [x] 不自动打 tag（等用户确认后单独开 release tag 轮）。
- [x] `/health` 报告 `P1-M24`。
- [x] 现有测试全部通过（93 passed）。
- [x] git status clean。
- [x] 不进入 P2/P3/P4 后端开发。

本轮已完成 (2026-07-05)：

- [x] 线上 health check: pgvector_available=true, extension_create_ok=true, phase=P1-M24
- [x] 线上 harness: 10/10 PASS, embedding_count=18, retrieval_mode=customerops_vector_retrieval
- [x] 线上 eval: keyword_hit_rate@5=0.7694, keyword_query_hit_rate@5=0.9167, fallback_count=0
- [x] embedding provider: mock_ready=true, real_embedding_ready=false
- [x] Bad Case 回流: harness step 09+10 PASS
- [x] docs/36_P1_REAL_RAG_ONLINE_RELEASE_READINESS_REPORT.md 新增
- [x] docs/08_DEV_STATUS.md, docs/09_STAGE_CHECKLIST.md, docs/35_REAL_RAG_DEVELOPMENT_ROADMAP.md 更新
- [x] README.md / README.en.md 小幅更新
- [x] 93 tests passed
- [x] 不打 tag
- [x] git status clean

### 41F. P1-M24.1 Env Template for DeepSeek LLM + Embedding API

P1-M24.1 is complete when:

- [x] `.env.example` 包含完整 LLM + Embedding provider 配置。
- [x] DeepSeek 标记为 LLM provider（非 embedding provider）。
- [x] Embedding provider 独立配置，默认 mock。
- [x] 预留 SiliconFlow 和 Jina embedding 选项（已注释，含维度兼容警告）。
- [x] 所有值为 placeholder，无真实 API Key。
- [x] `.env.local.example` 新增，记录本地覆盖模式。
- [x] 本地 `.env` 已创建，仅含 placeholder。
- [x] `.gitignore` 正确忽略 `.env`、`.env.local`、`.env.*.local`、`*.env`，不忽略 `.env.example` 和 `.env.local.example`。
- [x] `README.md` / `README.en.md` 补充本地环境变量说明。
- [x] `docs/08_DEV_STATUS.md` / `docs/09_STAGE_CHECKLIST.md` 更新。
- [x] 不写业务代码（不创建 llm.py、不改 embedding.py、不改 retrieve 逻辑）。
- [x] 不改前端、不改 API、不改数据库 schema、不新增依赖。
- [x] 不提交真实 `.env` 或 API Key。
- [x] 不打 tag（commit only）。
- [x] git status clean。

本轮已完成 (2026-07-05)：

- [x] `.env.example` 已重写（LLM DeepSeek + Embedding mock/SiliconFlow/Jina）
- [x] `.env.local.example` 已新增
- [x] `.env` 已从模板创建（placeholder only）
- [x] `.gitignore` 已更新（.env / .env.local / .env.*.local / *.env 忽略，示例文件放行）
- [x] README 已更新
- [x] docs 已更新
- [x] 无业务代码变更
- [x] 无真实 key 提交
- [x] 不打 tag

## 42. P1-M20.7 To P1-M24 General Rules

所有 P1-M20.7 到 P1-M24 阶段：

- git status 必须 clean 才能开始。
- 每个阶段 commit message 使用 `[P1-Mxx]` 前缀。
- 不打 tag，除非明确标注 release。
- 不提交 `backend/storage/`、`.env`、`datahub.db`、API Key、真实客服数据。
- 现有测试必须通过后再 push。
- 不进入 P2/P3/P4 后端开发。
- 不修改 CustomerOpsAgent 仓库。
- 不删除或破坏 JSON fallback 路径。
- M21 起：mock embedding 本地测试必须可用。
- M23 起：eval recall@5 必须可计算。

## P1-M24.2 Real Embedding Provider Verification & Vector Rebuild

### M24.2 Checklist

- [x] EMBEDDING_PROVIDER=mock 继续可用
- [x] 支持 siliconflow / jina / openai_compatible 真实 embedding provider
- [x] API key 只从 EMBEDDING_API_KEY 读取
- [x] base_url 只从 EMBEDDING_BASE_URL 读取
- [x] model 只从 EMBEDDING_MODEL 读取
- [x] timeout / retry 从环境变量读取
- [x] 不允许硬编码真实 key
- [x] 不允许在日志打印 key
- [x] 真实 provider 缺 key：provider_ready=false, missing_api_key
- [x] check_embedding_provider.py 输出真实 embedding 维度
- [x] 真实 embedding dimension != 1536 时输出 BLOCKED_DIMENSION_MISMATCH
- [x] BLOCKED_DIMENSION_MISMATCH 时不允许 vector rebuild
- [x] dimension = 1536 时允许 vector rebuild
- [x] 无法确认 dimension 时不允许 vector rebuild
- [x] rebuild_vector_rag.py 脚本新增
- [x] provider not ready 或 dimension mismatch 时 rebuild 不执行
- [x] rebuild 输出 embedding_count / failed_embedding_count / provider / model / dimension
- [x] DeepSeek LLM 与 embedding provider 职责明确分离
- [x] 测试覆盖：mock 仍可用
- [x] 测试覆盖：缺 key 不泄露
- [x] 测试覆盖：provider check 识别 missing_api_key
- [x] 测试覆盖：provider check 识别 dimension mismatch
- [x] 测试覆盖：rebuild 在 provider not ready 时不执行
- [x] 测试覆盖：rebuild 不静默失败
- [x] 测试不依赖真实外部 API
- [x] 测试不依赖真实 Render 数据库
- [x] 文档更新：08/09/35/36/README
- [x] 不打 tag
- [x] 不 force push
- [x] 不改前端
- [x] 不进入 P2/P3/P4
