# P2-M4 Knowledge Asset Foundation Report

## 1. Completion Summary

P2-M4 Knowledge Asset Foundation is complete.

This milestone adds an isolated governance projection:

```text
approved Asset Review Snapshot
        -> publish
active P2 Knowledge Asset
```

It does not write P1 `rag_chunks` or `rag_embeddings`, change CustomerOpsAgent retrieval, call an embedding provider, synchronize RAG, implement multimodal retrieval, or expose P2 content to an Agent.

P1 remains sealed at `p1-m24.3-real-embedding-online-release`.

## 2. Knowledge Asset Model

One additive `knowledge_assets` table represents a governed and traceable P2 knowledge unit:

| Field | Responsibility |
|---|---|
| `id` | Stable Knowledge Asset identity |
| `source_snapshot_id` | Unique immutable publication source and idempotency key |
| `asset_id` | Owning P2 Asset |
| `content` | Approved snapshot content copied at publication time |
| `content_type` | Shared extraction type such as OCR, Caption, or metadata |
| `status` | `draft`, `active`, or `archived` |
| `version` | Monotonic version per Asset and content type |
| `metadata_json` | Governance/source version metadata; explicitly records no RAG sync |
| `created_at`, `updated_at` | Audit timestamps |

The database enforces:

- one Knowledge Asset per `source_snapshot_id`;
- one version number per `(asset_id, content_type)`;
- no overwrite of previous content or source identity.

`draft` is reserved by the model for later governance workflows. P2-M4 publish creates an `active` record directly because the source is already an approved immutable snapshot. Archive changes only status and `updated_at`; it never edits content or provenance.

## 3. Publish and Version Rules

The `KnowledgeAssetService` owns publication validation and orchestration:

1. Load the requested immutable Snapshot.
2. Load its Review and require `review_status=approved`.
3. Validate that Snapshot, Review, Extraction, and Asset identifiers form one consistent source chain.
4. Require non-empty approved content and content type.
5. Use `source_snapshot_id` as the publication idempotency key.
6. Allocate the next version under an Asset row lock for the same Asset/content type.
7. Archive the previous active version in the same transaction.
8. Create the new active Knowledge Asset.

Pending, rejected, and needs-revision reviews cannot publish. Under normal M3 behavior they never produce snapshots; P2-M4 also re-checks the source Review so a malformed or externally inserted snapshot cannot bypass the approved-only boundary.

Publishing the same Snapshot again returns the existing Knowledge Asset with `created=false` and HTTP 200. It does not create a duplicate, allocate another version, or reactivate an archived record. A later approved Snapshot creates a later version and archives the older active version without overwriting it.

No publication queue, worker, embedding call, P1 RAG write, or Agent notification exists in this milestone.

## 4. API

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/snapshots/{id}/publish` | Publish an approved Snapshot; HTTP 201 when created and 200 for an idempotent replay |
| `GET` | `/api/knowledge-assets` | Paginated list with optional `asset_id` and status filters |
| `GET` | `/api/knowledge-assets/{id}` | Knowledge Asset detail with complete source trace |
| `POST` | `/api/knowledge-assets/{id}/archive` | Idempotently archive a Knowledge Asset |

Stable errors include:

- `SNAPSHOT_NOT_FOUND` (404)
- `SNAPSHOT_NOT_APPROVED` (409)
- `KNOWLEDGE_ASSET_NOT_FOUND` (404)
- `KNOWLEDGE_SOURCE_TRACE_INVALID` (409)

All routes are additive. No P1 API response or path was changed.

## 5. Source Trace

Every list and detail record resolves and validates this full lineage:

```text
Knowledge Asset
  -> source_snapshot_id / snapshot_version
  -> review_id / review_status / review_version
  -> extraction_id / extraction_job_id / extraction_type / extraction_version
  -> asset_id / file_name / hash / status
