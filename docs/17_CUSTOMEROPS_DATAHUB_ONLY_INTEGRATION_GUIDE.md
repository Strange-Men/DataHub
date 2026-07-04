# CustomerOpsAgent DataHub-Only Integration Guide

## 1. Purpose

This guide describes how CustomerOpsAgent should switch from an independent RAG path to DataHub-only governed retrieval after P1-M11.

P1-M11 scope:

- DataHub provides the unified retrieval contract.
- DataHub keeps source trace and retrieval ids.
- DataHub can receive Bad Cases from CustomerOpsAgent.
- The CustomerOpsAgent repository is not modified in this DataHub milestone.

## 2. Legacy RAG Migration Strategy

P1-M10 introduced a DataHub-side migration path for CustomerOpsAgent legacy RAG knowledge:

```text
CustomerOpsAgent legacy RAG export
-> POST /api/legacy-rag/import
-> DataHub knowledge candidates
-> approved candidates or pending_review candidates
-> POST /api/rag/build
-> CustomerOpsAgent retrieval API
```

Trusted legacy knowledge:

```text
trusted_import=true
-> review_status: approved
-> eligible for local RAG build
```

Review-required legacy knowledge:

```text
trusted_import=false
-> review_status: pending_review
-> not eligible for RAG until normal human approval
```

## 3. DataHub-Only Retrieval Rule

After P1-M11, the recommended CustomerOpsAgent rule is:

```text
CustomerOpsAgent should use DataHub as the primary RAG retrieval source.
```

CustomerOpsAgent should not silently continue using the old independent RAG path as a parallel primary source.

If DataHub is unavailable, CustomerOpsAgent may use a safe fallback answer, escalation, or controlled degraded mode. The fallback should be explicit and observable, not an invisible switch back to stale legacy RAG.

## 4. Recommended Runtime Flow

```text
CustomerOpsAgent receives user query
-> call DataHub POST /api/customer-ops-agent/retrieve
-> read returned chunks, answer fields, scores, matched_terms, and source trace
-> generate the final customer-facing response
-> if the answer is wrong, incomplete, unsafe, or off-tone
-> submit Bad Case to DataHub with retrieval_id
```

## 5. Required Header

Current local development auth placeholder:

```text
X-DataHub-Client: CustomerOpsAgent
```

Notes:

- This is not production authentication.
- No API key or real token is introduced in P1.
- Future production options may include service tokens, gateway auth, MCP permissions, or Agent identity policies.

## 6. Retrieve API

```text
POST /api/customer-ops-agent/retrieve
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

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Response shape:

```json
{
  "success": true,
  "data": {
    "retrieval_id": "retrieval_xxx",
    "query": "shipping Germany",
    "top_k": 5,
    "retrieval_mode": "customerops_local_mock_retrieval",
    "results": [
      {
        "score": 0.82,
        "matched_terms": ["shipping"],
        "chunk_id": "chunk_kc_xxx",
        "candidate_id": "kc_xxx",
        "source_type": "legacy_rag",
        "source_batch_id": null,
        "source_conversation_id": null,
        "source_message_ids": [],
        "source_bad_case_id": null,
        "source_retrieval_id": null,
        "source_chunk_ids": [],
        "source_legacy_id": "legacy_shipping_001",
        "source_import_id": "legacy_import_xxx",
        "knowledge_type": "faq",
        "intent": "shipping",
        "tags": ["shipping", "delivery", "legacy_rag"],
        "risk_level": "low",
        "quality_score": 0.85,
        "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
        "chunk_text": "Question: ...\nAnswer: ...",
        "review_status": "approved",
        "build_method": "local_json_mock_retrieval"
      }
    ],
    "created_at": "2026-07-03T12:30:00+00:00"
  },
  "requestId": "req_xxx"
}
```

## 7. Retrieval Trace API

```text
GET /api/customer-ops-agent/retrievals/{retrieval_id}
```

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrievals/{retrieval_id} `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"}
```

Purpose:

- Read retrieval metadata.
- Bind later Bad Cases to a specific retrieval.
- Do not return raw records.

## 8. Bad Case Submission

```text
POST /api/customer-ops-agent/bad-cases
```

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/bad-cases `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{
    "retrieval_id":"retrieval_xxx",
    "user_query":"Where is my order?",
    "agent_answer":"Your package should arrive soon.",
    "issue_type":"wrong_answer",
    "expected_answer":"The answer should mention tracking status or escalation.",
    "severity":"medium"
  }'
```

Bad Cases enter DataHub's queue. They do not directly modify candidates or RAG chunks.

## 9. Error Codes

CustomerOpsAgent-facing APIs return safe structured errors:

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED_CLIENT",
    "message": "CustomerOpsAgent client header is required.",
    "details": {}
  },
  "requestId": "req_xxx"
}
```

Common error codes:

- `UNAUTHORIZED_CLIENT`
- `INVALID_QUERY`
- `QUERY_TOO_LONG`
- `INVALID_TOP_K`
- `RETRIEVAL_NOT_FOUND`
- `INVALID_RETRIEVAL_REFERENCE`
- `INVALID_USER_QUERY`
- `USER_QUERY_TOO_LONG`
- `INVALID_AGENT_ANSWER`
- `AGENT_ANSWER_TOO_LONG`
- `INVALID_ISSUE_TYPE`
- `INVALID_SEVERITY`

## 10. Fallback Strategy

P1-M11 target:

```text
DataHub-only retrieval as the primary RAG source.
```

If DataHub is unavailable, CustomerOpsAgent should:

- return a safe fallback response,
- ask for clarification,
- escalate to a human,
- or use an explicit degraded mode.

CustomerOpsAgent should not silently use the old RAG path as if nothing happened. Silent fallback would hide governance drift and make Bad Case analysis unreliable.

## 11. CustomerOpsAgent Must Not

CustomerOpsAgent must not:

- Read DataHub raw data.
- Read DataHub sanitized data directly.
- Read DataHub knowledge candidate files directly.
- Modify candidates.
- Approve or reject knowledge.
- Write RAG chunks.
- Rebuild RAG.
- Access `backend/storage/` directly.
- Bypass DataHub review workflow.

## 12. Current Limitations

P1-M11 still uses:

- local JSON storage,
- local keyword/mock retrieval,
- local development auth placeholder.

P1-M11 does not use:

- real vector database,
- embedding model,
- database or ORM,
- real LLM,
- MCP tools,
- production authentication.
