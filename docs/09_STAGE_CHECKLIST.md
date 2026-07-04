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
