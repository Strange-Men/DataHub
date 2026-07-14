# P2-M6 Knowledge Index Foundation Report

## 1. Completion Summary

P2-M6 Knowledge Index Foundation is complete.

This milestone implements only:

```text
active Knowledge Asset
  -> P2 Knowledge Index Entry
  -> deterministic immutable text Chunk
  -> ready
```

It does not create embeddings, vector columns, vector indexes, retrieval APIs, unified retrieval, RRF, or Agent integration. It does not write or modify P1 `rag_chunks`, `rag_embeddings`, embedding logic, or CustomerOpsAgent retrieval.

P1 remains sealed at `p1-m24.3-real-embedding-online-release`.

## 2. Schema Decision

P2-M6 adds two isolated control/data-plane tables. Both work on SQLite and PostgreSQL through the existing SQLAlchemy table initialization path.

### 2.1 `p2_knowledge_index_entries`

| Field | Responsibility |
|---|---|
| `id` | Stable Index Entry id |
| `knowledge_asset_id` | Unique immutable Knowledge Asset source and idempotency key |
| `status` | Canonical lifecycle state |
| `generation` | Source Knowledge Asset version for M6 |
| `fingerprint` | Unique deterministic source/projection fingerprint |
| `sync_state` | Projection execution state separated from serving lifecycle |
| `error_message` | Safe failure summary only |
| `created_at`, `updated_at` | Audit timestamps |

`knowledge_asset_id` is unique, so repeated index requests cannot create duplicate control records. `fingerprint` is unique and includes source identity/version/content plus projection/chunker versions.

### 2.2 `p2_knowledge_chunks`

| Field | Responsibility |
|---|---|
| `id` | Deterministic chunk id |
| `index_entry_id` | Owning Index Entry |
| `knowledge_asset_id` | Direct governance source reference |
| `chunk_text` | Immutable text projection |
| `chunk_hash` | SHA-256 of projected text |
| `chunk_order` | Stable zero-based position |
| `metadata_json` | Projection/source versions and explicit non-vector flags |
| `created_at` | Immutable creation time |

`(index_entry_id, chunk_order)` is unique. M6 uses `single_chunk_v1`: one Knowledge Asset produces one chunk. Future chunking changes must use a new projection/chunker generation; they must not overwrite an existing chunk.

No `p2_knowledge_embeddings` table, vector type, pgvector index, provider field, or embedding dependency is added.

## 3. Index State Machine

The externally visible status set is:

```text
pending
building
ready
serving
failed
archived
```

The M6 synchronous path is:

```text
pending/pending
  -> building/building
  -> ready/ready
```

The first value is `status`; the second is `sync_state`.

| Status | Sync state | Meaning in M6 |
|---|---|---|
| `pending` | `pending` | Entry created; projection not started |
| `building` | `building` | Deterministic projection is being written |
| `ready` | `ready` | Chunk and trace are complete; still not searchable |
| `serving` | `ready` | Reserved for P2-M7; M6 exposes no activation API |
| `failed` | `failed` | Projection failed with safe error |
| `archived` | `archived` | Immediately not serving; chunks retained for audit |

Legal transitions are:

- `pending -> building -> ready`
- `building -> failed`
- `failed -> building` reserved for future explicit retry
- `ready -> serving` reserved for P2-M7
- every non-archived state -> `archived`
- `archived` is terminal in M6

Returning `ready` does not claim embedding or retrieval readiness. Frontend and metadata state this explicitly.

## 4. KnowledgeIndexService

`KnowledgeIndexService` owns:

1. Knowledge Asset lookup and full M4 trace validation.
2. `status=active` enforcement.
3. stable fingerprint computation.
4. idempotent pending entry creation.
5. `pending -> building` transition.
6. deterministic text projection and chunk hash/id generation.
7. atomic chunk persistence plus `building -> ready` transition.
8. safe failed-state recording.
9. idempotent Index Entry archive.

It does not import or call the P1 storage/RAG modules, embedding provider, pgvector query, CustomerOpsAgent retrieval, or any unified retrieval component.

## 5. Text Chunk Projection

M6 projection constants:

```text
projection_version = p2_text_projection_v1
chunker_version    = single_chunk_v1
```

The deterministic projection is:

```text
Content type: {normalized content_type}
{approved Knowledge Asset content}
```

The service reads only `knowledge_assets`; it never projects raw Asset bytes, unreviewed Extraction content, or Review drafts.

Fingerprint input:

```text
knowledge_asset_id
knowledge_asset_version
asset_id
content_type
content
projection_version
chunker_version
```

The JSON payload is canonicalized and SHA-256 hashed. Chunk text is independently SHA-256 hashed, and chunk id is deterministically derived from fingerprint, order, and chunk hash.

Chunk metadata records source/projection versions and explicitly stores:

```json
{
  "embedding_created": false,
  "vector_indexed": false
}
```

This is lifecycle preparation, not a searchable index.

## 6. Idempotency and Archive Semantics

- Repeating `POST /api/knowledge-assets/{id}/index` for an active Knowledge Asset returns the existing entry with `created=false` and HTTP 200.
- It does not create a second entry or chunk.
- Archived Knowledge Assets return `KNOWLEDGE_ASSET_NOT_ACTIVE`, including assets that already have an archived Index Entry.
- Explicit Index archive is idempotent and preserves immutable chunks.
- Explicit Knowledge Asset archive updates its Index Entry to `archived` in the same transaction.
- Publishing a later Knowledge Asset version atomically archives the superseded active Knowledge Asset and its Index Entry before creating the new active version.
- M6 does not implicitly reactivate an archived entry. A new Knowledge Asset version creates a new source identity and future entry.

