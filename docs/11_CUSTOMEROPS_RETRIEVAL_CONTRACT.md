# CustomerOpsAgent Retrieval Contract

## 1. Purpose

This document defines the current DataHub retrieval contract for CustomerOpsAgent.

Current stage:

```text
M7.5 Retrieval Contract Polish
```

The contract is read-only and restricted to approved local RAG chunks.

## 2. Current APIs

DataHub currently exposes these CustomerOpsAgent-facing APIs:

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
```

These APIs are implemented in DataHub only. The CustomerOpsAgent repository has not been modified.

## 3. Auth Placeholder

Current local development auth placeholder:

```text
X-DataHub-Client: CustomerOpsAgent
```

Rules:

- Both CustomerOpsAgent retrieval APIs require this header.
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
- Optional filters for `intent`, `tags`, and `risk_level`.
- Optional `conversation_id`.
- Optional `agent_session_id`.

The retrieval trace API supports:

- Lookup by `retrieval_id`.
- Returning retrieval metadata for later M8 Bad Case linkage.
- Returning result chunk ids, not full raw records.

## 5. Current Non-Capabilities

M7.5 does not support:

- Bad Case submission.
- Bad Case UI.
- Human correction workflow.
- Real vector database.
- Embedding model.
- Real LLM.
- Database or ORM.
- Direct knowledge modification.
- Direct RAG chunk writes by CustomerOpsAgent.
- Production authentication.

M8 is the planned stage for Bad Case feedback.

## 6. CustomerOpsAgent Rules

CustomerOpsAgent must:

- Call DataHub APIs only.
- Send `X-DataHub-Client: CustomerOpsAgent`.
- Treat retrieval results as read-only.
- Store or pass `retrieval_id` when a future Bad Case needs to reference a retrieval.

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

`retrieval_id` is reserved for M8 Bad Case feedback.

Future Bad Case records should be able to reference:

- `retrieval_id`
- user query
- agent answer
- expected answer if available
- issue type
- related context metadata

M7.5 only prepares the retrieval side of this linkage. It does not implement Bad Case submission or resolution.
