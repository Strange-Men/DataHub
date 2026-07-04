# DataHub API Contract Draft

This document defines the phase-one API contract and roadmap. Each section is marked as implemented, planned, or future roadmap.

Base assumptions:

- React admin UI calls management APIs.
- CustomerOpsAgent calls restricted retrieval and Bad Case APIs.
- All APIs return structured errors.
- Raw and unapproved data must never be retrievable by CustomerOpsAgent.

## 0. API Implementation Status

This document separates APIs by implementation status.

Implemented APIs: M2-P1-M15

- M2 JSON import.
- M3 cleaning and sanitization.
- M4 knowledge candidate extraction.
- M5 human review.
- M6 local RAG chunk build and local mock search.
- M6.5 local RAG quality hardening.
- M7 CustomerOpsAgent restricted retrieval over approved local RAG chunks.
- M7.5 CustomerOpsAgent retrieval contract polish, auth placeholder, and unified CustomerOps retrieval errors.
- M8 CustomerOpsAgent Bad Case submission and DataHub Bad Case queue management.
- M8.5 Bad Case conversion into pending-review knowledge candidate drafts.
- P1-M9 phase-one release freeze verification; no new API surface.
- P1-M9.5 public dataset evaluation; no new API surface.
- P1-M10 legacy RAG migration import APIs.
- P1-M11 unified DataHub RAG release; no new public API surface.
- P1-M12 advanced machine cleaning; no new public API surface, but cleaning responses and sanitized messages include additional quality and governance fields.
- P1-M13 manual cleaning API for sanitized messages.
- P1-M14 Chinese knowledge review console using existing candidate and review APIs.
- P1-M15 final high-quality DataHub release verification; no new public API surface.

Planned Phase 1 APIs: After P1-M15

- Approval and RAG rebuild for Bad Case-generated drafts through existing review/RAG steps.
- Future production retrieval hardening beyond local JSON plus mock retrieval.

Future Roadmap APIs: Phase 2-4

- Multimodal material ingestion and understanding.
- Sales training dataset export.
- Fine-tuning dataset export.
- MCP tool APIs for the Agent cluster.

Important M6 boundary:

- `POST /api/rag/build` and `POST /api/rag/search` are implemented as DataHub internal local RAG test APIs.
- Current `/api/rag/search` is not the official CustomerOpsAgent retrieval API.
- Current M6.5 uses local JSON plus keyword/mock retrieval.
- Current M6.5 does not use embeddings, a real vector database, database, ORM, or production RAG index.

Important M7 boundary:

- `POST /api/customer-ops-agent/retrieve` is the CustomerOpsAgent-facing restricted retrieval API.
- M7 still uses local JSON plus keyword/mock retrieval over approved `rag_chunked` records.
- M7 does not modify the CustomerOpsAgent repository.
- M7 does not implement Bad Case feedback.
- M7 does not use embeddings, a real vector database, database, ORM, real LLM, or production RAG index.

Important M7.5 boundary:

- CustomerOpsAgent retrieval APIs require `X-DataHub-Client: CustomerOpsAgent`.
- This header is a local development auth placeholder, not production authentication.
- M7.5 does not introduce API keys, real tokens, or `.env` secrets.
- M7.5 does not implement Bad Case feedback.
- The detailed CustomerOpsAgent contract is documented in `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`.

Important M8 boundary:

- `POST /api/customer-ops-agent/bad-cases` is implemented as the CustomerOpsAgent-facing Bad Case feedback entry.
- Bad Cases must bind to an existing `retrieval_id` stored under `backend/storage/retrieval_logs/`.
- Bad Cases are saved under `backend/storage/bad_cases/`.
- M8 only creates and manages Bad Case records.
- M8 does not create knowledge candidates, modify existing candidates, modify RAG chunks, rebuild RAG, or re-index.
- M8 does not modify the CustomerOpsAgent repository.

Important P1-M13 boundary:

- `PATCH /api/sanitized/{batch_id}/messages/{message_id}/manual-clean` is implemented for manual cleaning.
- The API updates sanitized batch messages only.
- The API never overwrites raw batch files.
- Manual cleaning records are saved under `backend/storage/manual_cleaning_records/`.
- `manual_action=drop` and `manual_action=needs_review` are excluded from extraction by default.
- `manual_action=keep_edited` makes extraction use `manual_cleaned_content`.
- Manual cleaning does not approve candidates and does not write RAG chunks.

## P1-M13 Manual Cleaning API

### PATCH `/api/sanitized/{batch_id}/messages/{message_id}/manual-clean`

Status: implemented.

Purpose:

Save a manual cleaning decision for one sanitized message.

Request:

```json
{
  "content": "Manually corrected sanitized content.",
  "manual_action": "keep_edited",
  "cleaner": "local_cleaner",
  "cleaning_note": "PII checked and business meaning preserved."
}
```

Fields:

- `content`: required, sanitized content after manual review.
- `manual_action`: required, one of `keep`, `keep_edited`, `drop`, `needs_review`.
- `cleaner`: required local cleaner identifier.
- `cleaning_note`: optional cleaning note.

Response:

```json
{
  "success": true,
  "data": {
    "record_id": "manual_clean_xxx",
    "batch_id": "batch_xxx",
    "message_id": "msg_xxx",
    "source_message_id": "source_msg_xxx",
    "conversation_id": "conv_xxx",
    "manual_cleaned_content": "Manually corrected sanitized content.",
    "manual_action": "keep_edited",
    "cleaner": "local_cleaner",
    "cleaning_note": "PII checked and business meaning preserved.",
    "created_at": "2026-07-03T10:00:00+00:00"
  },
  "requestId": "req_xxx"
}
```

Errors:

- `SANITIZED_MESSAGE_NOT_FOUND`: sanitized batch or message does not exist.
- validation error: missing content, invalid `manual_action`, or invalid cleaner field.

Updated sanitized message fields:

- `manual_cleaning_status`
- `manual_cleaned_content`
- `manual_action`
- `cleaner`
- `cleaning_note`
- `manual_cleaned_at`

## P1-M14 Knowledge Review Console API Usage

Status: implemented through existing APIs.

