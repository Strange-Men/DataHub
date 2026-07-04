# DataHub Project Review And Boundary

## 1. Current Positioning

DataHub is a multi-source data governance and RAG knowledge platform for Agent clusters.

The current implementation is a Phase 1 text customer service data platform. It turns customer-service-style text data into governed, reviewed, traceable local RAG knowledge for CustomerOpsAgent-style retrieval.

## 2. P1 Completed Capabilities

P1 has completed the high-quality text governance loop:

```text
JSON import
-> advanced machine cleaning
-> manual cleaning
-> knowledge extraction
-> knowledge review
-> approved-only local RAG
-> CustomerOpsAgent restricted retrieval
-> Bad Case feedback
-> Bad Case to pending-review draft
```

Implemented P1 capabilities include:

- JSON customer service chat import.
- Raw and sanitized data separation.
- Advanced machine cleaning with PII masking, duplicate detection, issue labels, risk flags, and quality scoring.
- Manual cleaning workbench and manual cleaning records.
- Rule-based knowledge candidate extraction.
- Knowledge review console with candidate editing and approve / reject / needs-revision decisions.
- Approved-only local RAG chunk build.
- CustomerOpsAgent restricted retrieval API with source trace.
- Bad Case submission and Bad Case to pending-review draft.
- Public dataset small-sample evaluation.
- Legacy RAG migration into DataHub candidates.

## 3. P1 High-Quality Data Governance Loop

P1 is no longer only a local RAG demo. It includes quality gates before retrieval:

- Machine gate: cleaning issues, PII detection, risk flags, quality score, suggested action.
- Human cleaning gate: keep, keep edited, drop, needs review.
- Knowledge review gate: approved, rejected, needs revision.
- Retrieval gate: only approved candidates can become RAG chunks.
- Feedback gate: Bad Cases return as pending-review drafts, not as automatic RAG updates.

## 4. Current Frontend Capabilities

The current frontend is a Chinese dark admin console.

Operational P1 areas:

- Backend connection status.
- Step-based main workflow.
- JSON import and batch refresh.
- Machine cleaning and sanitized batch loading.
- Manual cleaning workbench.
- Knowledge review workbench.
- Local RAG build access from the review area.

Roadmap-only areas:

- P2 AI Material Center.
- P3 data asset reuse.
- P4 MCP and Agent cluster.

Roadmap entries are visible for product structure only. They are not connected to backend features.

## 5. Current Backend Capabilities

The backend can verify:

- Import.
- Cleaning.
- Manual cleaning.
- Extraction.
- Candidate editing and review.
- RAG build idempotency.
- CustomerOpsAgent restricted retrieval.
- Bad Case submission and draft creation.
- Legacy RAG migration.

The backend also exposes `/health` and `/api/health` for frontend connection checks.

## 5A. Frontend API Boundary

The frontend uses relative API paths:

```text
/api/...
```

During local Vite development, `frontend/vite.config.ts` proxies `/api` to:

```text
http://127.0.0.1:8000
```

If the frontend shows "not connected", the most likely causes are:

- FastAPI is not running.
- FastAPI is running on a different host or port.
- The Vite proxy cannot reach `127.0.0.1:8000`.

P1-M15.5 adds `/api/health` so the frontend can check backend connectivity through the same proxy path used by business APIs.

## 6. P2 / P3 / P4 Current Status

P2, P3, and P4 are not implemented.

Current status:

- P2 is Roadmap / frontend entry / architecture reservation only.
- P3 is Roadmap / frontend entry / architecture reservation only.
- P4 is Roadmap / frontend entry / architecture reservation only.

Do not claim that multimodal ingestion, dataset export, fine-tuning export, MCP tools, or Agent-cluster production integration are implemented.

## 7. Current Technical Boundaries

Current boundaries:

- Local JSON storage（当前 P1 仍未数据库化）。
- Local keyword/mock retrieval.
- No real vector database.
- No embedding model.
- No database（数据库持久化已列入 P1-M16 至 P1-M20 补强计划，详见 `docs/26_DATABASE_PERSISTENCE_ROADMAP.md`）。
- No ORM（计划在 P1-M16 引入 SQLAlchemy）。
- No real LLM.
- No real multimodal ingestion.
- No OCR / Caption / SKU binding implementation.
- No MCP implementation.
- No CustomerOpsAgent repository modification.
- No production authentication.

These are intentional P1 boundaries, not accidental omissions. Database persistence is the next planned P1 hardening step (P1-M16 through P1-M20), after which P1 can be defined as a deployable, persistent data platform capable of supporting P2/P3/P4.

## 8. Demo-Friendly Flow

The current project is suitable for demonstrating:

1. Start FastAPI backend.
2. Start React frontend.
3. Import sample JSON.
4. Run machine cleaning.
5. Review quality fields.
6. Save a manual cleaning decision.
7. Run extraction.
8. Edit and approve a candidate.
9. Build local RAG.
10. Run CustomerOpsAgent restricted retrieval through API or documented commands.
11. Submit a Bad Case.
12. Convert a Bad Case into a pending-review draft.

## 9. Capabilities Not Suitable To Claim

Do not claim:

- Production vector retrieval.
- Production-grade ranking quality.
- Real embedding retrieval.
- Real LLM extraction.
- Database-backed storage.
- Real multimodal material processing.
- Real sales training export.
- Real fine-tuning dataset export.
- MCP runtime tools.
- CustomerOpsAgent repository migration or deployment.
- Production security or auth.

## 10. Recommended Preparation Before P2

Before starting P2, clarify:

- Material source format from the AI Material Center.
- Whether images, posters, and videos need separate ingestion schemas.
- OCR and Caption provider strategy.
- SKU binding data source.
- Multimodal review status model.
- Whether local JSON remains acceptable or a database/object store is needed.
- Whether RAG retrieval should move from keyword/mock retrieval to embeddings and vector search.

## 11. Non-Goals Of This Document

This document is a project boundary and review note.

It intentionally does not include:

- Resume wording.
- Interview scripts.
- Job-search packaging.
- Personal positioning material.
