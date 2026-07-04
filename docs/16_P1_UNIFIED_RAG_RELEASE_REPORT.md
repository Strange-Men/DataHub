# P1-M11 Unified DataHub RAG Release Report

## 1. Release Goal

P1-M11 is the final Phase 1 release checkpoint.

Goal:

```text
DataHub governed knowledge sources
-> unified knowledge candidates
-> approved candidates
-> unified local RAG chunks
-> CustomerOpsAgent restricted retrieval API
```

Target tag:

```text
p1-m11-unified-rag-release
```

Historical tags remain unchanged and must not be moved, deleted, or renamed.

## 2. Phase 1 Route Review

Completed P1 route:

- M2: JSON customer service chat import.
- M3: Cleaning and sanitization.
- M4: Knowledge candidate extraction.
- M5: Human review.
- M6: Local RAG chunk build.
- M6.5: Local RAG quality hardening.
- M7: CustomerOpsAgent restricted retrieval.
- M7.5: Retrieval contract polish.
- M8: Bad Case feedback.
- M8.5: Bad Case to pending-review draft.
- P1-M9: Phase-one core release freeze.
- P1-M9.5: Public dataset evaluation.
- P1-M10: Legacy RAG migration.
- P1-M11: Unified DataHub RAG release.

## 3. Unified RAG Sources

P1-M11 defines the unified DataHub RAG source set as:

```text
chat_logs
public_dataset
bad_case
legacy_rag
manual
```

Current implemented coverage:

- `chat_logs`: JSON customer service chat import, cleaning, extraction, review, RAG.
- `public_dataset`: P1-M9.5 Bitext sample evaluation, converted into DataHub import JSON.
- `bad_case`: Bad Case-generated pending-review drafts; approved drafts can enter RAG.
- `legacy_rag`: CustomerOpsAgent legacy RAG export import with trusted and review-required modes.
- `manual`: reserved source type for future manual knowledge supplements; not implemented as a dedicated UI/API in P1.

## 4. Unified Candidate And Chunk Rules

All current sources converge into DataHub knowledge candidates.

Rules:

- Candidates must preserve source trace.
- Only `approved` candidates can become local RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates cannot become chunks.
- RAG build remains idempotent.
- CustomerOpsAgent retrieval reads only `backend/storage/rag_chunks/`.
- CustomerOpsAgent does not read raw batches, sanitized batches, or candidate files directly.

## 5. CustomerOpsAgent DataHub-Only Retrieval Contract

P1-M11 locks the CustomerOpsAgent-facing retrieval contract:

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
POST /api/customer-ops-agent/bad-cases
```

Required local development header:

```text
X-DataHub-Client: CustomerOpsAgent
```

Recommended CustomerOpsAgent flow:

```text
CustomerOpsAgent receives user query
-> call DataHub retrieval API
-> use returned answer / chunks / source trace
-> generate final answer
-> submit Bad Case with retrieval_id if the answer is wrong or incomplete
```

DataHub returns a unified retrieval shape. CustomerOpsAgent does not need to know whether the result came from chat logs, public samples, Bad Case drafts, or legacy RAG imports.

## 6. P1 Completed Capabilities

P1 completed:

- Raw JSON import.
- Raw/sanitized layer separation.
- PII masking for common patterns.
- Rule-based mock extraction.
- Human review.
- Approved-only local RAG chunking.
- RAG build idempotency.
- Local keyword/mock retrieval.
- CustomerOpsAgent restricted retrieval.
- Retrieval traces and retrieval ids.
- Bad Case queue.
- Bad Case to pending-review draft.
- Public dataset small-sample evaluation.
- Legacy RAG migration.
- Unified multi-source local RAG release.
- Chinese and English README for P1-M11 release positioning.

## 7. P1 Non-Goals

P1 does not implement:

- Production vector database.
- Embedding model.
- Database or ORM.
- Real LLM extraction.
- Production authentication.
- Automatic Bad Case approval.
- Automatic RAG rebuild from Bad Case resolution.
- Dedicated manual knowledge supplement API.
- Complex BI.
- Complex multi-tenant permissions.

## 8. P2 / P3 / P4 Roadmap

P2 roadmap, not implemented:

```text
AI Material Center & Multimodal Knowledge
```

P3 roadmap, not implemented:

```text
Sales training dataset export
Fine-tuning dataset export
```

P4 roadmap, not implemented:

```text
MCP Tools & Agent Cluster Integration
```

## 9. Known Limitations

- Storage is local JSON under `backend/storage/`.
- Retrieval is local keyword/mock retrieval.
- No real vector store is connected.
- No embedding model is connected.
- No database or ORM is connected.
- No real LLM is connected.
- CustomerOpsAgent repository is not modified in this DataHub release.
- `X-DataHub-Client` is a local development auth placeholder, not production security.
- Public dataset evaluation uses a 50-conversation sample, not full production traffic.
- Legacy RAG sample is fake data only.

## 10. Test Result

Required verification for P1-M11:

```powershell
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py
python backend\tests\test_customerops_retrieval.py
python backend\tests\test_rag_quality.py
python backend\tests\test_bad_case_feedback.py
python backend\tests\test_phase_one_flow.py
python backend\tests\test_public_dataset_eval_flow.py
python backend\tests\test_legacy_rag_migration.py
python backend\tests\test_unified_rag_release.py
```

Expected result:

```text
All commands pass.
```

The unified release test verifies:

- `chat_logs` candidates can enter RAG after approval.
- `public_dataset` candidates can enter RAG after approval.
- trusted `legacy_rag` candidates can enter RAG.
- Bad Case-generated drafts stay `pending_review` until approved.
- Approved Bad Case drafts can enter RAG.
- CustomerOpsAgent retrieval returns a consistent shape with `source_type` and source trace.
- Pending, rejected, and needs-revision candidates remain outside RAG.
- Repeated RAG build remains idempotent.
- No vector database, embedding, database, ORM, or MCP route is introduced.

## 11. Release Tag

Release tag:

```text
p1-m11-unified-rag-release
```

This is the P1 final release tag.

## 12. Next Route

Recommended next step after P1-M11:

```text
Pause development for project review / resume packaging / architecture retrospective
```

If development continues later, the next product phase may be:

```text
P2-M1 Material Ingestion
```

P2 must not start unless explicitly requested.