P1-M14 does not add a new review queue API. The Chinese review console reuses:

- `GET /api/knowledge/candidates`
- `GET /api/review/pending`
- `PATCH /api/knowledge/candidates/{candidate_id}`
- `POST /api/review/{candidate_id}/approve`
- `POST /api/review/{candidate_id}/reject`
- `POST /api/review/{candidate_id}/needs-revision`

Candidate editable fields:

- `question`
- `answer`
- `intent`
- `tags`
- `risk_level`
- `quality_score`

Review payload:

```json
{
  "reviewer": "local_reviewer",
  "review_note": "Approved: answer is accurate and safe."
}
```

Review states:

- `pending_review`
- `needs_revision`
- `approved`
- `rejected`

Hard RAG rule:

- `approved` candidates can enter `POST /api/rag/build`.
- `pending_review`, `needs_revision`, and `rejected` candidates cannot enter RAG.
- Review records continue to be saved under `backend/storage/review_records/`.

Important M8.5 boundary:

- `POST /api/bad-cases/{bad_case_id}/create-draft` creates a new `pending_review` candidate from a Bad Case.
- M8.5 generated candidates use `extraction_method: bad_case_resolution`.
- M8.5 records `source_bad_case_id`, `source_retrieval_id`, and `source_chunk_ids`.
- M8.5 does not auto-approve candidates.
- M8.5 does not modify existing candidates or RAG chunks.
- M8.5 does not rebuild or re-index RAG.

Important P1-M10 boundary:

- `POST /api/legacy-rag/import` imports CustomerOpsAgent legacy RAG export JSON into DataHub.
- P1-M10 does not read or modify the CustomerOpsAgent repository.
- P1-M10 does not switch CustomerOpsAgent to DataHub-only retrieval.
- Legacy items become normal DataHub knowledge candidates.
- `trusted_import=true` creates approved candidates with `migration_mode: trusted_import`.
- `trusted_import=false` creates pending-review candidates with `migration_mode: review_required`.
- Existing `/api/rag/build` is still the only way to create RAG chunks.
- Existing `/api/customer-ops-agent/retrieve` is used only for retrieval verification.

Important P1-M11 boundary:

- P1-M11 does not add a new retrieval API.
- P1-M11 locks the existing CustomerOpsAgent-facing retrieval API as the DataHub-only contract.
- Unified RAG means approved `chat_logs`, `public_dataset`, `bad_case`, and `legacy_rag` chunks share the same local chunk and retrieval result shape.
- P1-M11 still uses local JSON plus keyword/mock retrieval.
- P1-M11 does not modify the CustomerOpsAgent repository.
- P1-M11 does not introduce embeddings, a vector database, database, ORM, real LLM, MCP, or P2/P3/P4 features.

Important P1-M12 boundary:

- P1-M12 does not add a new cleaning API.
- P1-M12 enhances `POST /api/cleaning/run/{batch_id}`, `GET /api/cleaning/jobs/{job_id}`, and `GET /api/sanitized/{batch_id}`.
- P1-M12 keeps all existing cleaning response fields and adds machine quality fields.
- P1-M12 advanced cleaning remains deterministic Python logic with standard library helpers only.
- P1-M12 does not implement manual cleaning UI, production data quality services, embeddings, vector database, database, ORM, real LLM, MCP, or P2/P3/P4 features.

Important P1-M15 boundary:

- P1-M15 is the final high-quality DataHub Phase 1 release.
- P1-M15 does not add a new API surface.
- P1-M15 verifies the existing API chain:
  - import
  - cleaning
  - manual cleaning
  - extraction
  - review
  - RAG build
  - CustomerOpsAgent retrieval
  - Bad Case feedback
  - Bad Case to pending-review draft
  - legacy RAG import
- P1-M15 keeps storage as local JSON and retrieval as local keyword/mock retrieval.
- P1-M15 does not introduce embeddings, a vector database, database, ORM, real LLM, production auth, MCP, or P2/P3/P4 features.

## 0A. Canonical State Names

Use these canonical state names:

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
- `approved` means a human approved the candidate. It does not mean RAG chunks or production indexing exist.
- `rag_chunked` means M6 local RAG chunks exist.
- `indexed` is reserved for future real vector store or production retrieval index status.
- Current M6/M6.5 reaches `rag_chunked`, not production `indexed`.
- `knowledge candidate` is used for M4-M5 records.
- `approved candidate` is the M5 post-review state.
- A future `knowledge_item` or formal knowledge asset store must be planned separately.

## 1. Common Response Shapes

### 1.1 Success

```json
{
  "success": true,
  "data": {},
  "requestId": "req_..."
}
```

