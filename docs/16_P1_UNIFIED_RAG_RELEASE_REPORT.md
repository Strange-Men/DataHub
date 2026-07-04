# P1-M11 Unified DataHub RAG Release Report

## 1. Release Goal

P1-M11 is the unified DataHub RAG release checkpoint.

P1-M11 was originally treated as the Phase 1 final release. After the high-quality DataHub goal was refined, P1-M11 is now considered the unified RAG release, while P1-M15 is the planned final Phase 1 high-quality data platform release.

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

This is the P1 unified RAG release tag.

## 12. Next Route

Recommended next step after P1-M11:

```text
P1-M12 Advanced Machine Cleaning & Data Quality Scoring
```

Updated Phase 1 high-quality route:

- P1-M12: Advanced machine cleaning and data quality scoring.
- P1-M13: Chinese admin console and manual cleaning workbench.
- P1-M14: Knowledge review quality console.
- P1-M15: High-quality DataHub P1 final release.

P2 must not start unless explicitly requested after P1-M15.

## 13. P1-M13 Addendum

P1-M13 extends the post-unified-RAG Phase 1 quality work with a Chinese admin console and manual cleaning workbench.

Added capabilities:

- Chinese DataHub dashboard with P1/P2/P3/P4 capability cards.
- P2/P3/P4 shown as Roadmap / not connected, not implemented.
- Manual cleaning API for sanitized messages.
- Manual cleaning records under ignored local storage.
- Extraction respects manual cleaning decisions:
  - `drop` and `needs_review` are skipped.
  - `keep_edited` uses manually corrected content.
  - `keep` uses existing sanitized content.

This addendum does not change the P1-M11 unified RAG tag. It documents the continued Phase 1 high-quality data platform hardening route toward P1-M15.

## 14. P1-M14 Addendum

P1-M14 adds the Chinese knowledge review quality console.

Added capabilities:

- Candidate list and local filters in the admin console.
- Candidate editing for question, answer, intent, tags, risk level, and quality score.
- Review actions for approved, rejected, and needs_revision decisions.
- Reviewer and review note capture.
- Source trace, quality score, cleaning issues, and risk flags shown to reviewers.
- Reviewer-facing guide at `docs/20_KNOWLEDGE_REVIEW_GUIDE.md`.

P1-M14 preserves the P1 RAG boundary:

- Only approved candidates can become local RAG chunks.
- Pending, needs-revision, and rejected candidates cannot become chunks.
- No production vector database, embedding model, database, ORM, real LLM, MCP, or P2/P3/P4 feature is introduced.
