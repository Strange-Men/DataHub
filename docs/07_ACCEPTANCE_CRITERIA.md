# DataHub Acceptance Criteria

This document defines milestone-level acceptance criteria. Each milestone should be accepted before moving to the next one.

## Canonical State Names

Use these canonical state names in implementation and documentation:

```text
raw_imported
sanitized
pending_review
needs_revision
approved
rejected
rag_chunked
indexed
```

Rules:

- `pending_review` is the candidate review state. Do not use `review_pending`.
- `approved` means human review passed, but it does not mean RAG chunks or production indexing exist.
- `rag_chunked` means M6 local RAG chunks exist.
- `indexed` is reserved for future real vector store or production retrieval index status.
- Current M6/M6.5 stops at `rag_chunked`; it is not production `indexed`.
- `knowledge candidate` is used for M4-M5 records.
- `approved candidate` is the M5 state before M6 local RAG chunking.
- A future `knowledge_item` or formal knowledge asset store requires separate planning.

## M0 Documentation Baseline

Goal:

- Solidify phase-one scope, architecture direction, API draft, development rules, technical candidates, and milestone acceptance criteria.

Acceptance criteria:

- `docs/00_PROJECT_SCOPE.md` exists and defines what DataHub is and is not.
- `docs/01_IDEA_PRESSURE_TEST.md` exists and explains why the project is worth building and why scope must be narrowed.
- `docs/02_PRD.md` exists and defines phase-one product requirements.
- `docs/03_ARCHITECTURE.md` exists and uses React + TypeScript and FastAPI + Python as the main architecture direction.
- `docs/04_API_CONTRACT.md` exists and defines first-phase API drafts.
- `docs/05_DEV_RULES.md` exists and defines development guardrails.
- `docs/06_TECH_STACK_CANDIDATES.md` exists and keeps non-confirmed technology choices as candidates.
- `docs/07_ACCEPTANCE_CRITERIA.md` exists and defines milestone acceptance.
- No business feature code is implemented.
- No dependencies are installed.
- No RAG implementation is started.

## M1 Project Initialization

Goal:

- Initialize a minimal project structure without implementing business workflows.

Acceptance criteria:

- React + TypeScript frontend scaffold exists.
- FastAPI + Python backend scaffold exists.
- Basic project commands are documented.
- Environment variable example file exists without real secrets.
- Git ignore rules prevent committing secrets, caches, and local data.
- Basic health check endpoint may exist if needed for setup verification.
- No data import, extraction, RAG, Bad Case, or CustomerOpsAgent business logic is implemented yet.

## M2 Data Import

Goal:

- Import customer service chat records into DataHub.

Acceptance criteria:

- CSV, JSON, or manual input is supported according to the selected MVP order.
- Import batch metadata is stored.
- Raw records are stored in the raw data layer.
- Invalid input returns safe structured errors.
- Duplicate import detection or warning exists at a basic level.
- Raw data is not exposed to CustomerOpsAgent APIs.
- Tests or manual verification cover successful import and invalid input.

## M3 Cleaning And Desensitization

Goal:

- Convert raw records into cleaned and sanitized records.

Acceptance criteria:

- Empty or invalid records are filtered or marked.
- Exact duplicates are detected.
- Sensitive information is masked for supported patterns.
- Sanitized records are stored separately from raw records.
- Cleaning job status can be checked.
- Extraction cannot start unless data is sanitized.
- Logs and errors do not expose raw private data.

## M4 Knowledge Extraction

Goal:

- Generate reviewable knowledge drafts from sanitized records.

Acceptance criteria:

- Extraction only reads sanitized records.
- Drafts can be created for:
  - FAQ
  - Standard answer
  - Business rule
  - Human-handoff rule
  - Forbidden-answer rule
- Each draft includes source references.
- Drafts are created in `pending_review` or equivalent state.
- Drafts are not searchable by CustomerOpsAgent.
- Mock mode or controlled LLM mode is available before real uncontrolled LLM usage.

## M5 Human Review

Goal:

- Allow humans to control which knowledge becomes approved.

Acceptance criteria:

- Reviewers can list pending drafts.
- Reviewers can edit draft content.
- Reviewers can approve drafts.
- Reviewers can reject drafts.
- Reviewers can mark drafts as needing revision.
- Manual knowledge supplements can be created as drafts.
- Approved knowledge includes reviewer, timestamp, version, and source references.
- Rejected and pending knowledge cannot enter RAG.

## M6 RAG Build

Goal:

- Build local RAG chunks from approved candidates only.

Acceptance criteria:

- Local RAG build accepts approved candidates only.
- Pending, needs-revision, rejected, raw, or sanitized-only records are skipped or rejected by RAG chunking.
- RAG chunks preserve candidate id, knowledge type, tags, and source metadata.
- Internal M6 retrieval returns only local chunks created from approved candidates.
- Retrieval results include traceable source information.
- Build failures are visible and safe.

## M7 CustomerOpsAgent Integration

Goal:

- Allow CustomerOpsAgent to retrieve approved local RAG chunks through DataHub APIs.

Acceptance criteria:

- CustomerOpsAgent retrieval API exists.
- Retrieval trace lookup API exists.
- Request validation is enforced.
- Query length limit is enforced.
- API returns topK approved retrieval-ready results.
- At the current local stage, retrieval-ready may mean approved `rag_chunked` records.
- Production `indexed` retrieval is a later hardening step.
- API returns retrieval id for later Bad Case linkage.
- Retrieval traces are saved under ignored local storage.
- API never returns raw records, unapproved drafts, rejected knowledge, or archived knowledge.
- CustomerOpsAgent has no direct database access.
- CustomerOpsAgent repository is not modified by DataHub M7.
- No Bad Case API or workflow is implemented in M7.

## M8 Bad Case Feedback

Goal:

- Close the improvement loop from CustomerOpsAgent back to DataHub.

Acceptance criteria:

- CustomerOpsAgent can submit Bad Cases.
- Bad Cases must bind to an existing `retrieval_id`.
- Bad Cases store user query, agent answer, issue type, expected answer if available, retrieval id, linked chunk ids, retrieval result count, and metadata.
- Bad Cases enter `open` state by default.
- Human reviewers can update management status and review notes.
- Allowed statuses are `open`, `triaged`, `resolved`, and `ignored`.
- M8 does not create new knowledge drafts or update existing knowledge drafts.
- Bad Case fixes must pass a later normal review flow before entering RAG.
- Bad Cases cannot directly update candidates, approved knowledge, RAG chunks, or the RAG index.
- Bad Cases cannot trigger automatic RAG rebuild or re-index.

## M9 Phase-One Release Freeze

Goal:

- Stabilize the phase-one text knowledge loop.

Acceptance criteria:

- P1 core flow works end to end:

```text
import
-> clean and desensitize
-> extract drafts
-> human review
-> build local RAG chunks from approved candidates
-> CustomerOpsAgent retrieval
-> Bad Case feedback
-> human correction
-> pending_review draft creation
```

- Security rules are verified.
- Raw and unapproved data cannot be retrieved.
- Source traceability exists for approved knowledge.
- Documentation reflects the implemented behavior.
- Known limitations are recorded.
- Git tag `p1-m9-phase-one-release-freeze` is created.
- Historical tags are not moved, deleted, or renamed.
- At the P1-M9 checkpoint, P1-M9.5 public dataset evaluation was not implemented yet.
- At the P1-M9 checkpoint, P1-M10 legacy RAG migration was not implemented yet.
- At the P1-M9 checkpoint, P1-M11 unified RAG release was not implemented yet.
- Future extensions are documented but not implemented:
  - Multimodal.
  - MCP.
  - Fine-tuning export.
  - Sales Agent.
  - Operations Agent.

## M6.5 RAG Quality Hardening Completion Check

M6.5 is complete when:

- RAG build remains local JSON plus mock retrieval only.
- RAG build is idempotent for unchanged approved candidates.
- Repeated RAG build does not create duplicate chunks.
- Existing chunks are updated only when candidate-derived chunk content changes.
- Build response includes:
  - `built_count`
  - `updated_count`
  - `skipped_count`
  - `chunk_count`
  - `skipped_reasons`
  - `status`