### 1.2 Error

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable safe message",
    "details": {}
  },
  "requestId": "req_..."
}
```

Error messages must not include raw private data, secrets, or internal stack traces.

## 2. Implemented APIs: M2 JSON Data Import

M2 implements only JSON customer service chat import. CSV, Excel, database-backed import, cleaning, desensitization, extraction, RAG, and CustomerOpsAgent integration are not implemented in M2.

Raw batch files are saved under `backend/storage/raw_batches/`. The storage directory is ignored by Git.

### 2.1 Import JSON Chat Records

`POST /api/sources/import-json`

Request:

```json
{
  "source_name": "sample_customer_chat",
  "conversations": [
    {
      "conversation_id": "conv_001",
      "messages": [
        {
          "message_id": "msg_001",
          "role": "customer",
          "content": "How long does shipping take to Germany?",
          "timestamp": "2026-07-03T10:00:00"
        },
        {
          "message_id": "msg_002",
          "role": "agent",
          "content": "Shipping to Germany usually takes 7-12 business days after dispatch.",
          "timestamp": "2026-07-03T10:01:00"
        }
      ]
    }
  ]
}
```

Response:

```json
{
  "success": true,
  "data": {
    "batch_id": "batch_abc123",
    "source_name": "sample_customer_chat",
    "message_count": 2,
    "conversation_count": 1,
    "created_at": "2026-07-03T10:01:00+00:00",
    "status": "raw_imported"
  },
  "requestId": "req_001"
}
```

Allowed input state:

- New external data only.

Possible errors:

- `VALIDATION_ERROR`: Required fields missing or invalid.
- `PAYLOAD_TOO_LARGE`: Content too large.

Security notes:

- Raw records are stored only in the local raw batch layer.
- This API must not create knowledge drafts or RAG entries.
- This API must not clean, deduplicate, desensitize, extract, index, or call LLM services.
- Logs must not print full raw content.

### 2.2 List Raw Source Batches

`GET /api/sources`

Response:

```json
{
  "success": true,
  "data": {
    "sources": [
      {
        "batch_id": "batch_abc123",
        "source_name": "sample_customer_chat",
        "message_count": 2,
        "conversation_count": 1,
        "created_at": "2026-07-03T10:01:00+00:00",
        "status": "raw_imported"
      }
    ]
  },
  "requestId": "req_002"
}
```

Returned data:

- Metadata only.
- Raw message content is not returned by this endpoint.

### 2.3 Get Raw Source Batch Metadata

`GET /api/sources/{batch_id}`

Response:

```json
{
  "success": true,
  "data": {
    "batch_id": "batch_abc123",
    "source_name": "sample_customer_chat",
    "message_count": 2,
    "conversation_count": 1,
    "created_at": "2026-07-03T10:01:00+00:00",
    "status": "raw_imported"
  },
  "requestId": "req_003"
}
```

Response fields:

- `batch_id`
- `source_name`
- `message_count`
- `conversation_count`
- `created_at`
- `status`

Possible errors:

- `BATCH_NOT_FOUND`: Raw batch metadata was not found.

M2 state rule:

- Imported batches only have `raw_imported` status.
- `raw_imported` data cannot be used for extraction, RAG, CustomerOpsAgent retrieval, or export.

## 2A. Planned Phase 1 Import APIs Not Implemented

The earlier generic import direction is reserved for later stages:

- CSV import.
- Manual text paste import.
- Upload-based import.
- Duplicate import detection.
- Database-backed batch storage.

These are not implemented in M2.

## 3. Implemented APIs: M3 Cleaning And Sanitization

M3 converts a raw batch into a separate sanitized batch.

Hard rules:

- Raw batch files are read-only during cleaning.
- Sanitized batches are saved under `backend/storage/sanitized_batches/`.
- Cleaning jobs are saved under `backend/storage/cleaning_jobs/`.
- M3 only creates `sanitized` data.
- M3 must not create `pending_review`, `approved`, `rag_chunked`, or `indexed` data.
- M3 must not create RAG, embedding, vector store, CustomerOpsAgent, or Bad Case workflows.

### 3.1 Run Cleaning And Sanitization

`POST /api/cleaning/run/{batch_id}`

Request:

No request body.

Response:

```json
{
  "success": true,
  "data": {
    "job_id": "clean_job_abc123",
    "source_batch_id": "batch_abc123",
    "sanitized_batch_id": "batch_abc123",
    "raw_message_count": 6,
    "sanitized_message_count": 5,
    "dropped_message_count": 1,
    "pii_detected_count": 3,
    "exact_duplicate_count": 1,
    "near_duplicate_count": 1,
    "low_quality_count": 2,
    "noise_count": 1,
    "review_recommended_count": 2,
    "drop_recommended_count": 1,
    "average_quality_score": 0.82,
    "status": "completed",
    "created_at": "2026-07-03T10:10:00+00:00",
    "completed_at": "2026-07-03T10:10:00+00:00"
  },
  "requestId": "req_002"
}
```

Allowed source states:

- `raw_imported`

Possible errors:

- `BATCH_NOT_FOUND`

Cleaning rules:

- Trim leading and trailing whitespace from `content`.
- Drop empty `content`.
- Standardize role into `customer`, `agent`, or `system`.
- Apply safe fallback values for missing fields.
- Count raw, sanitized, and dropped messages.
- P1-M12 also detects exact duplicates, near duplicates, low-quality text, possible noise, weak questions, and weak answers.
- P1-M12 adds message-level quality scores and suggested actions for later manual cleaning.

PII masking rules:

- Email -> `[EMAIL]`
- Phone or mobile number -> `[PHONE]`
- Order id -> `[ORDER_ID]`
- Tracking id -> `[TRACKING_ID]`
- Obvious address text -> `[ADDRESS]`
- Name-like text -> `[NAME]`
- Postal or ZIP code -> `[ZIP_CODE]`
- Payment-like long digit sequence -> `[PAYMENT_SENSITIVE]`

### 3.2 Get Cleaning Job Status

`GET /api/cleaning/jobs/{job_id}`

Response fields:

- `job_id`
- `source_batch_id`
- `sanitized_batch_id`
- `raw_message_count`
- `sanitized_message_count`
- `dropped_message_count`
- `pii_detected_count`
- `exact_duplicate_count`
- `near_duplicate_count`
- `low_quality_count`
- `noise_count`
- `review_recommended_count`
- `drop_recommended_count`
- `average_quality_score`
- `status`
- `created_at`
- `completed_at`

Possible errors:

- `JOB_NOT_FOUND`

### 3.3 Get Sanitized Batch

`GET /api/sanitized/{batch_id}`

Response:

```json
{
  "success": true,
  "data": {
    "batch_id": "batch_abc123",
    "source_batch_id": "batch_abc123",
    "status": "sanitized",
    "raw_message_count": 6,
    "sanitized_message_count": 5,
    "dropped_message_count": 1,
    "pii_detected_count": 3,
    "exact_duplicate_count": 1,
    "near_duplicate_count": 1,
    "low_quality_count": 2,
    "noise_count": 1,
    "review_recommended_count": 2,
    "drop_recommended_count": 1,
    "average_quality_score": 0.82,
    "created_at": "2026-07-03T10:10:00+00:00",
    "messages": [
      {
        "source_batch_id": "batch_abc123",
        "conversation_id": "conv_001",
        "message_id": "msg_003",
        "source_message_id": "msg_003",
        "role": "customer",
        "content": "Please contact me at [EMAIL] or [PHONE]. My [ORDER_ID].",
        "pii_detected": true,
        "pii_types": ["EMAIL", "PHONE", "ORDER_ID"],
        "cleaning_notes": ["pii_masked"],
        "cleaning_issues": [],
        "risk_flags": ["contains_personal_data", "contains_business_identifier"],
        "quality_score": 0.95,
        "quality_level": "high",
        "suggested_action": "keep"
      }
    ]
  },
  "requestId": "req_003"
}
```

Sanitized message fields:

- `source_batch_id`
- `conversation_id`
- `message_id`
- `source_message_id`
- `role`
- `content`
- `pii_detected`
- `pii_types`
- `cleaning_notes`
- `cleaning_issues`
- `risk_flags`
- `quality_score`
- `quality_level`
- `suggested_action`

P1-M12 backward compatibility:

- Historical sanitized messages without the new fields should be treated as:
  - `cleaning_issues: []`
  - `risk_flags: []`
  - `quality_score: 1.0`
  - `quality_level: high`
  - `suggested_action: keep`

Possible errors:

- `SANITIZED_BATCH_NOT_FOUND`

State rule:

- Sanitized data is safer processed data.
- Sanitized data is not knowledge.
- Sanitized data is not approved.
- Sanitized data is not `rag_chunked` or `indexed`.
- Sanitized data cannot be retrieved by CustomerOpsAgent.

## 4. Implemented APIs: M4 Knowledge Candidate Extraction

M4 extracts reviewable knowledge candidates from sanitized batches only.

Hard rules:

- Extraction must read only from `backend/storage/sanitized_batches/`.
- Extraction must not read raw batch files.
- Candidates are saved under `backend/storage/knowledge_candidates/`.
- Extraction jobs are saved under `backend/storage/extraction_jobs/`.
- Every candidate must be `pending_review`.
- Candidates are not approved knowledge.
- Candidates must not enter RAG.
- M4 must not create embeddings, vector records, CustomerOpsAgent retrieval records, or Bad Case records.

### 4.1 Run Knowledge Candidate Extraction

`POST /api/extraction/run/{batch_id}`

Request:

No request body.

Response:

```json
{
  "success": true,
  "data": {
    "job_id": "extract_job_abc123",
    "source_batch_id": "batch_abc123",
    "candidate_count": 2,
    "status": "completed",
    "extraction_method": "rule_based_mock",
    "created_at": "2026-07-03T10:20:00+00:00",
    "completed_at": "2026-07-03T10:20:00+00:00"
  },
  "requestId": "req_004"
}
```

Allowed source states:

- `sanitized`

Possible errors:

- `SANITIZED_BATCH_NOT_FOUND`: Sanitized batch does not exist. Run cleaning first.

Extraction method:

- `rule_based_mock`
- The first version identifies simple customer -> agent question-answer pairs.
- No real LLM is called.

### 4.2 Get Extraction Job Status

`GET /api/extraction/jobs/{job_id}`

Response fields:

- `job_id`
- `source_batch_id`
- `candidate_count`
- `status`
- `extraction_method`
- `created_at`
- `completed_at`

Possible errors:

- `EXTRACTION_JOB_NOT_FOUND`

### 4.3 List Knowledge Candidates

`GET /api/knowledge/candidates`

Response:

```json
{
  "success": true,
  "data": {
    "candidates": [
      {
        "candidate_id": "kc_abc123",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"],
        "knowledge_type": "faq",
        "question": "How long does shipping take to Germany?",
        "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
        "intent": "shipping",
        "tags": ["shipping", "delivery"],
        "risk_level": "low",
        "review_status": "pending_review",
        "quality_score": 0.85,
        "extraction_method": "rule_based_mock",
        "created_at": "2026-07-03T10:20:00+00:00"
      }
    ]
  },
  "requestId": "req_005"
}
```

Candidate fields:

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

Allowed `review_status` in M4:

- `pending_review`

### 4.4 Get Knowledge Candidate Detail

`GET /api/knowledge/candidates/{candidate_id}`

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_abc123",
    "source_batch_id": "batch_abc123",
    "source_conversation_id": "conv_001",
    "source_message_ids": ["msg_001", "msg_002"],
    "knowledge_type": "faq",
    "question": "How long does shipping take to Germany?",
    "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
    "intent": "shipping",
    "tags": ["shipping", "delivery"],
    "risk_level": "low",
    "review_status": "pending_review",
    "quality_score": 0.85,
    "extraction_method": "rule_based_mock",
    "created_at": "2026-07-03T10:20:00+00:00"
  },
  "requestId": "req_006"
}
```

