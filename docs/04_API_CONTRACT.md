# DataHub API Contract Draft

This document defines the phase-one API contract and roadmap. Each section is marked as implemented, planned, or future roadmap.

Base assumptions:

- React admin UI calls management APIs.
- CustomerOpsAgent calls restricted retrieval and Bad Case APIs.
- All APIs return structured errors.
- Raw and unapproved data must never be retrievable by CustomerOpsAgent.

## 0. API Implementation Status

This document separates APIs by implementation status.

Implemented APIs: M2-M6

- M2 JSON import.
- M3 cleaning and sanitization.
- M4 knowledge candidate extraction.
- M5 human review.
- M6 local RAG chunk build and local mock search.

Planned Phase 1 APIs: M7-M8

- CustomerOpsAgent production retrieval.
- CustomerOpsAgent Bad Case feedback.
- Bad Case management and resolution.
- Any production retrieval endpoint that exposes data to CustomerOpsAgent.

Future Roadmap APIs: Phase 2-4

- Multimodal material ingestion and understanding.
- Sales training dataset export.
- Fine-tuning dataset export.
- MCP tool APIs for the Agent cluster.

Important M6 boundary:

- `POST /api/rag/build` and `POST /api/rag/search` are implemented as DataHub internal local RAG test APIs.
- Current `/api/rag/search` is not the official CustomerOpsAgent retrieval API.
- Current M6 uses local JSON plus keyword/mock retrieval.
- Current M6 does not use embeddings, a real vector database, database, ORM, or production RAG index.

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
- Current M6 reaches `rag_chunked`, not production `indexed`.
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

PII masking rules:

- Email -> `[EMAIL]`
- Phone or mobile number -> `[PHONE]`
- Order id -> `[ORDER_ID]`
- Tracking id -> `[TRACKING_ID]`
- Obvious address text -> `[ADDRESS]`

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
        "cleaning_notes": ["pii_masked"]
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

## 5A. Implemented APIs: M6 Local RAG Build And Search

M6 builds local JSON RAG chunks from approved knowledge candidates only.

Hard rules:

- RAG build reads only from `backend/storage/knowledge_candidates/`.
- Only candidates with `review_status: approved` can become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- M6 writes chunks under `backend/storage/rag_chunks/`.
- M6 uses local JSON plus mock keyword retrieval only.
- M6 does not use embeddings, a vector database, database, ORM, real LLM, or RAG framework.
- M6 does not expose CustomerOpsAgent-specific APIs.

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
    "skipped_count": 2,
    "skipped_reasons": {
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
        "chunk_id": "chunk_abc123",
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

Response:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "score": 0.75,
        "chunk_id": "chunk_abc123",
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

M6 search is a DataHub internal test endpoint. It does not mean CustomerOpsAgent integration is complete.

## 6. Planned Phase 1 APIs: Knowledge Base Management (Not Implemented)

This section describes planned Phase 1 knowledge management capabilities. These APIs are not implemented through M6.

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

- Retrieval must only return approved and indexed knowledge.

## 9. Planned Phase 1 APIs: CustomerOpsAgent Integration (M7-M8, Not Implemented)

### 9.1 CustomerOpsAgent Knowledge Retrieval

`POST /api/customer-ops-agent/retrieve`

Request:

```json
{
  "conversationId": "customer_conv_001",
  "userQuery": "Can I return this product after 7 days?",
  "topK": 5,
  "context": {
    "channel": "web_chat",
    "locale": "zh-CN"
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "retrievalId": "retrieval_001",
    "results": [
      {
        "knowledgeId": "know_001",
        "knowledgeType": "business_rule",
        "title": "Return policy",
        "content": "Approved retrieval content",
        "score": 0.91,
        "version": 2,
        "sourceSummary": "Approved from customer service chat batch batch_001"
      }
    ]
  },
  "requestId": "req_008"
}
```

Allowed data states:

- `indexed` approved knowledge only.

Forbidden:

- Returning raw records.
- Returning review-pending drafts.
- Returning rejected or archived knowledge.
- Allowing CustomerOpsAgent to change knowledge.

Possible errors:

- `QUERY_TOO_LONG`
- `AGENT_NOT_AUTHORIZED`
- `NO_APPROVED_KNOWLEDGE_AVAILABLE`
- `RAG_INDEX_UNAVAILABLE`

### 9.2 CustomerOpsAgent Bad Case Feedback

`POST /api/customer-ops-agent/bad-cases`

Request:

```json
{
  "conversationId": "customer_conv_001",
  "retrievalId": "retrieval_001",
  "userQuery": "Can I return this product after 7 days?",
  "agentAnswer": "Incorrect or low-quality answer",
  "issueType": "wrong_answer | missing_knowledge | unsafe_answer | outdated_knowledge | other",
  "expectedAnswer": "Optional corrected answer",
  "reportedBy": "CustomerOpsAgent",
  "metadata": {}
}
```

Response:

```json
{
  "success": true,
  "data": {
    "badCaseId": "badcase_001",
    "status": "open",
    "createdAt": "2026-07-03T12:00:00+08:00"
  },
  "requestId": "req_009"
}
```

Possible errors:

- `VALIDATION_ERROR`
- `AGENT_NOT_AUTHORIZED`
- `PAYLOAD_TOO_LARGE`
- `INVALID_RETRIEVAL_REFERENCE`

Hard rule:

- Bad Cases cannot directly update approved knowledge or the RAG index.

## 10. Planned Phase 1 APIs: Bad Case Management (M8, Not Implemented)

### 10.1 List Bad Cases

`GET /api/bad-cases?status=open&issueType=missing_knowledge`

Response fields:

- `badCaseId`
- `status`
- `issueType`
- `userQuery`
- `agentAnswer`
- `expectedAnswer`
- `retrievalId`
- `createdAt`

### 10.2 Resolve Bad Case

`POST /api/bad-cases/{badCaseId}/resolution`

Request:

```json
{
  "resolutionType": "create_knowledge_draft | update_existing_knowledge | mark_not_actionable",
  "reviewerId": "user_001",
  "note": "Resolution note",
  "draftKnowledge": {
    "knowledgeType": "faq",
    "title": "Return after 7 days",
    "question": "Can customers return products after 7 days?",
    "answer": "Draft corrected answer",
    "tags": ["return_policy"]
  },
  "targetKnowledgeId": "know_001"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "badCaseId": "badcase_001",
    "status": "resolved",
    "createdDraftId": "draft_010"
  },
  "requestId": "req_010"
}
```

Hard rule:

- Created or updated knowledge from Bad Case resolution must enter review before indexing.

## 11. Future Roadmap APIs: Phase 2-4 (Not Implemented)

These API groups belong to the formal roadmap, but they are not implemented through M6 and must not be started without an explicit future phase.

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
