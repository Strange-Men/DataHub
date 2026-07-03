# DataHub API Contract Draft

This document defines the phase-one API draft. It is a planning contract, not an implementation.

Base assumptions:

- React admin UI calls management APIs.
- CustomerOpsAgent calls restricted retrieval and Bad Case APIs.
- All APIs return structured errors.
- Raw and unapproved data must never be retrievable by CustomerOpsAgent.

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

## 2. M2 JSON Data Import APIs

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

## 2A. Future Import APIs Not Implemented In M2

The earlier generic import direction is reserved for later stages:

- CSV import.
- Manual text paste import.
- Upload-based import.
- Duplicate import detection.
- Database-backed batch storage.

These are not implemented in M2.

## 3. Cleaning Task APIs

### 3.1 Start Cleaning And Desensitization

`POST /api/processing/cleaning-jobs`

Request:

```json
{
  "batchId": "batch_001",
  "options": {
    "deduplicate": true,
    "desensitize": true,
    "detectNearDuplicates": true
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "jobId": "clean_job_001",
    "batchId": "batch_001",
    "status": "queued"
  },
  "requestId": "req_002"
}
```

Allowed source states:

- `raw_imported`
- `failed_cleaning`
- `failed_desensitization`

Possible errors:

- `BATCH_NOT_FOUND`
- `INVALID_STATE`: Batch is not eligible for cleaning.
- `JOB_ALREADY_RUNNING`

Hard rule:

- Cleaning must produce sanitized records before extraction can start.

### 3.2 Get Cleaning Job Status

`GET /api/processing/cleaning-jobs/{jobId}`

Response fields:

- `jobId`
- `batchId`
- `status`: `queued | running | completed | failed`
- `rawRecordCount`
- `cleanedRecordCount`
- `sanitizedRecordCount`
- `duplicateCount`
- `errorSummary`

## 4. Knowledge Extraction APIs

### 4.1 Start Knowledge Extraction

`POST /api/extraction/jobs`

Request:

```json
{
  "batchId": "batch_001",
  "knowledgeTypes": [
    "faq",
    "standard_answer",
    "business_rule",
    "human_handoff_rule",
    "forbidden_answer_rule"
  ],
  "mode": "mock | llm"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "jobId": "extract_job_001",
    "batchId": "batch_001",
    "status": "queued"
  },
  "requestId": "req_003"
}
```

Allowed source states:

- `sanitized`
- `failed_extraction`

Possible errors:

- `BATCH_NOT_FOUND`
- `INVALID_STATE`: Batch is not sanitized.
- `UNSUPPORTED_KNOWLEDGE_TYPE`
- `LLM_PROVIDER_DISABLED`

Hard rule:

- Extraction must not read from raw records.

### 4.2 List Knowledge Drafts

`GET /api/knowledge/drafts?batchId=batch_001&status=review_pending`

Response fields:

- `draftId`
- `knowledgeType`
- `title`
- `question`
- `answer`
- `ruleContent`
- `tags`
- `status`
- `sourceRecordIds`
- `createdAt`

Allowed states returned:

- `review_pending`
- `needs_revision`
- `rejected`

Drafts are not retrievable by CustomerOpsAgent.

## 5. Human Review APIs

### 5.1 Review Knowledge Draft

`POST /api/review/knowledge-drafts/{draftId}/decision`

Request:

```json
{
  "decision": "approve | reject | needs_revision",
  "reviewerId": "user_001",
  "reviewNote": "optional safe note",
  "editedKnowledge": {
    "title": "Shipping delay FAQ",
    "question": "Why is my shipment delayed?",
    "answer": "Approved answer text",
    "knowledgeType": "faq",
    "tags": ["shipping", "delay"],
    "sourceNote": "Derived from June customer service conversations."
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "draftId": "draft_001",
    "knowledgeId": "know_001",
    "status": "approved",
    "version": 1,
    "reviewedAt": "2026-07-03T11:00:00+08:00"
  },
  "requestId": "req_004"
}
```

Allowed draft states:

- `review_pending`
- `needs_revision`

Possible errors:

- `DRAFT_NOT_FOUND`
- `INVALID_STATE`
- `MISSING_SOURCE_REFERENCE`
- `UNSAFE_CONTENT`

Hard rule:

- Approved knowledge must retain source references.

### 5.2 Create Manual Knowledge

`POST /api/knowledge/manual`

Request:

```json
{
  "knowledgeType": "faq",
  "title": "Manual supplement title",
  "question": "Customer question",
  "answer": "Reviewed answer draft",
  "tags": ["manual"],
  "sourceNote": "Manual supplement from reviewer",
  "sourceRecordIds": []
}
```

Response:

```json
{
  "success": true,
  "data": {
    "draftId": "draft_manual_001",
    "status": "review_pending"
  },
  "requestId": "req_005"
}
```

Manual knowledge must still pass review before indexing.

## 6. Knowledge Base APIs

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

## 7. RAG Build APIs

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

## 8. RAG Retrieval API

### 8.1 Internal Retrieval

`POST /api/rag/search`

Request:

```json
{
  "query": "How do I handle a refund request?",
  "topK": 5,
  "filters": {
    "knowledgeTypes": ["faq", "business_rule"],
    "tags": ["refund"]
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "knowledgeId": "know_001",
        "knowledgeType": "faq",
        "title": "Refund policy",
        "content": "Approved answer content",
        "score": 0.87,
        "version": 1,
        "sourceRecordIds": ["record_001"],
        "approvedAt": "2026-07-03T11:00:00+08:00"
      }
    ]
  },
  "requestId": "req_007"
}
```

Allowed retrieval states:

- `indexed`

Possible errors:

- `QUERY_TOO_LONG`
- `INVALID_FILTER`
- `RAG_INDEX_UNAVAILABLE`

Hard rule:

- This API must only return approved and indexed knowledge.

## 9. CustomerOpsAgent APIs

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

## 10. Bad Case Management APIs

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