Possible errors:

- `KNOWLEDGE_CANDIDATE_NOT_FOUND`

State rule:

- M4 produces only `pending_review` candidates.
- M4 does not produce `approved` knowledge.
- M4 does not produce `rag_chunked` or production `indexed` knowledge.

## 4A. Historical Note: Knowledge Review Is Implemented In M5

M4 itself does not implement review. M5 implements human review, editing, approval, and rejection.

## 5. Implemented APIs: M5 Human Review

M5 allows humans to edit and review existing knowledge candidates.

Hard rules:

- Review APIs only operate on existing files under `backend/storage/knowledge_candidates/`.
- Review APIs must not read raw batches directly.
- Review APIs must not read sanitized batches directly to create approvals.
- Approved candidates are human-reviewed candidates only.
- Approved candidates are not RAG chunks.
- Approved candidates are not `rag_chunked` or production `indexed`.
- Rejected and needs-revision candidates must not enter future retrieval.
- M5 must not create embeddings, vector records, CustomerOpsAgent retrieval records, or Bad Case records.

### 5.1 List Pending Review Candidates

`GET /api/review/pending`

Response:

```json
{
  "success": true,
  "data": {
    "candidates": [
      {
        "candidate_id": "kc_abc123",
        "review_status": "pending_review",
        "question": "How long does shipping take to Germany?",
        "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"]
      }
    ]
  },
  "requestId": "req_007"
}
```

Returned states:

- `pending_review`
- `needs_revision`

### 5.2 Edit Knowledge Candidate

`PATCH /api/knowledge/candidates/{candidate_id}`

Request:

```json
{
  "question": "How long does shipping take to Germany?",
  "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
  "intent": "shipping",
  "tags": ["shipping", "delivery"],
  "risk_level": "low",
  "quality_score": 0.82
}
```

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_abc123",
    "review_status": "pending_review",
    "updated_at": "2026-07-03T11:00:00+00:00"
  },
  "requestId": "req_008"
}
```

Editable fields:

- `question`
- `answer`
- `intent`
- `tags`
- `risk_level`
- `quality_score`

Possible errors:

- `KNOWLEDGE_CANDIDATE_NOT_FOUND`

### 5.3 Approve Candidate

`POST /api/review/{candidate_id}/approve`

Request:

```json
{
  "reviewer": "local_reviewer",
  "review_note": "Approved after wording check."
}
```

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_abc123",
    "review_status": "approved",
    "reviewer": "local_reviewer",
    "review_note": "Approved after wording check.",
    "reviewed_at": "2026-07-03T11:00:00+00:00",
    "updated_at": "2026-07-03T11:00:00+00:00"
  },
  "requestId": "req_009"
}
```

Hard rule:

- Approved candidates retain `source_batch_id`, `source_conversation_id`, `source_message_ids`, and `extraction_method`.
- Approved candidates are not `rag_chunked` until M6 build runs. They are not production `indexed` and are not available to CustomerOpsAgent.

### 5.4 Reject Candidate

`POST /api/review/{candidate_id}/reject`

Request:

```json
{
  "reviewer": "local_reviewer",
  "review_note": "Not useful enough."
}
```

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_abc123",
    "review_status": "rejected"
  },
  "requestId": "req_010"
}
```

Rejected candidates must not enter future retrieval or RAG.

### 5.5 Mark Candidate As Needs Revision

`POST /api/review/{candidate_id}/needs-revision`

Request:

```json
{
  "reviewer": "local_reviewer",
  "review_note": "Needs a clearer answer."
}
```

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_abc123",
    "review_status": "needs_revision"
  },
  "requestId": "req_011"
}
```

Needs-revision candidates must be edited before later approval or rejection.

## 5A. Implemented APIs: M6/M6.5 Local RAG Build And Search

M6 builds local JSON RAG chunks from approved knowledge candidates only. M6.5 hardens build idempotency, search validation, and debug traceability.

Hard rules:

- RAG build reads only from `backend/storage/knowledge_candidates/`.
- Only candidates with `review_status: approved` can become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- M6 writes chunks under `backend/storage/rag_chunks/`.
- M6 uses local JSON plus mock keyword retrieval only.
- M6 does not use embeddings, a vector database, database, ORM, real LLM, or RAG framework.
- M6 does not expose CustomerOpsAgent-specific APIs.
- M6.5 build is idempotent: repeating build for the same unchanged approved candidate must not create duplicate chunks.
- M6.5 search returns `matched_terms` for local debugging.

### 5A.1 Build Local RAG Chunks

`POST /api/rag/build`

Request:

No request body.

Response:

```json
{
  "success": true,
  "data": {
    "built_count": 1,
    "updated_count": 0,
    "skipped_count": 2,
    "skipped_reasons": {
      "unchanged": 0,
      "review_status_pending_review": 1,
      "review_status_rejected": 1
    },
    "chunk_count": 1,
    "status": "completed",
    "build_method": "local_json_mock_retrieval",
    "created_at": "2026-07-03T12:00:00+00:00"
  },
  "requestId": "req_012"
}
```

Response fields:

- `built_count`: new chunks created from approved candidates.
- `updated_count`: existing chunks updated because candidate-derived chunk content changed.
- `skipped_count`: non-approved candidates plus unchanged approved chunks that were skipped.
- `skipped_reasons`: reason counts such as `unchanged`, `review_status_pending_review`, `review_status_needs_revision`, or `review_status_rejected`.
- `chunk_count`: total chunks after the build.
- `status`: `completed`.

Allowed source state:

- `approved`

Forbidden source states:

- `pending_review`
- `needs_revision`
- `rejected`
- raw batches
- sanitized batches

### 5A.2 List RAG Chunks

`GET /api/rag/chunks`

Response:

```json
{
  "success": true,
  "data": {
    "chunks": [
      {
        "chunk_id": "chunk_kc_abc123",
        "candidate_id": "kc_abc123",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"],
        "knowledge_type": "faq",
        "intent": "shipping",
        "tags": ["shipping", "delivery"],
        "risk_level": "low",
        "quality_score": 0.82,
        "review_status": "approved",
        "chunk_text": "Question: ...\nAnswer: ...\nIntent: shipping\nTags: shipping, delivery",
        "created_at": "2026-07-03T12:00:00+00:00",
        "build_method": "local_json_mock_retrieval"
      }
    ]
  },
  "requestId": "req_013"
}
```

### 5A.3 Get RAG Chunk

`GET /api/rag/chunks/{chunk_id}`

Possible errors:

- `RAG_CHUNK_NOT_FOUND`

### 5A.4 Search Local RAG Chunks

`POST /api/rag/search`

Request:

```json
{
  "query": "shipping Germany",
  "top_k": 5
}
```

Validation:

- `query` must be a non-empty string after trimming.
- `query` maximum length is 500 characters.
- `top_k` defaults to 5.
- `top_k` minimum is 1.
- `top_k` maximum is 10.
- Invalid input returns a safe structured error and does not include private content.