- Only `approved` candidates become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- Search query is trimmed and validated.
- Empty query, overlong query, and invalid `top_k` return safe errors.
- `top_k` defaults to 5 and is limited to 1-10.
- Search scoring remains local keyword/mock scoring.
- Search results include:
  - `score`
  - `matched_terms`
  - `chunk_id`
  - `candidate_id`
  - source trace
- No CustomerOpsAgent integration, Bad Case workflow, vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## M7 CustomerOpsAgent Retrieval Completion Check

M7 is complete when:

- `POST /api/customer-ops-agent/retrieve` exists.
- `GET /api/customer-ops-agent/retrievals/{retrieval_id}` exists.
- `/health` reports `phase: M7`.
- Retrieval reads only from `backend/storage/rag_chunks/`.
- Retrieval does not read raw batches directly.
- Retrieval does not read sanitized batches directly.
- Retrieval does not read knowledge candidates directly.
- Only approved local `rag_chunked` results are returned.
- `pending_review`, `needs_revision`, and `rejected` data is not returned.
- Request validation covers:
  - trimmed non-empty query
  - query maximum length of 500 characters
  - `top_k` default 5
  - `top_k` range 1-10
- Results include:
  - `retrieval_id`
  - `retrieval_mode`
  - `score`
  - `matched_terms`
  - `chunk_id`
  - `candidate_id`
  - source trace
- Retrieval traces are saved under `backend/storage/retrieval_logs/`.
- Retrieval traces include result chunk ids for later M8 Bad Case linkage.
- M7 does not implement Bad Case submission, Bad Case UI, or human correction workflow.
- M7 does not modify the CustomerOpsAgent repository.
- M7 remains local JSON plus keyword/mock retrieval only.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## M7.5 Retrieval Contract Polish Completion Check

M7.5 is complete when:

- `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md` exists.
- The contract document defines:
  - `POST /api/customer-ops-agent/retrieve`
  - `GET /api/customer-ops-agent/retrievals/{retrieval_id}`
  - required `X-DataHub-Client: CustomerOpsAgent` header
  - current capabilities
  - current non-capabilities
  - CustomerOpsAgent do/don't rules
  - PowerShell examples
  - M8 `retrieval_id` linkage
- Both CustomerOpsAgent retrieval APIs require the local auth placeholder header.
- Missing or invalid `X-DataHub-Client` returns `UNAUTHORIZED_CLIENT`.
- CustomerOpsAgent retrieval API errors use the safe structure:
  - `success: false`
  - `error.code`
  - `error.message`
  - `error.details`
  - `requestId`
- Empty query returns `INVALID_QUERY`.
- Overlong query returns `QUERY_TOO_LONG`.
- `top_k` below 1 or above 10 returns `INVALID_TOP_K`.
- Missing retrieval trace returns `RETRIEVAL_NOT_FOUND`.
- No RAG chunks still returns an empty result list, not an error.
- No API key, real token, `.env` secret, production auth, CustomerOpsAgent repository change, vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## M8 Bad Case Feedback Completion Check

M8 is complete when:

- `POST /api/customer-ops-agent/bad-cases` exists.
- `GET /api/bad-cases` exists.
- `GET /api/bad-cases/{bad_case_id}` exists.
- `PATCH /api/bad-cases/{bad_case_id}` exists.
- `/health` reports `phase: M8`.
- CustomerOpsAgent Bad Case submission requires `X-DataHub-Client: CustomerOpsAgent`.
- Missing or invalid header returns `UNAUTHORIZED_CLIENT`.
- Bad Case submission validates `retrieval_id` against existing retrieval logs.
- Bad Cases are saved under `backend/storage/bad_cases/`.
- Bad Cases store `linked_chunk_ids` and `retrieval_result_count` from the retrieval trace.
- Bad Case records default to `status: open`.
- PATCH can update `status`, `review_note`, `resolution_type`, and `linked_candidate_id`.
- PATCH records manual handling only.
- PATCH does not create candidates.
- PATCH does not modify existing candidates.
- PATCH does not modify RAG chunks.
- PATCH does not rebuild or re-index RAG.
- The CustomerOpsAgent repository is not modified.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## Future Phase Acceptance Outline

