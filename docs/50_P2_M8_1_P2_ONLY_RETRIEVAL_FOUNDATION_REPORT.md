# P2-M8.1 P2-only Retrieval Foundation Report

## 1. Completion Scope

P2-M8.1 adds an isolated retrieval plane for governed P2 text-bridge knowledge:

```text
active Knowledge Asset
  -> ready Index Entry + immutable Chunk
  -> immutable P2 Embedding build (Entry stays ready)
  -> explicit Serving Gate
  -> serving Index Entry
  -> P2-only cosine recall
  -> governance revalidation
  -> traced P2 evidence results
```

It does not implement unified retrieval, P1/P2 parallel recall, RRF, shadow mode, CustomerOpsAgent integration, answer generation, or a frontend retrieval page.

## 2. M7 Automatic Serving Correction

M7 originally persisted a complete embedding build and activated `ready -> serving` in the same transaction. That made vector construction itself the serving decision.

M8.1 separates the boundaries:

1. `POST /api/knowledge-index/{id}/embed` validates and persists all embedding rows.
2. The Index Entry remains `ready` with `sync_state=ready` and no build error.
3. `POST /api/knowledge-index/{id}/serve` performs a separate release gate.
4. Only a successful gate changes `ready -> serving`.
5. Existing serving rows are not automatically rolled back; repeated serve is idempotent.

This is the only intentional M7 behavior correction. P1 provider and retrieval behavior are untouched.

## 3. Explicit Serving Gate

Serve requires all of the following:

- Knowledge Asset exists and is `active`.
- Index Entry is `ready` or already `serving` for idempotent replay.
- `sync_state=ready` and `error_message` is empty.
- At least one governed Chunk exists.
- The current profile has exactly one complete embedding build covering every Chunk.
- Provider, model, dimension, and profile match the active query provider.
- Stored vector length equals the declared dimension.
- Embedding text, Chunk hash, Entry fingerprint, generation, and canonical SHA-256 embedding fingerprint match.
- Persisted trace equals the currently resolved Index -> Knowledge Asset -> Snapshot -> Review -> Extraction/Job -> Asset trace.
- The row set remains unchanged when activation is committed under a row lock.

Stable serve errors distinguish missing source, non-active source, illegal state, missing build, fingerprint mismatch, dimension mismatch, profile mismatch, sync failure, and invalid trace.

## 4. P2-only Retrieval API

### 4.1 Activation

```http
POST /api/knowledge-index/{index_entry_id}/serve
```

Returns Entry status, sync state, provider/model/dimension/profile, embedding count, activation/idempotency flag, and source trace.

### 4.2 Search

```http
POST /api/v2/retrieval/p2/search
```

Request:

```json
{
  "query": "How long is the DH-100 warranty?",
  "top_k": 5,
  "debug": false,
  "request_id": "optional-correlation-id"
}
```

Response data includes `retrieval_id`, `request_id`, `retrieval_mode=p2_vector_retrieval`, query, top_k, matched count, ranked results, provider/model/dimension/profile, latency, `fallback_used=false`, and a safe reason when empty or failed.

Each result contains rank, cosine similarity, Chunk/Entry/Knowledge Asset/Asset ids, text, content type, metadata, and complete source trace. Full vectors are never returned.

The unified `/api/v2/retrieval/search` route does not exist in M8.1.

## 5. Vector Query

PostgreSQL with pgvector uses:

```sql
1 - (p2_knowledge_embeddings.embedding <=> CAST(:query_vector AS vector))
```

Results are ordered by cosine distance. The SQL joins only P2 `knowledge_assets`, `p2_knowledge_index_entries`, `p2_knowledge_chunks`, and `p2_knowledge_embeddings` and filters active/serving/ready-sync ownership plus provider/model/dimension/profile and persisted Entry/Chunk fingerprints.

Query embedding uses the same provider contract and active P2 profile as the serving build. Incompatible profile or dimension fails closed. `P2_RETRIEVAL_MIN_SCORE` may override the conservative default relevance floor `0.45`; malformed values fail safely to the default.

SQLite tests decode the existing JSON vector and compute deterministic cosine locally. They use mock embeddings, no pgvector server, and no network.