```

The repository does not merely echo metadata JSON. It queries each source row and verifies that the Asset, Extraction, Review, and Snapshot relationships agree. Missing or inconsistent lineage is surfaced as `KNOWLEDGE_SOURCE_TRACE_INVALID`; it is not silently returned as trusted knowledge.

## 6. Frontend

The existing dark Material Center received only the minimum P2-M4 controls:

- publish an approved Snapshot as a Knowledge Asset;
- show whether a Snapshot has already been published;
- list Knowledge Assets for the selected Asset;
- display content type, active/archive status, version, and source identifiers;
- archive an active Knowledge Asset.

The page explicitly states that Knowledge Assets have not entered RAG. It adds no RAG page, embedding action, retrieval tester, queue, bulk operation, or UI redesign.

## 7. Verification

Focused P2-M4 suite:

```text
python -m pytest -q backend/tests/test_knowledge_asset_foundation.py
6 passed
```

Coverage includes approved publication, non-approved rejection, idempotent replay, archive idempotency/content preservation, list/detail trace completeness, and immutable multi-version history.

Full exact-source suite in a clean isolated Git workspace:

```text
python -m pytest -q backend/tests
274 passed, 32 warnings in 110.98s
```

Additional gates:

```text
npm run build
tsc && vite build
PASS
```

The warnings are existing FastAPI lifecycle and pytest configuration warnings plus intentional embedding-provider fallback warnings; they are not failures.

## 8. P1 Regression

Final authoritative online command:

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 300 --verbose --stop-on-fail
```

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 80.3 s |
| Trace | `p1-harness-20260714-144136-257fd9` |
| Health | P1-M24.3; PostgreSQL healthy |
| pgvector | Available; extension enabled |
| Vector sync | 35 chunks, 35 embeddings, 0 failures |
| Embedding | SiliconFlow, 1536 dimensions |
| Retrieval | `customerops_vector_retrieval`, no fallback |
| Bad Case | Feedback and pending-review draft passed |

An earlier run used a 120-second per-request limit and timed out at the external `/api/rag/build` call after its first six steps passed. The final warmed run above used the documented higher timeout and completed all ten steps; it is the authoritative regression result.

The P2-M4 modules do not import P1 RAG storage, embedding, or CustomerOpsAgent retrieval modules.

## 9. Files Changed

Backend:

- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/review_repositories.py`
- `backend/app/knowledge_asset_schemas.py`
- `backend/app/knowledge_asset_repositories.py`
- `backend/app/knowledge_asset_service.py`
- `backend/app/knowledge_asset_routes.py`
- `backend/tests/test_knowledge_asset_foundation.py`

Frontend:

- `frontend/src/types.ts`
- `frontend/src/pages/P2MaterialCenter.tsx`
- `frontend/src/styles.css`

Documentation:

- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/45_P2_M4_KNOWLEDGE_ASSET_FOUNDATION_REPORT.md`

## 10. Boundary Audit

- No P1 table or schema definition changed.
- No direct write to P1 `rag_chunks` or `rag_embeddings` was added.
- No CustomerOpsAgent retrieval or P1 RAG business logic changed.
- No embedding, OCR, Caption, Vision LLM, multimodal retrieval, RAG sync, or Agent call was added.
- No P2-M1, M2, or M3 model contract was redesigned; M4 only adds a public Snapshot lookup needed for the new projection.
- No dependency, environment variable, secret, uploaded binary, local database, migration rewrite, or tag is included.

## 11. P2-M5 Recommendation

P2-M5 should begin with a separate **isolated P2 Knowledge Index planning gate**, not by writing the existing P1 index. Recommended decisions before implementation:

1. define a P2-only index/schema and synchronization state contract;
2. decide whether the first retrieval representation is reviewed text bridge only;
3. define active/archive propagation, re-index idempotency, delete/withdraw behavior, and evaluation data;
4. design query-time P1/P2 result fusion without changing the sealed P1 write path;
5. require explicit regression gates before CustomerOpsAgent can consume any P2 result.

Until that milestone is explicitly authorized, Knowledge Assets remain governed P2 records and are not RAG-visible.
