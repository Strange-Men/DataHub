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

Online results are recorded in Section 12 after deployment.

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

Pending deployment of the feature commit. This section will be updated with real ids, SiliconFlow profile, ready/serve/archive results, Eval metrics, and the P1 Harness trace after the Render deployment is verified.

## 13. Known Boundaries

- P2 retrieval uses reviewed text bridge only; it is not image or multimodal embedding.
- No bulk serving, unserve API, queue, cache, ANN DDL, or hard-delete worker is included.
- The initial score floor requires continued eval calibration; it is route-local and is never compared with P1 scores.
- Profile migration history exists, but automated multi-generation rollout remains deferred.
- Reusing `retrieval_logs.metadata_json` is sufficient for M8.1 volume; shadow-scale retention/queryability must be re-evaluated in M8.2.
- Online stable expected ids are not available in the committed fixture, so formal recall/MRR may be `n/a`.

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