These rules prioritize stale-content prevention over uninterrupted serving. No physical chunk deletion is performed.

## 7. API

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/knowledge-assets/{id}/index` | Active-only, idempotently create Entry and deterministic Chunk; 201 created / 200 replay |
| `GET` | `/api/knowledge-index` | Paginated lifecycle list with optional status and Asset filters |
| `GET` | `/api/knowledge-index/{id}` | Entry, chunks, state, fingerprint, and complete trace |
| `POST` | `/api/knowledge-index/{id}/archive` | Idempotently archive Entry and immediately stop future serving eligibility |

Stable errors include:

- `KNOWLEDGE_ASSET_NOT_FOUND` (404)
- `KNOWLEDGE_ASSET_NOT_ACTIVE` (409)
- `KNOWLEDGE_INDEX_NOT_FOUND` (404)
- `KNOWLEDGE_INDEX_SOURCE_INVALID` (409)
- `KNOWLEDGE_INDEX_PROJECTION_FAILED` (500, safe message)

No retrieval/search API is added.

## 8. Source Trace

Every list/detail record resolves and validates:

```text
Index Entry
  -> Knowledge Asset / version
  -> Snapshot / version
  -> Review / status / version
  -> Extraction / Job / type / version
  -> Asset / file name / hash / status
```

Chunks also store stable source ids and projection versions in metadata, but this metadata is not treated as a replacement source of truth. A missing or inconsistent M4 trace returns `KNOWLEDGE_INDEX_SOURCE_INVALID`.

## 9. Frontend

The existing dark Material Center now minimally shows, per Knowledge Asset:

- Index status (`pending`, `building`, `ready`, reserved `serving`, `failed`, `archived`);
- generation, chunk count, and Entry id;
- create text projection for an active unindexed Knowledge Asset;
- archive a non-archived Index Entry.

The page states that `ready` has no Embedding and is not retrievable. No search page, search input, score, vector status, RRF, or Agent action is added.

## 10. Verification

Focused P2-M6 tests:

```text
python -m pytest -q backend/tests/test_knowledge_index_foundation.py
8 passed
```

Coverage includes active-only indexing, archived rejection, chunk projection/hash/non-vector metadata, stable fingerprint, replay idempotency, explicit and Knowledge Asset archive, complete source trace, and superseded-version Index archive.

P2-M4/M6 lifecycle regression:

```text
14 passed
```

P2 M1-M6 focused regression before the final additional version test:

```text
32 passed
```

Full exact-source suite in a clean isolated Git workspace:

```text
python -m pytest -q backend/tests
282 passed, 36 warnings in 101.04s
```

Additional gates:

```text
python -m compileall -q backend/app backend/tests/test_knowledge_index_foundation.py
PASS

npm run build
tsc && vite build
PASS

git diff --check
PASS
```

Warnings are existing FastAPI lifecycle/pytest configuration warnings and intentional provider fallback warnings; they are not failures.

## 11. P1 Regression

Pre-deployment online command:

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 300 --verbose --stop-on-fail
```

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 81.7 s |
| Trace | `p1-harness-20260714-155626-f878dd` |
| Health | P1-M24.3; PostgreSQL healthy |
| pgvector | Available; extension enabled |
| Vector sync | 37 chunks, 37 embeddings, 0 failures |
| Embedding | SiliconFlow, 1536 dimensions |
| Retrieval | `customerops_vector_retrieval`, no fallback |
| Bad Case | Feedback and draft creation passed |

The harness writes its documented test data. P2-M6 code does not import or call P1 retrieval/embedding paths.

## 12. Files Changed

Backend:

- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/knowledge_asset_repositories.py`
- `backend/app/knowledge_index_schemas.py`
- `backend/app/knowledge_index_repositories.py`
- `backend/app/knowledge_index_service.py`
- `backend/app/knowledge_index_routes.py`
- `backend/tests/test_knowledge_index_foundation.py`

Frontend:

- `frontend/src/types.ts`
- `frontend/src/pages/P2MaterialCenter.tsx`
- `frontend/src/styles.css`

Documentation:

- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/47_P2_M6_KNOWLEDGE_INDEX_FOUNDATION_REPORT.md`

## 13. Boundary Audit

- No P1 table, RAG row, schema contract, sync method, endpoint, embedding provider, or retrieval logic changed.
- No vector column/index, `p2_knowledge_embeddings`, Embedding call, similarity query, retrieval API, RRF, unified retrieval, or Agent use was added.
- M6 tables contain control state and plain text only.
- `serving` is reserved in the state machine but cannot be activated by any M6 public API.
- No dependency, environment variable, secret, uploaded binary, local database, tag, or force push is included.

## 14. P2-M7 Recommendation

P2-M7 should be a separately authorized **Text Bridge Semantic Index** stage:

1. write an ADR for P2-only embedding provider/model/dimension, pgvector DDL, profile/generation, cost, rollback, and SQLite testing;
2. add `p2_knowledge_embeddings`, never write P1 `rag_embeddings`;
3. index only `ready` entries whose Knowledge Asset remains active and fingerprint matches;
4. implement incremental/rebuild/withdraw tests plus a P2 text-bridge eval set;
5. decide when `ready -> serving` is legal;
6. keep CustomerOpsAgent and unified retrieval outside M7.

Until P2-M7 is explicitly approved, M6 entries and chunks remain non-vector and non-retrievable.