Response:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "score": 0.75,
        "matched_terms": ["germany", "shipping"],
        "chunk_id": "chunk_kc_abc123",
        "candidate_id": "kc_abc123",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"],
        "knowledge_type": "faq",
        "intent": "shipping",
        "tags": ["shipping", "delivery"],
        "risk_level": "low",
        "quality_score": 0.82,
        "review_status": "approved",
        "chunk_text": "Question: ...\nAnswer: ...",
        "build_method": "local_json_mock_retrieval"
      }
    ]
  },
  "requestId": "req_014"
}
```

M6/M6.5 search is a DataHub internal test endpoint. CustomerOpsAgent must use the M7 `/api/customer-ops-agent/retrieve` endpoint instead.

## 6. Planned Phase 1 APIs: Knowledge Base Management (Not Implemented)

This section describes planned Phase 1 knowledge management capabilities. These APIs are not implemented through M7.

### 6.1 List Approved Knowledge

`GET /api/knowledge?status=approved&type=faq`

Response fields:

- `knowledgeId`
- `knowledgeType`
- `title`
- `question`
- `answer`
- `tags`
- `status`
- `version`
- `sourceRecordIds`
- `approvedAt`
- `indexedStatus`

Allowed states:

- Admin API may list approved knowledge.
- CustomerOpsAgent must use retrieval APIs, not this management API.

### 6.2 Archive Knowledge

`POST /api/knowledge/{knowledgeId}/archive`

Request:

```json
{
  "reviewerId": "user_001",
  "reason": "Outdated policy"
}
```

Allowed states:

- `approved`
- `indexed`

Archived knowledge must be removed from future retrieval results.

## 7. Planned/Future Phase 1 APIs: Production RAG Index Jobs (Not Implemented)

This section is for future production indexing. It must not be confused with M6 `POST /api/rag/build`, which only creates local JSON RAG chunks.

### 7.1 Start RAG Index Job

`POST /api/rag/index-jobs`

Request:

```json
{
  "knowledgeIds": ["know_001", "know_002"],
  "mode": "incremental | rebuild"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "jobId": "rag_job_001",
    "status": "queued",
    "eligibleKnowledgeCount": 2
  },
  "requestId": "req_006"
}
```

Allowed knowledge states:

- `approved`
- `indexed` when rebuilding

Possible errors:

- `KNOWLEDGE_NOT_FOUND`
- `INVALID_STATE`: Knowledge is not approved.
- `VECTOR_STORE_UNAVAILABLE`

Hard rule:

- Pending, rejected, raw, cleaned, or sanitized records cannot be indexed.

### 7.2 Get RAG Index Job

`GET /api/rag/index-jobs/{jobId}`

Response fields:

- `jobId`
- `status`
- `indexedCount`
- `failedCount`
- `errorSummary`

## 8. Future RAG Retrieval Enhancements

M6 implements local internal search in section 5A.4 using:

- `query`
- `top_k`
- local JSON chunks
- mock keyword scoring

Future production retrieval may add:

- filters
- version metadata
- archive handling
- access control
- real vector scoring
- CustomerOpsAgent-specific response guarantees

Hard rule:

- Retrieval must only return approved retrieval-ready knowledge. At the current local stage, retrieval-ready means approved `rag_chunked` records; future production retrieval may require `indexed`.

## 9. CustomerOpsAgent Integration

### 9.1 Implemented API: CustomerOpsAgent Restricted Retrieval (M7/M7.5)

`POST /api/customer-ops-agent/retrieve`

Required header:

```text
X-DataHub-Client: CustomerOpsAgent
```

Auth placeholder:

- The header is required for local development.
- This is not production authentication.
- Missing or invalid header returns `UNAUTHORIZED_CLIENT`.
- No API key, real token, or `.env` secret is introduced in M7.5.

Request:

```json
{
  "query": "How long does shipping take to Germany?",
  "top_k": 5,
  "filters": {
    "intent": "shipping",
    "tags": ["shipping"],
    "risk_level": "low"
  },
  "conversation_id": "optional_conv_id",
  "agent_session_id": "optional_session_id"
}
```

Validation:

- `query` is required.
- `query` must be a string.
- `query` must be non-empty after trimming.
- `query` maximum length is 500 characters.
- `top_k` defaults to 5.
- `top_k` must be between 1 and 10.
- `filters`, `conversation_id`, and `agent_session_id` are optional.
- Invalid input returns safe structured errors and does not expose private content.

Response:

```json
{
  "success": true,
  "data": {
    "retrieval_id": "retrieval_abc123",
    "query": "How long does shipping take to Germany?",
    "top_k": 5,
    "retrieval_mode": "customerops_local_mock_retrieval",
    "results": [
      {
        "score": 0.82,
        "matched_terms": ["shipping"],
        "chunk_id": "chunk_kc_abc123",
        "candidate_id": "kc_abc123",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"],
        "knowledge_type": "faq",
        "intent": "shipping",
        "tags": ["shipping", "delivery"],
        "risk_level": "low",
        "quality_score": 0.86,
        "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
        "chunk_text": "Question: ...\nAnswer: ...",
        "review_status": "approved",
        "build_method": "local_json_mock_retrieval"
      }
    ],
    "created_at": "2026-07-03T12:30:00+00:00"
  },
  "requestId": "req_008"
}
```

Allowed data states:

- `approved` local `rag_chunked` records only.
- The endpoint reads only `backend/storage/rag_chunks/`.

Forbidden:

- Returning raw records.
- Returning sanitized records directly.
- Returning knowledge candidates directly.
- Returning `pending_review`, `needs_revision`, or `rejected` records.
- Allowing CustomerOpsAgent to change knowledge.
- Creating Bad Cases.
- Calling a real vector database, embedding model, database, ORM, or real LLM.

Possible errors:

- `UNAUTHORIZED_CLIENT`
- `INVALID_QUERY`
- `QUERY_TOO_LONG`
- `INVALID_TOP_K`

Error shape:

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED_CLIENT",
    "message": "CustomerOpsAgent client header is required.",
    "details": {}
  },
  "requestId": "req_abc123"
}
```

### 9.2 Implemented API: CustomerOpsAgent Retrieval Trace Lookup (M7/M7.5)

`GET /api/customer-ops-agent/retrievals/{retrieval_id}`

Required header:

```text
X-DataHub-Client: CustomerOpsAgent
```

Response:

```json
{
  "success": true,
  "data": {
    "retrieval_id": "retrieval_abc123",
    "query": "How long does shipping take to Germany?",
    "top_k": 5,
    "filters": {
      "intent": "shipping",
      "tags": ["shipping"]
    },
    "result_count": 1,
    "result_chunk_ids": ["chunk_kc_abc123"],
    "conversation_id": "optional_conv_id",
    "agent_session_id": "optional_session_id",
    "created_at": "2026-07-03T12:30:00+00:00",
    "retrieval_mode": "customerops_local_mock_retrieval"
  },
  "requestId": "req_009"
}
```