These outlines describe the long-term product roadmap. They are not permission to start implementation before Phase 1 is accepted.

### Phase 2 Multimodal Material Integration

Goal:

- Extend DataHub from text customer service knowledge into AI Material Center and multimodal asset governance.

Acceptance outline:

- AI Material Center assets can be imported as governed data sources.
- Image, poster, and later video assets have metadata records.
- OCR, Caption, tags, and SKU binding can be generated or edited.
- Human reviewers can approve or reject material understanding results.
- Approved multimodal assets can enter a multimodal knowledge store.
- Multimodal retrieval results preserve asset source, review, and SKU traceability.
- CustomerOpsAgent can later use approved multimodal knowledge for image-text customer service.
- Raw or unreviewed assets cannot be retrieved by Agent consumers.

### Phase 3 Sales Training And Fine-Tuning Dataset Export

Goal:

- Export reviewed high-quality knowledge into human training materials and model improvement datasets.

Acceptance outline:

- Approved FAQ, SOP, scripts, typical cases, excellent replies, and Bad Case fixes can be selected for export.
- Sales onboarding outputs can include FAQ handbooks, SOP, script handbooks, typical cases, and quiz questions.
- Fine-tuning exports can produce SFT and Preference-style datasets.
- Exported records preserve source and review traceability.
- Private data remains desensitized before export.
- Exported datasets are clearly labeled as generated artifacts, not production model training runs.

### Phase 4 MCP And Agent Cluster Integration

Goal:

- Package DataHub capabilities as stable tools for multiple Agents.

Acceptance outline:

- MCP Tools expose governed capabilities such as:
  - `search_customer_knowledge`
  - `search_multimodal_assets`
  - `submit_bad_case`
  - `export_training_dataset`
  - `export_finetune_dataset`
- CustomerOpsAgent, SalesAgent, OpsAgent, and MaterialAgent can call the appropriate tools.
- Tool permissions prevent Agents from bypassing review.
- Tool responses return only approved, indexed, and authorized data.
- Bad Case submission enters a governed review workflow.
- Tool contracts are documented and versioned.

## M8.5 Bad Case Resolution To Draft Completion Check

M8.5 is complete when:

- `POST /api/bad-cases/{bad_case_id}/create-draft` exists.
- `/health` reports `phase: M8.5`.
- Existing Bad Cases with `open`, `triaged`, or `resolved` status can create a draft.
- `ignored` Bad Cases return `BAD_CASE_IGNORED`.
- Missing Bad Cases return `BAD_CASE_NOT_FOUND`.
- Invalid draft fields return `INVALID_DRAFT_PAYLOAD`.
- Created candidates are saved under `backend/storage/knowledge_candidates/`.
- Created candidate ids start with `kc_badcase_`.
- Created candidates use `source_type: bad_case`.
- Created candidates include:
  - `source_bad_case_id`
  - `source_retrieval_id`
  - `source_chunk_ids`
- Created candidates use `extraction_method: bad_case_resolution`.
- Created candidates always use `review_status: pending_review`.
- Bad Case records update `linked_candidate_id` to the new candidate.
- Existing candidates are not modified.
- RAG chunks are not modified.
- RAG build is not triggered automatically.
- The CustomerOpsAgent repository is not modified.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## P1-M9 Release Freeze Completion Check

P1-M9 is complete when:

- `backend/tests/test_phase_one_flow.py` verifies the P1 core loop.
- `/health` reports `phase: P1-M9`.
- Existing M6.5, M7.5, and M8.5 tests pass.
- The release report exists at `docs/13_P1_RELEASE_FREEZE_REPORT.md`.
- README documents P1-M9 status and remaining P1 milestones.
- `docs/08_DEV_STATUS.md` and `docs/09_STAGE_CHECKLIST.md` document phase-prefixed tag naming.
- P1-M9 tag is `p1-m9-phase-one-release-freeze`.
- Rejected and needs-revision candidates are not chunked into RAG.
- CustomerOpsAgent retrieval reads only approved local RAG chunks.
- Bad Case-generated drafts remain `pending_review`.
- Bad Case-generated drafts do not automatically approve, rebuild RAG, or re-index.
- No CustomerOpsAgent repository changes are made.
- No public dataset evaluation, legacy RAG migration, unified RAG switching, vector database, embedding, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.

## P1-M10 Legacy RAG Migration Completion Check

P1-M10 is complete when:

- `/health` reports `phase: P1-M10`.
- `POST /api/legacy-rag/import` exists.
- `GET /api/legacy-rag/imports` exists.
- `GET /api/legacy-rag/imports/{import_id}` exists.
- `samples/legacy_rag_export_sample.json` exists and contains fake legacy RAG data only.
- Legacy import metadata is saved under `backend/storage/legacy_rag_imports/`.
- Generated legacy candidates are saved under `backend/storage/knowledge_candidates/`.
- Generated legacy candidates include:
  - `source_type: legacy_rag`
  - `source_legacy_id`
  - `source_import_id`
  - `migration_mode`
  - `extraction_method: legacy_rag_migration`
- `trusted_import=true` creates `approved` candidates.
- `trusted_import=false` creates `pending_review` candidates.
- Re-importing the same `source_name + legacy_id` does not create duplicate candidates.
- Changed legacy items update the same stable candidate instead of creating a duplicate.
- Trusted approved legacy candidates can enter existing local RAG build.
- Review-required legacy candidates cannot enter local RAG build.
- CustomerOpsAgent retrieval can return approved legacy chunks with source trace.
- CustomerOpsAgent repository is not read or modified.
- At the P1-M10 checkpoint, P1-M11 unified RAG release was not implemented yet.
- No real vector database, embedding model, database, ORM, real LLM, multimodal, MCP, sales export, or fine-tuning work is implemented.
- `backend/storage/` remains ignored by Git.

## P1-M11 Unified DataHub RAG Release Completion Check

P1-M11 is complete when:

- `/health` reports `phase: P1-M11`.
- `README.md` and `README.en.md` present P1-M11 as the completed Phase 1 release.
- Both READMEs contain STAR project breakdowns and verified metrics only.
- `docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md` exists.
- `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md` exists.
- `backend/tests/test_unified_rag_release.py` passes.
- Approved candidates from `chat_logs`, `public_dataset`, and trusted `legacy_rag` can become local RAG chunks.
- Bad Case-generated drafts remain `pending_review` until normal approval.
- Approved Bad Case drafts can become local RAG chunks.
- CustomerOpsAgent retrieval returns a consistent result shape with `source_type` and source trace.
- Pending, needs-revision, and rejected candidates cannot enter RAG.
- Repeated RAG build remains idempotent.
- CustomerOpsAgent repository is not modified.
- No real vector database, embedding model, database, ORM, real LLM, MCP, or P2/P3/P4 implementation is introduced.
- Tag `p1-m11-unified-rag-release` is created.
- Historical tags are not moved, deleted, or renamed.

## P1-M12 Advanced Machine Cleaning Completion Check

P1-M12 is complete when:

- `/health` reports `phase: P1-M12`.
- P1-M12 to P1-M15 high-quality DataHub roadmap is written into README and core docs.
- `POST /api/cleaning/run/{batch_id}` keeps the old response fields and adds:
  - `exact_duplicate_count`
  - `near_duplicate_count`
  - `low_quality_count`
  - `noise_count`
  - `review_recommended_count`
  - `drop_recommended_count`
  - `average_quality_score`
- `GET /api/sanitized/{batch_id}` returns message-level:
  - `cleaning_issues`
  - `risk_flags`
  - `quality_score`
  - `quality_level`
  - `suggested_action`