No ANN index is added in M8.1. The dimension-flexible P2 column needs production corpus/query-plan evidence before profile-specific HNSW DDL is justified.

## 6. Double Governance Gate

Before query embedding/provider cost, the service inspects every candidate profile row and resolves the current trace. Repository recall then applies database status/ownership/profile filters. Before serialization, each selected result is resolved and validated again.

The second check closes archive/supersede races and rejects:

- ready but not serving;
- pending, building, failed, or archived Entry;
- non-active or superseded Knowledge Asset;
- missing/changed Chunk or Embedding;
- profile/dimension mismatch;
- stale Entry/Chunk/generation/embedding fingerprint;
- incomplete or inconsistent trace.

At most two chunks from one source Asset may enter a response. M8.1 performs no P1 fusion or RRF.

## 7. Safe Failure Contract

P2-only failures never fall back to P1. `retrieval_mode` remains `p2_vector_retrieval`, `fallback_used` remains false, and both request/retrieval ids are retained.

Stable reasons are:

- `no_serving_index`;
- `embedding_generation_failed`;
- `embedding_dimension_mismatch`;
- `embedding_profile_mismatch`;
- `pgvector_unavailable`;
- `pgvector_query_error`;
- `source_trace_invalid`;
- `fingerprint_mismatch`;
- `no_hits`.

`no_serving_index` and `no_hits` are valid empty responses. Provider and database failures return sanitized typed errors. API keys, URLs, `DATABASE_URL`, upstream bodies, stack traces, and vectors are not logged or returned.

## 8. Retrieval Logging

The existing `retrieval_logs` table has no P1 foreign key and already provides flexible `metadata_json`, so M8.1 reuses it without a schema change:

- id namespace: `p2_retrieval_*`;
- metadata namespace: `p2_retrieval_v1`;
- P1 write/read implementation is not modified;
- P2 does not expose these ids through the P1 trace endpoint.

Metadata records query/request ids, mode, top_k, counts, Chunk and Knowledge Asset ids, similarities, provider/model/dimension/profile, latency, fallback state/reason, safe trace summaries, and creation time. It never stores the query vector or secrets.

## 9. Archive Zero-recall Proof

The focused gate executes:

```text
active Asset lineage
  -> ready Entry
  -> Embedding build remains ready
  -> search: zero results
  -> explicit serve
  -> search: governed hit
  -> archive Entry or Knowledge Asset
  -> search: zero results
  -> physical p2_knowledge_embeddings row still exists
```

Separate tests cover explicit Entry archive, Knowledge Asset archive, automatic old-version archive during replacement, stale fingerprint, and missing trace. Because repository recall joins active Knowledge Asset and serving Entry, delayed vector cleanup cannot leak archived content.

## 10. P2 Eval

`samples/p2_rag_eval_queries.json` now contains 10 categories: product information, warranty, cancellation policy, Caption-derived knowledge, OCR-derived knowledge, metadata-derived knowledge, archived content, replaced version, no-answer, and semantic paraphrase.

`scripts/run_p2_rag_eval.py` calls only `/api/v2/retrieval/p2/search` and supports `--base-url`, `--top-k`, `--verbose`, and `--timeout`.

It reports total queries, expected-term coverage proxy (`hit_rate@k`), term-labeled query hit rate, exact-id candidate recall when stable labels exist, exact-id MRR, semantic mode count, no-hit count, archived leakage, duplicate Asset rate, top scores, average/p95 API latency, and failed queries.

The committed online fixture has no stable production-generated ids, so candidate recall and MRR must report `n/a`; keyword evidence is explicitly labeled as a proxy and is never promoted to formal recall.

Online results and the deployment gate outcome are recorded in Section 12.

## 11. Local Verification

| Gate | Result |
|---|---|
| M7/M8.1/Eval focused | 37 passed |
| M4/M6/M7/M8.1 regression | 51 passed |
| Full backend, clean worktree | 319 passed, 44 warnings, 129.05 s |
| `python -m compileall -q backend/app scripts` | PASS |
| Frontend `tsc && vite build` | PASS |
| `git diff --check` | PASS before deployment commit |

