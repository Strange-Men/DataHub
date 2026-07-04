# CustomerOpsAgent Retrieval Contract

## 1. Purpose

This document defines the current DataHub retrieval contract for CustomerOpsAgent.

Current related stage:

```text
P1-M11 Unified DataHub RAG Release
```

The contract is read-only and restricted to approved local RAG chunks.

## 2. Current APIs

DataHub currently exposes these CustomerOpsAgent-facing APIs:

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
POST /api/customer-ops-agent/bad-cases
```

These APIs are implemented in DataHub only. The CustomerOpsAgent repository has not been modified.

## 3. Auth Placeholder

Current local development auth placeholder:

```text
X-DataHub-Client: CustomerOpsAgent
```

Rules:

- CustomerOpsAgent retrieval and Bad Case submission APIs require this header.
- Missing header returns `UNAUTHORIZED_CLIENT`.
- Any value other than `CustomerOpsAgent` returns `UNAUTHORIZED_CLIENT`.
- This is not production authentication.
- This does not introduce an API key.
- This does not introduce a real token.
- No secret should be stored in `.env` for this placeholder.

Future replacement options:

- Service token.
- Gateway authentication.
- MCP tool permission.
- Agent identity and authorization policy.

## 4. Capabilities

The retrieval API supports:

- Read-only retrieval.
- Approved local `rag_chunked` results only.
- `retrieval_id` generation.
- Source trace in every result.
- `matched_terms` in every result.
- Keyword/mock `score` in every result.
- Legacy RAG source trace when a result came from P1-M10 migration.
- Optional filters for `intent`, `tags`, and `risk_level`.
- Optional `conversation_id`.
- Optional `agent_session_id`.

The retrieval trace API supports:

- Lookup by `retrieval_id`.
- Returning retrieval metadata for later M8 Bad Case linkage.
- Returning result chunk ids, not full raw records.

## 5. Current Non-Capabilities

M8 still does not support:

- Automatic Bad Case approval.
- Automatic candidate modification from Bad Cases.
- Automatic RAG chunk modification from Bad Cases.
- Automatic RAG rebuild or re-index from Bad Cases.
- Real vector database.
- Embedding model.
- Real LLM.
- Database or ORM.
- Direct knowledge modification.
- Direct RAG chunk writes by CustomerOpsAgent.
- Production authentication.

M8.5 implements human-triggered Bad Case conversion into new `pending_review` drafts. It does not approve those drafts or put them into RAG.

P1-M9 freezes and verifies this contract as part of the Phase 1 core loop. It does not add new CustomerOpsAgent-facing APIs beyond the M7/M8 surface.

P1-M10 adds DataHub-side legacy RAG migration. CustomerOpsAgent retrieval may now return approved chunks with `source_type: legacy_rag`, `source_legacy_id`, and `source_import_id`.

P1-M11 locks DataHub as the recommended CustomerOpsAgent-only retrieval source from the DataHub side. It documents the cutover path in `docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md`. P1-M11 still does not modify the CustomerOpsAgent repository.

## 6. CustomerOpsAgent Rules

CustomerOpsAgent must:

- Call DataHub APIs only.
- Send `X-DataHub-Client: CustomerOpsAgent`.
- Treat retrieval results as read-only.
- Store or pass `retrieval_id` when a future Bad Case needs to reference a retrieval.
- Treat DataHub retrieval as the primary RAG source after P1-M11 cutover planning.

CustomerOpsAgent must not:

- Access raw data.
- Access sanitized data.
- Access `knowledge_candidates`.
- Modify candidates.
- Approve or reject knowledge.
- Directly write RAG chunks.
- Directly read or write DataHub storage.
- Bypass DataHub review workflow.

## 7. Retrieve API

`POST /api/customer-ops-agent/retrieve`

Headers:

```text
X-DataHub-Client: CustomerOpsAgent
```

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
- `query` must be non-empty after trimming.
- `query` maximum length is 500 characters.
- `top_k` defaults to 5.
- `top_k` minimum is 1.
- `top_k` maximum is 10.
- `filters` is optional.
- `conversation_id` is optional.
- `agent_session_id` is optional.

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
        "source_type": "sanitized_batch",
        "source_batch_id": "batch_abc123",
        "source_conversation_id": "conv_001",
        "source_message_ids": ["msg_001", "msg_002"],
        "source_legacy_id": null,
        "source_import_id": null,
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
  "requestId": "req_abc123"
}
```

Empty results:

- If no approved local RAG chunks match, DataHub returns `results: []`.
- Empty results are not an error.

## 8. Retrieval Trace API

`GET /api/customer-ops-agent/retrievals/{retrieval_id}`

Headers:

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
  "requestId": "req_abc123"
}
```

Trace storage:

```text
backend/storage/retrieval_logs/
```

The storage directory is ignored by Git.

## 9. Error Response

CustomerOpsAgent retrieval APIs return safe structured errors:

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

Error codes:

- `UNAUTHORIZED_CLIENT`: missing or invalid `X-DataHub-Client`.
- `INVALID_QUERY`: query is empty after trimming.
- `QUERY_TOO_LONG`: query exceeds 500 characters.
- `INVALID_TOP_K`: top_k is outside 1-10.
- `RETRIEVAL_NOT_FOUND`: retrieval trace does not exist.

Errors must not expose:

- Raw customer records.
- Sanitized message content from source batches.
- Secrets.
- Internal stack traces.

## 10. PowerShell Examples

Retrieve:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Read retrieval trace:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrievals/{retrieval_id} `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"}
```

## 11. M8 Linkage

`retrieval_id` is used by M8 Bad Case feedback.

Bad Case records can reference:

- `retrieval_id`
- user query
- agent answer
- expected answer if available
- issue type
- related context metadata

M8 implements:

```text
POST /api/customer-ops-agent/bad-cases
GET  /api/bad-cases
GET  /api/bad-cases/{bad_case_id}
PATCH /api/bad-cases/{bad_case_id}
```

Bad Case submission requires the same header:

```text
X-DataHub-Client: CustomerOpsAgent
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

M8 Bad Case records are saved under:

```text
backend/storage/bad_cases/
```

M8.5 implements:

```text
POST /api/bad-cases/{bad_case_id}/create-draft
```

This creates a new `pending_review` candidate with:

- `source_type: bad_case`
- `source_bad_case_id`
- `source_retrieval_id`
- `source_chunk_ids`
- `extraction_method: bad_case_resolution`

M8.5 does not implement automatic approval, existing candidate mutation, RAG chunk mutation, RAG rebuild, or re-indexing.

Bad Case submission may return safe structured errors such as:

- `UNAUTHORIZED_CLIENT`
- `INVALID_RETRIEVAL_REFERENCE`
- `INVALID_USER_QUERY`
- `USER_QUERY_TOO_LONG`
- `INVALID_AGENT_ANSWER`
- `AGENT_ANSWER_TOO_LONG`
- `INVALID_ISSUE_TYPE`
- `INVALID_SEVERITY`
- `BAD_CASE_NOT_FOUND`
- `BAD_CASE_IGNORED`
- `INVALID_DRAFT_PAYLOAD`