- Exact duplicate and near-duplicate detection are covered by tests.
- Low-quality, repeated-character, symbol-noise, possible-ad, and possible-noise flags are covered by tests.
- Enhanced PII detection covers email, phone, order id, tracking id, address, name-like text, ZIP/postal code, and payment-like long digit strings.
- Extraction skips sanitized messages with `suggested_action: drop`.
- Existing P1 tests continue to pass.
- `docs/18_ADVANCED_CLEANING_RULES.md` exists.
- No full manual cleaning frontend, P1-M14 review console, P1-M15 final release, P2/P3/P4, database, ORM, vector database, embedding model, real LLM, MCP, or CustomerOpsAgent repository change is introduced.
- Tag `p1-m12-advanced-data-cleaning` is created.
- Historical tags are not moved, deleted, or renamed.

## P1-M13 Chinese Admin Console & Manual Cleaning Workbench Outline

P1-M13 should be started only when explicitly requested.

Acceptance outline:

- Frontend is Chinese-first.
- Dashboard reserves P1/P2/P3/P4 module entries and marks unimplemented modules as Roadmap / Not Connected.
- Manual cleaning workbench shows raw versus sanitized comparison.
- Operators can correct sanitized content, mark keep/drop/review, and write cleaning notes.
- Cleaner operation guide is documented.
- `C:\Users\16432\Desktop\AI_workflow\前端工作流.md` is read and followed before frontend work.

## P1-M14 Knowledge Review Quality Console Outline

P1-M14 should be started only when explicitly requested.

Acceptance outline:

- Chinese review console supports candidate editing, approve, reject, and needs_revision.
- Review UI shows source trace, quality_score, cleaning_issues, and risk_flags.
- Reviewer guide defines standards for FAQ, standard answer, business rule, human handoff rule, and forbidden answer rule.
- No unreviewed candidate enters RAG.

## P1-M15 High-quality DataHub P1 Final Release Outline

P1-M15 should be started only when explicitly requested.

Acceptance outline:

- Full high-quality loop is validated:
  machine cleaning -> manual cleaning -> extraction -> human review -> unified RAG -> CustomerOpsAgent retrieval -> Bad Case feedback.
- Final P1 high-quality DataHub acceptance report is produced.
- P2 multimodal material ingestion remains a prepared next phase, not implemented inside P1-M15 unless separately requested.

## P1-M13 Acceptance Criteria

P1-M13 is accepted when:

- The React frontend is presented as a Chinese DataHub admin console.
- P1/P2/P3/P4 capability cards are visible.
- P2/P3/P4 cards clearly show Roadmap / not connected state.
- The manual cleaning workbench can load sanitized messages by `batch_id`.
- The workbench displays PII, cleaning issues, risk flags, quality score, quality level, and suggested action.
- A cleaner can edit sanitized content and save `manual_action`, `cleaner`, and `cleaning_note`.
- Manual cleaning records are saved under ignored local storage.
- Raw batch files remain read-only.
- Extraction skips `drop` and `needs_review` manual actions.
- Extraction uses `manual_cleaned_content` for `keep_edited`.
- P1 existing tests continue to pass.
- README files are product-oriented and do not claim roadmap modules are already implemented.

## P1-M14 Acceptance Criteria

P1-M14 is accepted when:

- The Chinese admin console includes a knowledge review workbench.
- Reviewers can load candidates from existing candidate APIs.
- Reviewers can filter candidates by review status, source type, quality level, intent, and keyword.
- The UI shows candidate id, source type, knowledge type, question, answer, intent, tags, risk level, quality score, review status, cleaning issues, risk flags, source trace, and timestamps.
- Reviewers can edit `question`, `answer`, `intent`, `tags`, `risk_level`, and `quality_score`.
- Reviewers can save edits.
- Reviewers can approve, reject, or mark candidates as `needs_revision`.
- Reviewer and review note are saved on review decisions.
- Review records are saved under ignored local storage.
- Approved candidates can enter local RAG chunks.
- Pending, needs-revision, and rejected candidates cannot enter RAG chunks.
- `docs/20_KNOWLEDGE_REVIEW_GUIDE.md` exists and is written for reviewers.
- P2/P3/P4 remain Roadmap / not connected.
- Existing P1 tests continue to pass.