The direct workspace full run was stopped because ignored historical `backend/storage` caused a P1 test to rebuild vectors for the developer corpus. The authoritative clean worktree excludes `.env`, local DB, and ignored storage, matching M1–M7 release verification and completed all 319 tests.

## 12. Online P2 Smoke, Eval, and P1 Regression

The feature commit `bebf92c` deployed successfully. `/api/health` reports `phase=P1-M24.3`, `p2_phase=P2-M8.1`, PostgreSQL healthy, and pgvector available with extension creation successful.

### 12.1 P2 end-to-end smoke

The first operation, `POST /api/assets/upload`, failed closed with HTTP 503 and the safe code `ASSET_STORAGE_UNAVAILABLE`: the Render service does not have `ASSET_STORAGE_ROOT` configured for an attached persistent disk. This is the production gate defined by the P2-M1 storage ADR; writing to Render's ephemeral filesystem is intentionally prohibited.

The rejected upload created no Asset, so no `asset_id`, Extraction, Review, Snapshot, Knowledge Asset, Index Entry, Chunk, or P2 Embedding id exists for this attempted smoke. Consequently the online chain could not honestly proceed to a SiliconFlow build, ready-state search, explicit serve, serving hit, or archive search. No database row or binary object was inserted to manufacture a result, and no P1 endpoint was used as a substitute.

Result: the code is deployed, but the online P2 end-to-end smoke is **BLOCKED by Render storage deployment configuration**. Configure an attached persistent disk and an absolute root such as `ASSET_STORAGE_ROOT=/var/data/datahub-assets`, redeploy, and repeat the complete chain before M8.2.

### 12.2 P2 online Eval

The Eval ran against the deployed P2-only route with no serving corpus:

| Metric | Result |
|---|---:|
| total_queries | 10 |
| hit_rate@5 | 0.0 (expected-term coverage proxy, not recall) |
| query_hit_rate@5 | 0.0 |
| candidate_recall@5 | n/a (no stable expected ids) |
| MRR | n/a (no stable expected ids) |
| semantic_mode_count | 10 |
| no_hit_count | 10 |
| archived_leakage_count | 0 |
| duplicate_asset_rate | 0.0 |
| avg_top1_score | 0.0 |
| avg_top5_score | 0.0 |
| avg_latency_ms | 9.643 |
| p95_latency_ms | 48.596 |
| failed_queries | 0 |

All ten responses remained `p2_vector_retrieval`, never fell back to P1, and leaked no archived ids. However, `query_hit_rate@5=0.0` is below the required `0.75`; zero leakage alone is not a retrieval-quality pass. Formal recall and MRR remain unavailable because the committed fixture intentionally contains no environment-specific ids.

### 12.3 Sealed P1 regression

The first 30-second Harness attempt reached `/api/rag/build` and timed out after its first six PASS steps. Re-running the unchanged Harness with its supported `--timeout 120` option completed **10/10 PASS**:

- trace: `p1-harness-20260715-142112-c48ac6`;
- PostgreSQL healthy and pgvector available;
- vector sync: 41 Chunks and 41 Embeddings, SiliconFlow, 1536 dimensions;
- CustomerOpsAgent: `customerops_vector_retrieval`, `fallback_used=false`;
- Bad Case submission and draft creation: PASS.

This verifies that the deployed additive P2 route did not regress sealed P1 behavior. It does not override the blocked P2 smoke/Eval gate.

## 13. Known Boundaries

- P2 retrieval uses reviewed text bridge only; it is not image or multimodal embedding.
- No bulk serving, unserve API, queue, cache, ANN DDL, or hard-delete worker is included.
- The initial score floor requires continued eval calibration; it is route-local and is never compared with P1 scores.
- Profile migration history exists, but automated multi-generation rollout remains deferred.
- Reusing `retrieval_logs.metadata_json` is sufficient for M8.1 volume; shadow-scale retention/queryability must be re-evaluated in M8.2.
- Online stable expected ids are not available in the committed fixture, so formal recall/MRR may be `n/a`.
- The current Render service has no attached/configured Asset persistent disk. Until that deployment prerequisite is fixed, no online P2 serving corpus can be built through the governed public APIs.

## 14. Why Unified Retrieval Is Not Included

