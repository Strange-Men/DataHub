# P2-M7 Text Bridge Semantic Index Report

## 1. Completion Summary

P2-M7 Text Bridge Semantic Index is complete.

```text
active Knowledge Asset
  -> ready P2 Index Entry
  -> immutable p2_knowledge_chunks
  -> profile-aware text embedding
  -> immutable p2_knowledge_embeddings
  -> serving P2 Index Entry
```

This milestone creates semantic-index data and management APIs only. It adds no similarity-search API, unified retrieval, RRF, CustomerOpsAgent integration, image/multimodal embedding, P3, or P4 work. P1 remains sealed at `p1-m24.3-real-embedding-online-release`.

## 2. Architecture Decision

### 2.1 Physical isolation

P2 writes only `p2_knowledge_embeddings`. It never writes, deletes, rebuilds, or queries P1 `rag_chunks` or `rag_embeddings`. The existing `/api/customer-ops-agent/retrieve` route and `customerops_vector_retrieval` implementation are unchanged.

### 2.2 Provider reuse

P2 reuses the existing `EmbeddingProvider` contract and `get_embedding_provider()` resolver rather than creating a second HTTP client. The contract supports deterministic `mock` and OpenAI-compatible `siliconflow`, and exposes provider name, model name, and dimension as mandatory build metadata.

The current verified production profile is SiliconFlow model `Qwen/Qwen3-Embedding-4B`, dimension `1536`. Local tests explicitly select mock and require no secret or external call. `P2_EMBEDDING_PROFILE` is optional; when absent, P2 derives a stable profile from provider, model, and dimension.

### 2.3 Vector storage and future dimensions

PostgreSQL with pgvector stores P2 embeddings in an unconstrained `vector` column; SQLite stores compact JSON text for deterministic tests. Every row stores and validates its explicit dimension.

- P1 keeps its frozen `Vector(1536)` column unchanged.
- A future P2 model with a different dimension creates a new profile and historical row instead of rewriting prior vectors.
- M7 creates no ANN/HNSW/IVFFlat index because no retrieval API exists yet.
- M8 must select one serving profile/dimension and define a profile-specific vector index before exposing retrieval.

### 2.4 Cost, rollback, and migration

- Build scope is one ready Index Entry per management request; no bulk backfill or queue is introduced.
- Fingerprint replay is a no-op and avoids duplicate provider cost.
- Provider/model upgrades require a new profile and ready generation; historical rows remain immutable.
- Rollback is additive: stop calling the M7 APIs and keep entries at ready/archived. P1 is independent.
- Hard deletion and cross-profile rebuild are deferred. Archive immediately removes serving eligibility while retaining audit rows.

## 3. Data Model

M7 adds one table: `p2_knowledge_embeddings`.

| Field | Responsibility |
|---|---|
| `id` | Stable content-derived P2 embedding id |
| `index_entry_id` | Owning P2 Index Entry |
| `chunk_id` | Immutable governed Chunk source |
| `knowledge_asset_id` | Direct governance source reference |
| `chunk_text` | Exact text snapshot embedded by the provider |
| `embedding` | pgvector value on PostgreSQL; JSON text on SQLite |
| `provider` | Provider actually used, such as `mock` or `siliconflow` |
| `model` | Model actually used |
| `dimension` | Declared and validated vector length |
| `embedding_profile` | Provider/model/dimension generation boundary |
| `fingerprint` | Canonical SHA-256 build identity |
| `metadata_json` | Bridge/index versions, chunk hash, index fingerprint, and persisted source trace |
| `created_at` | Immutable creation time |

Each embedding row belongs to exactly one Chunk. A Chunk may retain multiple historical rows across profiles/fingerprints; unique `(chunk_id, embedding_profile, fingerprint)` prevents duplicate builds without destroying model-upgrade history. `fingerprint` is also globally unique.

The persisted trace snapshot contains:

```text
Embedding
  -> Chunk / Index Entry
  -> Knowledge Asset / version
  -> Snapshot / version
  -> Review / status / version
  -> Extraction / Job / type / version
  -> Asset / file name / hash / status
```

Management responses re-resolve the canonical M6/M4 trace and reject missing or inconsistent lineage rather than trusting metadata alone.

## 4. Text Bridge Service and Lifecycle

`P2KnowledgeEmbeddingService` enforces:

1. Index Entry exists and its complete trace resolves.
2. Source Knowledge Asset still has `status=active`.
3. The Entry has governed chunks.
4. Provider, model, and declared dimension are valid.
5. Existing fingerprints are checked before any provider call.
6. New generation is allowed only while Entry status is `ready`.
7. `embed_batch()` result count and every vector dimension match the contract.
8. All embedding rows and `ready -> serving` are committed atomically.

For an Entry already in `serving`, exact fingerprint replay returns existing rows with `created_count=0`; it does not call the provider. A changed profile/fingerprint requires a separately prepared ready generation. Archived, building, failed, or otherwise non-ready entries cannot generate vectors.

Provider exceptions become the safe message `Embedding provider call failed.` in the existing P2 Index Entry `error_message`. Raw upstream messages, credentials, and URLs are not persisted or returned. Dimension mismatch is also persisted safely, leaves the Entry ready for correction, and writes no partial embedding row.

## 5. Fingerprint and Idempotency

The canonical SHA-256 fingerprint includes:

```text
p2_text_bridge_embedding_v1
chunk_id
chunk_hash
chunk_text
index generation
provider
model
dimension
embedding_profile
```

- Same input/profile: skip, no provider cost, no duplicate row.
- Changed model/profile: new immutable history after a new ready generation.
- Changed governed content: M4/M6 create a new Knowledge Asset/Entry/Chunk lineage.
- Failure before persistence: no partial row; Entry remains ready with a safe last error.
- Success: rows and serving activation become visible together.