Storage:

- Retrieval traces are saved under `backend/storage/retrieval_logs/`.
- The storage directory is ignored by Git.
- Traces are for later M8 Bad Case linkage.
- M7 traces store retrieval metadata and result chunk ids, not full raw records.

Possible errors:

- `UNAUTHORIZED_CLIENT`
- `RETRIEVAL_NOT_FOUND`

PowerShell examples:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrievals/{retrieval_id} `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"}
```

### 9.3 Implemented API: CustomerOpsAgent Bad Case Feedback (M8)

`POST /api/customer-ops-agent/bad-cases`

Required header:

```text
X-DataHub-Client: CustomerOpsAgent
```

Request:

```json
{
  "retrieval_id": "retrieval_abc123",
  "user_query": "Where is my order?",
  "agent_answer": "Your package should arrive soon.",
  "issue_type": "wrong_answer",
  "expected_answer": "The answer should mention tracking status or escalation.",
  "severity": "medium",
  "conversation_id": "conv_001",
  "agent_session_id": "session_001",
  "metadata": {
    "channel": "web_chat",
    "language": "en"
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "bad_case_id": "badcase_abc123",
    "retrieval_id": "retrieval_abc123",
    "issue_type": "wrong_answer",
    "severity": "medium",
    "status": "open",
    "linked_chunk_ids": ["chunk_kc_abc123"],
    "retrieval_result_count": 1,
    "created_at": "2026-07-03T12:00:00+00:00",
    "updated_at": "2026-07-03T12:00:00+00:00"
  },
  "requestId": "req_009"
}
```

Validation:

- `retrieval_id` is required and must exist in `backend/storage/retrieval_logs/`.
- `user_query` is required, trimmed, non-empty, and at most 500 characters.
- `agent_answer` is required, trimmed, non-empty, and at most 2000 characters.
- `issue_type` must be one of `wrong_answer`, `missing_knowledge`, `unsafe_answer`, `bad_tone`, `retrieval_miss`, or `other`.
- `expected_answer` is optional and at most 2000 characters.
- `severity` defaults to `medium` and must be `low`, `medium`, or `high`.

Possible errors:

- `UNAUTHORIZED_CLIENT`
- `INVALID_RETRIEVAL_REFERENCE`
- `INVALID_USER_QUERY`
- `USER_QUERY_TOO_LONG`
- `INVALID_AGENT_ANSWER`
- `AGENT_ANSWER_TOO_LONG`
- `EXPECTED_ANSWER_TOO_LONG`
- `INVALID_ISSUE_TYPE`
- `INVALID_SEVERITY`

Hard rule:

- Bad Cases cannot directly update candidates, approved knowledge, RAG chunks, or any retrieval index.

## 10. Implemented APIs: Bad Case Management (M8)

### 10.1 List Bad Cases

`GET /api/bad-cases?status=open&issue_type=missing_knowledge&severity=medium`

Optional filters:

- `status`
- `issue_type`
- `severity`

Response:

```json
{
  "success": true,
  "data": {
    "bad_cases": [
      {
        "bad_case_id": "badcase_abc123",
        "retrieval_id": "retrieval_abc123",
        "issue_type": "wrong_answer",
        "severity": "medium",
        "status": "open",
        "linked_chunk_ids": ["chunk_kc_abc123"],
        "retrieval_result_count": 1,
        "created_at": "2026-07-03T12:00:00+00:00",
        "updated_at": "2026-07-03T12:00:00+00:00"
      }
    ]
  },
  "requestId": "req_010"
}
```

### 10.2 Get Bad Case Detail

`GET /api/bad-cases/{bad_case_id}`

Possible errors:

- `BAD_CASE_NOT_FOUND`

### 10.3 Update Bad Case Handling State

`PATCH /api/bad-cases/{bad_case_id}`

Request:

```json
{
  "status": "triaged",
  "review_note": "Confirmed retrieval miss.",
  "resolution_type": "retrieval_tuning",
  "linked_candidate_id": "kc_manual_reference_only"
}
```

Editable fields:

- `status`: one of `open`, `triaged`, `resolved`, `ignored`.
- `review_note`: human handling note.
- `resolution_type`: one of `create_new_knowledge`, `update_existing_knowledge`, `retrieval_tuning`, `ignore`, or `other`.
- `linked_candidate_id`: optional manual reference only.

Hard rules:

- `linked_candidate_id` does not create or update a candidate.
- `resolution_type` does not trigger knowledge flow.
- PATCH does not modify RAG chunks.
- PATCH does not rebuild or re-index RAG.

## 10A. Implemented API: Bad Case Resolution To Draft (M8.5)

### 10A.1 Create Pending-Review Draft From Bad Case

`POST /api/bad-cases/{bad_case_id}/create-draft`

Request:

```json
{
  "question": "Where is my order?",
  "answer": "Please provide your order number or tracking number. If tracking is unavailable, we will escalate this to a human agent.",
  "intent": "order_status",
  "tags": ["order", "tracking", "handoff"],
  "risk_level": "medium",
  "quality_score": 0.7,
  "knowledge_type": "faq",
  "reviewer": "local_reviewer",
  "review_note": "Created from Bad Case after human correction."
}
```

Response:

```json
{
  "success": true,
  "data": {
    "candidate_id": "kc_badcase_abc123",
    "source_type": "bad_case",
    "source_bad_case_id": "badcase_abc123",
    "source_retrieval_id": "retrieval_abc123",
    "source_chunk_ids": ["chunk_kc_abc123"],
    "source_batch_id": null,
    "source_conversation_id": "conv_001",
    "source_message_ids": [],
    "knowledge_type": "faq",
    "question": "Where is my order?",
    "answer": "Please provide your order number or tracking number...",
    "intent": "order_status",
    "tags": ["order", "tracking", "handoff"],
    "risk_level": "medium",
    "review_status": "pending_review",
    "quality_score": 0.7,
    "extraction_method": "bad_case_resolution"
  },
  "requestId": "req_010"
}
```

Validation:

- `bad_case_id` must exist.
- Bad Cases with `status: ignored` cannot create drafts.
- `question` is required, trimmed, non-empty, and at most 500 characters.
- `answer` is required, trimmed, non-empty, and at most 2000 characters.
- `intent` defaults to `general`.
- `tags` defaults to an empty array.
- `risk_level` defaults to `medium`.
- `quality_score` defaults to `0.7` and must be 0-1.
- `knowledge_type` defaults to `faq`.

Possible errors:

- `BAD_CASE_NOT_FOUND`
- `BAD_CASE_IGNORED`
- `INVALID_DRAFT_PAYLOAD`

Hard rule:

- Created candidates must use `review_status: pending_review`.
- Created candidates must pass the normal M5 review flow before RAG build.
- This API must not modify existing candidates.
- This API must not modify RAG chunks.
- This API must not rebuild or re-index RAG.

## 10B. Implemented APIs: Legacy RAG Migration (P1-M10)

P1-M10 imports a legacy RAG export shape into DataHub's existing candidate layer.

Storage:

- Import metadata is saved under `backend/storage/legacy_rag_imports/`.
- Generated candidates are saved under `backend/storage/knowledge_candidates/`.
- Both directories are ignored by Git through `backend/storage/`.

Hard rules:

- P1-M10 does not read the CustomerOpsAgent repository.
- P1-M10 does not modify the CustomerOpsAgent repository.
- P1-M10 does not switch CustomerOpsAgent to DataHub-only retrieval.
- P1-M10 does not introduce a vector database, embedding model, database, ORM, or real LLM.
- Repeated import of the same `source_name + legacy_id` does not create duplicate candidates.

### 10B.1 Import Legacy RAG Export

`POST /api/legacy-rag/import`

Request:

```json
{
  "source_name": "customerops_legacy_rag_sample",
  "source_type": "legacy_rag",
  "trusted_import": true,
  "exported_at": "2026-07-03T10:00:00+00:00",
  "items": [
    {
      "legacy_id": "legacy_shipping_001",
      "question": "How long does shipping take to Germany?",
      "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
      "intent": "shipping",
      "tags": ["shipping", "delivery"],
      "risk_level": "low",
      "quality_score": 0.85,
      "knowledge_type": "faq",
      "source_note": "Migrated from CustomerOpsAgent legacy RAG."
    }
  ]
}
```

Response:

```json
{
  "success": true,
  "data": {
    "import_id": "legacy_import_abc123",
    "source_name": "customerops_legacy_rag_sample",
    "source_type": "legacy_rag",
    "trusted_import": true,
    "migration_mode": "trusted_import",
    "item_count": 1,
    "created_candidate_count": 1,
    "updated_count": 0,
    "approved_count": 1,
    "pending_review_count": 0,
    "skipped_count": 0,
    "skipped_reasons": {},
    "created_at": "2026-07-03T10:00:00+00:00",
    "candidate_ids": ["kc_legacy_abc123"]
  },
  "requestId": "req_abc123"
}
```

Generated candidate fields:

- `candidate_id`: stable `kc_legacy_*` id derived from `source_name + legacy_id`.
- `source_type: legacy_rag`.
- `source_legacy_id`.
- `source_import_id`.
- `source_batch_id: null`.
- `source_conversation_id: null`.
- `source_message_ids: []`.
- `review_status: approved` when `trusted_import=true`.
- `review_status: pending_review` when `trusted_import=false`.
- `extraction_method: legacy_rag_migration`.
- `migration_mode: trusted_import | review_required`.
- `source_note`.

Idempotency strategy:

- The same `source_name + legacy_id` maps to the same candidate id.
- If the candidate does not exist, DataHub creates it.
- If the candidate exists and content is unchanged, DataHub skips it and increments `skipped_count`.
- If the candidate exists and content changed, DataHub updates the same candidate and increments `updated_count`.
- DataHub never creates duplicate candidates for the same legacy item.

### 10B.2 List Legacy RAG Imports

`GET /api/legacy-rag/imports`

Response:

```json
{
  "success": true,
  "data": {
    "imports": [
      {
        "import_id": "legacy_import_abc123",
        "source_name": "customerops_legacy_rag_sample",
        "source_type": "legacy_rag",
        "trusted_import": true,
        "item_count": 3,
        "candidate_ids": ["kc_legacy_abc123"]
      }
    ]
  },
  "requestId": "req_abc123"
}
```

### 10B.3 Get Legacy RAG Import Detail

`GET /api/legacy-rag/imports/{import_id}`

Possible errors:

- `LEGACY_RAG_IMPORT_NOT_FOUND`

### 10B.4 RAG Build And Retrieval Verification

P1-M10 does not add new RAG APIs.

Use existing APIs:

```text
POST /api/rag/build
POST /api/customer-ops-agent/retrieve
```

Expected behavior:

- Approved legacy candidates can become local RAG chunks.
- Review-required legacy candidates remain `pending_review` and cannot become RAG chunks.
- Retrieval results can include `source_type: legacy_rag`, `source_legacy_id`, `source_import_id`, `candidate_id`, and `chunk_id`.

## 11. Future Roadmap APIs: Phase 2-4 (Not Implemented)

These API groups belong to the formal roadmap, but they are not implemented through M7 and must not be started without an explicit future phase.

### 11.1 Phase 2 Multimodal Material APIs

Potential future APIs:

- Material asset import.
- OCR and Caption job management.
- Tag and SKU binding management.
- Multimodal review queue.
- Multimodal asset retrieval.

Status:

- Not implemented.
- Not part of M6.5 or M7 unless explicitly approved later.

### 11.2 Phase 3 Dataset Export APIs

Potential future APIs:

- Export sales training materials.
- Export FAQ handbook.
- Export SOP and script handbook.
- Export typical cases and quiz questions.
- Export SFT dataset.
- Export Preference dataset.

Status:

- Not implemented.
- No real fine-tuning is performed by DataHub.

### 11.3 Phase 4 MCP Tool APIs

Potential future tools:

- `search_customer_knowledge`
- `search_multimodal_assets`
- `submit_bad_case`
- `export_training_dataset`
- `export_finetune_dataset`

Status:

- Not implemented.
- Future MCP tool contracts must enforce review and authorization boundaries.