M8.1 proves the P2 route can independently enforce governance, retrieval quality, archive withdrawal, traceability, and rollback. Adding P1 fan-out before this proof would make P2 failures capable of degrading the sealed CustomerOpsAgent path.

Therefore this milestone adds no unified API, RRF, shadow traffic, feature-flag fan-out, CustomerOpsAgent change, or Agent answer generation.

## 15. Next Stage

The next proposed stage is **P2-M8.2 Unified Retrieval Shadow Gate**, only after:

- online P2 SiliconFlow smoke passes;
- archived leakage is exactly `0`;
- P2 Eval meets its proxy/latency/duplicate gates with honest recall labeling;
- P1 online Harness remains 10/10 vector retrieval with no fallback;
- the final worktree is clean and M8.1 is pushed;
- M8.2 receives separate explicit authorization.

Those gates are not yet all satisfied: the P1 gate and local implementation gates pass, but the online P2 smoke and retrieval-quality Eval remain blocked/failed. Therefore M8.2 is **not authorized** by this report.

## 16. P2-M8.1.1 Local Development Acceptance

P2-M8.1.1 subsequently executed the complete governed chain in a real local PostgreSQL/pgvector environment because the Render storage prerequisite in Section 12 remains unavailable. This section supplements rather than rewrites the historical online empty-corpus smoke and Eval values.

The accepted local trace is `p2-local-20260716-014332-34783c6a`. It used real `siliconflow` / `Qwen/Qwen3-Embedding-4B` embeddings at 1536 dimensions with profile `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536` and proved:

- embedding build leaves the Entry at `ready` with `sync_state=ready`;
- the target has zero recall before explicit serve;
- `POST /api/knowledge-index/{id}/serve` makes the governed target retrievable through `p2_vector_retrieval` with `fallback_used=false` and complete trace;
- archive removes the target immediately while the physical embedding row remains;
- a superseded old Knowledge Asset/version has zero recall.

The runtime-id manifest enabled formal local metrics:

| Metric | Local result |
|---|---:|
| total_queries | 12 |
| hit_rate@5 | 1.0 (keyword proxy) |
| query_hit_rate@5 | 1.0 |
| candidate_recall@5 | 1.0 over 10 positive id-labeled queries |
| MRR | 0.95 over 10 positive id-labeled queries |
| semantic_mode_count | 12 |
| no_hit_count | 2 |
| archived_leakage_count | 0 |
| duplicate_asset_rate | 0.0 |
| avg_top1_score | 0.712 |
| avg_top5_score | 0.6195 |
| avg_latency_ms | 2387.681 |
| p95_latency_ms | 2900.276 |
| failed_queries | 0 |

Retrieval-log inspection confirmed `p2_retrieval_*` ids, `p2_retrieval_v1` metadata, required result/profile/latency/trace fields, and no full vectors or secrets.

The sealed P1 Harness also passed locally 10/10 with trace `p1-harness-20260715-175644-34b47c`: PostgreSQL and pgvector were healthy, sync produced 2/2 SiliconFlow embeddings at 1536 dimensions with zero failures, CustomerOpsAgent remained `customerops_vector_retrieval` with no fallback, and Bad Case submit/draft passed.

Final M8.1.1 verification passed: the focused M4/M6/M7/M8.1 plus acceptance/Eval set passed 59/59, the authoritative clean-runtime full suite passed 327/327, Python compileall passed, and the frontend production build passed. Details and the clean-runtime rationale are recorded in `docs/51_P2_M8_1_LOCAL_ACCEPTANCE_CLOSURE.md`. Local M8.2 Shadow development/testing may proceed only under a separately authorized scope.

Status split:

- **M8.1 Development Acceptance: PASS** based on the real local governed chain and semantic retrieval evidence.
- **M8.1 Render Deployment Acceptance: BLOCKED** because Render still returns HTTP 503 `ASSET_STORAGE_UNAVAILABLE` without persistent Asset storage.

This local acceptance does not authorize online P2 retrieval, Render Shadow traffic, CustomerOpsAgent switching, or a claim that Render persistence has passed. Persistent Disk and S3/R2 adapters remain future deployment options and are not implemented here.