## 6. Management API

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/knowledge-index/{id}/embed` | Active/ready-only build; exact serving replay is idempotent |
| `GET` | `/api/knowledge-embeddings` | Paginated metadata with Entry, Knowledge Asset, provider, and profile filters |

The list omits the full vector payload. It returns provider, model, dimension, profile, fingerprint, text snapshot, and complete source trace, preventing the management API from becoming an accidental retrieval surface.

Stable errors include `KNOWLEDGE_INDEX_NOT_FOUND`, `KNOWLEDGE_ASSET_NOT_ACTIVE`, `KNOWLEDGE_INDEX_NOT_READY`, `KNOWLEDGE_EMBEDDING_SOURCE_INVALID`, `KNOWLEDGE_EMBEDDING_PROVIDER_FAILED`, and `KNOWLEDGE_EMBEDDING_DIMENSION_MISMATCH`.

No `/search`, `/retrieve`, score, top-k, or Agent endpoint is added.

## 7. P2 Eval and Semantic Smoke

`samples/p2_rag_eval_queries.json` contains offline fixtures for product knowledge, policy knowledge, FAQ, version replacement, archive exclusion, and Caption text bridge. It is explicitly marked `offline-eval-fixtures-only-no-retrieval-api`; M7 claims no retrieval metric.

The deterministic semantic smoke verifies generation, stored vector length, provider/model metadata, serving transition, and complete source trace. Additional tests cover active/ready gates, replay idempotency, historical profiles, provider failure, dimension mismatch, management listing, and eval categories.

## 8. Verification

Focused P2-M7 tests:

```text
python -m pytest -q backend/tests/test_p2_text_bridge_semantic_index.py
9 passed
```

M4/M6/M7 focused regression:

```text
23 passed
```

The first clean full run exposed one legacy P1-M15 route-surface assertion that rejected every route containing `embedding`. It was narrowed only to allow the authorized P2 management path `/api/knowledge-embeddings`; the P1 release-flow test then passed independently.

Authoritative full clean-workspace suite:

```text
python -m pytest -q backend/tests
291 passed, 40 warnings in 262.20s
```

The clean clone excludes ignored developer `.env`, local databases, and historical `backend/storage`, matching the established M1-M6 method. Warnings are existing FastAPI lifecycle/pytest configuration warnings and intentional provider-fallback warnings.

Additional gates:

```text
python -m compileall -q backend/app backend/tests
PASS

npm run build
tsc && vite build
PASS

git diff --check
PASS
```

No frontend source changed in M7; the production build verifies compatibility.

## 9. P1 Regression

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 300 --verbose --stop-on-fail
```

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 83.2 s |
| Trace | `p1-harness-20260715-093458-fb44aa` |
| Health | P1-M24.3; PostgreSQL healthy |
| pgvector | Available; extension enabled |
| P1 vector sync | 39 chunks, 39 embeddings, 0 failures |
| P1 provider | SiliconFlow, 1536 dimensions |
| P1 retrieval | `customerops_vector_retrieval`, no fallback |
| Bad Case | Feedback and draft creation passed |

This validates deployed sealed P1. The new P2 table/API was not deployed during this gate, so this report does not claim a production P2 SiliconFlow build.

## 10. Files Changed

- `.env.example`
- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/knowledge_embedding_schemas.py`
- `backend/app/knowledge_embedding_repositories.py`
- `backend/app/knowledge_embedding_service.py`
- `backend/app/knowledge_embedding_routes.py`
- `backend/tests/test_p2_text_bridge_semantic_index.py`
- `backend/tests/test_p1_high_quality_datahub_release.py` (P2 route compatibility only)
- `samples/p2_rag_eval_queries.json`
- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/48_P2_M7_TEXT_BRIDGE_SEMANTIC_INDEX_REPORT.md`

## 11. Boundary Audit

- No change to P1 `rag_chunks`, `rag_embeddings`, repositories, sync/build, or schema.
- No change to `/api/customer-ops-agent/retrieve`, its result contract, vector query, fallback, or Agent behavior.
- No P1/P2 unified retrieval, RRF, score normalization, query fan-out, or retrieval API.
- No image/multimodal embedding, OCR/Caption provider, Vision LLM, P3, or P4 work.
- No full vector is returned by a management response.
- No ANN index, bulk backfill, queue, hard delete, tag, secret, `.env`, database, or uploaded binary is committed.

## 12. P2-M8 Recommendation

M8 may enter a separately authorized **Unified Retrieval Planning Gate**, not direct implementation. Before any query endpoint or CustomerOpsAgent change it must decide P2 serving-profile/index DDL, active/archive query filters, P2-only retrieval eval, Asset deduplication, P1/P2 score non-comparability, additive versioned API, shadow mode, latency/partial-failure budget, and rollback.

M7 completion authorizes planning only. It does not authorize unified retrieval, RRF, Agent integration, or multimodal embedding.

## 13. P2-M8.1 Serving Boundary Clarification

This is an additive historical clarification; the M7 evidence above is not rewritten.

M7 originally committed embedding rows and changed the Index Entry from `ready` to `serving` in the same operation. P2-M8.1 separated those responsibilities: a successful embedding build now leaves the Entry at `ready`, and only the explicit `POST /api/knowledge-index/{id}/serve` gate may activate `serving` after validating the active Knowledge Asset, Chunk coverage, current profile/provider/model/dimension, exact embedding fingerprint, synchronization state, and complete source trace. Existing `serving` rows are not automatically rolled back.
