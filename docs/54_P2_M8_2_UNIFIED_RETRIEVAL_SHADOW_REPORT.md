# P2-M8.2 Unified Retrieval Shadow Gate Report

## 1. Outcome and Acceptance Scope

P2-M8.2 adds an isolated, versioned Unified Retrieval control plane on top of the sealed P1 text index and the governed P2 text-bridge index. The implementation, focused/full automated regression, build, and real local Docker Shadow/Eval gates have passed. The implementation and acceptance phase is complete; only the final staged diff/security audit, phase commit, and push remain. No uncreated M8.2 commit hash is recorded.

This phase does **not** change the CustomerOpsAgent default path. The existing `POST /api/customer-ops-agent/retrieve` endpoint remains the P1 control and continues to report `customerops_vector_retrieval`. M8.2 does not write P2 content into P1 `rag_chunks` or `rag_embeddings`, does not replace the old endpoint, and does not enable Agent opt-in.

The authoritative development evidence is from the local Docker environment. Render Deployment Acceptance remains **BLOCKED** by the existing missing Persistent Disk and `ASSET_STORAGE_UNAVAILABLE`; no Docker result in this report is presented as Render online evidence.

## 2. Additive API Contract

M8.2 adds:

```text
POST /api/v2/retrieval/search
```

The request supports `query`, `top_k`, `sources` (`p1`, `p2`, or `all`), `fusion_enabled`, `shadow_mode`, `include_archived=false`, `debug`, and an optional `request_id`. Unknown fields and attempts to enable archived content are rejected by the versioned schema.

The response preserves:

- `retrieval_id`, `request_id`, `retrieval_mode`, `control_mode`, and `candidate_mode`;
- the visible `results`, P1 control evidence, and comparison-only candidate evidence;
- P1/P2/fused counts, source modes, source distribution, fallback state, and branch/fusion latency;
- route-local scores for diagnostics, fused rank scores, governed ids, and complete source trace;
- a Shadow comparison summary without returning any embedding vector.

In server-forced Shadow mode, the visible `results` are always the current P1 control. The unified candidate is retained only for comparison/Eval and cannot alter the control result delivered by this endpoint. The legacy P1 endpoint and CustomerOpsAgent are not invoked through a replacement contract.

## 3. Physical Boundary and Branch Execution

The architecture is **physical dual indexes plus logical late fusion**:

```text
Query
  |-- P1 adapter -> sealed P1 rag_chunks/rag_embeddings
  `-- P2 adapter -> governed P2 chunks/embeddings
                         |
                  rank-only RRF
                         |
              Shadow comparison candidate
```

Each adapter owns its source-specific query, eligibility rules, score interpretation, result normalization, and native retrieval id. P1 and P2 execute independently and in parallel through a process-wide bounded executor:

- shared worker pool: `8` workers;
- shared submission capacity: `16` branch tasks;
- per-request branch timeout default: `8` seconds;
- one branch error/timeout does not cancel a healthy branch;
- both branches unavailable produces a safe typed failure;
- fusion failure or one unavailable branch falls back to the available route with an explicit reason.

The bounded shared pool avoids creating an unbounded executor per request. Branch-failure isolation and fallback reasons are proven with deterministic injected unit tests. They are not misreported as a live HTTP infrastructure outage.

## 4. RRF and Deduplication

M8.2 implements Reciprocal Rank Fusion with default rank constant `k=60`:

```text
RRF(d) = sum(1 / (k + rank_route(d)))
```

Only route-local rank contributes to fused ordering. P1 and P2 cosine scores remain diagnostics in their original source context and are never compared or mixed across indexes.

Fusion applies the following controls:

- source-aware evidence identity deduplication;
- P2 Knowledge Asset/version-aware collapse through governed current-version eligibility;
- a default maximum of `2` returned P2 chunks per source Asset;
- deterministic tie handling based on route rank and stable governed ids;
- final P2 source-trace and serving-state revalidation before evidence can be returned.

The duplicate/quota behavior is proven through injected unit tests and the real Eval duplicate rate. It is not inferred only from a favorable corpus.

## 5. P2 Freshness and Archive Gate

The P2 adapter uses the existing repository eligibility gate and performs a fresh result-time governance check. Returned P2 evidence must still satisfy:

- Knowledge Asset status `active` and current version;
- Index Entry status `serving` and normal sync state;
- current Chunk/Embedding ownership and fingerprint;
- valid provider/model/dimension/profile;
- complete Asset -> Extraction -> Review -> Snapshot -> Knowledge Asset -> Index trace;
- no archived or superseded state.

Archive visibility is removed logically before asynchronous physical-vector cleanup. The real Docker Unified Eval labeled three forbidden archived/replaced cases by exact ids and returned none, so `archived_leakage_count=0` even though physical P2 embedding history can remain.

## 6. Feature Flags and Safe Defaults

M8.2 introduces these runtime flags, all defaulting to `false`:

- `UNIFIED_RETRIEVAL_ENABLED`
- `P2_RETRIEVAL_ENABLED`
- `UNIFIED_RETRIEVAL_SHADOW_MODE`

Operational parameters have bounded defaults:

- `UNIFIED_RETRIEVAL_BRANCH_TIMEOUT_SECONDS=8`
- `UNIFIED_RETRIEVAL_RRF_K=60`
- `UNIFIED_RETRIEVAL_P2_ASSET_CHUNK_QUOTA=2`

With Unified Retrieval disabled, the additive API fails closed and the old P1 endpoint is unaffected. With P2 disabled, no P2 branch is queried. Shadow requests require the Shadow flag; when Shadow is enabled the server forces P1 control visibility, regardless of a request attempting active candidate behavior. These flags provide immediate rollback without deleting indexes or rewriting the legacy endpoint.

The final default-off Docker check confirmed all three feature flags are `false`. A call to the additive Unified API returned HTTP 503 with its safe reason while retaining both `retrieval_id` and `request_id`; the sealed P1 endpoint remained available.

## 7. Retrieval Logging

M8.2 reuses `retrieval_logs.metadata_json` under the separate namespace `unified_retrieval_v1`. Unified records use `unified_retrieval_*` ids while preserving each branch's native retrieval id. The log contains:

- request/retrieval ids and safe query metadata;
- requested sources and Shadow state;
- P1/P2/fused counts and selected governed ids;
- branch state, latency, provider profile diagnostics, and fallback reason;
- source distribution and Shadow control/candidate comparison;
- source-trace summaries and rank-level evidence ids.

It does not contain complete vectors, API keys, `DATABASE_URL`, environment dumps, or internal exception stacks. No new observability table and no change to the P1 retrieval writer were required.

## 8. Unified Eval Design

The Docker Eval uses 11 scenarios covering P1-only knowledge, P2-only knowledge, mixed relevance, archived and replaced P2 versions, conflict/version behavior, no-answer behavior, duplicate Assets, and latency/source comparisons. Runtime expected ids are generated from the Docker corpus rather than hard-coded into the committed sample.

Exact-id recall and MRR are calculated only for queries with explicit labels. Keyword coverage remains a separate proxy and is never presented as formal recall. Archive leakage uses exact forbidden Knowledge Asset/Asset/Chunk ids. Branch-failure isolation and artificial duplicate pressure remain deterministic unit-test gates because no real branch outage was induced during the healthy Docker run.

## 9. Real Docker Shadow Eval Results

| Metric | Result |
|---|---:|
| total / successful queries | 11 / 11 |
| control keyword coverage | 0.3333 |
| control query hit rate | 0.4444 |
| candidate keyword coverage | 1.0 |
| candidate query hit rate | 1.0 |
| control exact recall | 0.0 over 7 labeled positives |
| candidate exact recall | 1.0 over 7 labeled positives |
| control MRR | 0.0 |
| candidate MRR | 0.6071 |
| source coverage | 1.0 over 9 applicable queries |
| candidate source distribution | P1 = 18, P2 = 21 |
| duplicate Asset rate | 0.0 |
| archived leakage | 0 across 3 exact-labeled forbidden queries |
| fallback count | 0 |
| Shadow responses / control violations | 11 / 0 |
| no-answer returned-result count | 2 |
| average latency | 478.579 ms |
| p50 / p95 latency | 390.858 / 1226.990 ms |
| average P1 / P2 branch latency | 370.848 / 370.794 ms |
| average fusion latency | 0.077 ms |
| failed queries | 0 |

The candidate improved the measured exact recall and keyword coverage without changing any visible control response. The observed p95 is recorded as the local Docker baseline; no arbitrary production SLO is inferred from a single small-corpus run.

The no-answer cases returned two low-confidence vector results. M8.2 has no calibrated refusal threshold, so this result is explicitly a known boundary and is not described as no-answer safety.

## 10. Independent P1 and P2 Gates

The pre-existing P2-only baseline remains:

- `candidate_recall@5=1.0`;
- `MRR=0.95`;
- `archived_leakage_count=0`;
- no P1 fallback.

The latest default-off sealed P1 Docker Harness passed 10/10 under trace `p1-harness-20260715-201239-f5d993`. PostgreSQL/pgvector, SiliconFlow embedding, P1 vector retrieval, Bad Case submit/draft, and the legacy `customerops_vector_retrieval` mode remained healthy; vector retrieval fallback remained `false`.

## 11. Compatibility and Rollback

- The old P1 retrieval endpoint remains available and unchanged.
- CustomerOpsAgent still defaults exclusively to P1.
- P1 and P2 physical tables remain isolated.
- Disabling `UNIFIED_RETRIEVAL_ENABLED` closes the additive API without touching P1.
- Disabling `P2_RETRIEVAL_ENABLED` removes P2 from the candidate branch.
- Disabling Shadow mode prevents Shadow execution; no default Agent cutover exists.
- Archive and version gates are enforced at query time even if vector cleanup lags.

## 12. Final Automated Gates and Git Closure

Final verification on the completed implementation produced:

- focused regression matrix: **81 passed**;
- final M8.2 targeted suite: **28 passed**, including the explicit no-fusion path without double-counting it into the 81-test matrix;
- authoritative clean-runtime backend suite: **365 passed**, 44 existing warnings, 251.11 seconds;
- Python compileall: **PASS**;
- frontend production build: **PASS**;
- `docker compose config`, image build, and healthy startup: **PASS**;
- default-off feature/API safety check: **PASS**;
- latest sealed P1 Harness: **10/10 PASS**;
- P2 exact baseline: recall 1.0, MRR 0.95, archive leakage 0.

M8.2 implementation and acceptance are therefore **COMPLETED**. The final diff/ignored-data/secret audit passed, commit `e0eb6b6 [P2-M8.2] feat: add unified retrieval shadow gate` was created, and `main` was pushed normally to `origin/main` without history rewriting.

M8.3 CustomerOpsAgent explicit opt-in began only after that Git closure. This outcome note does not alter the M8.2 Eval evidence above.

## 13. Boundaries and Deferred Work

M8.2 does not implement CustomerOpsAgent integration, default Unified cutover, native image embedding, CLIP, multimodal reranking, cloud object storage, Render Persistent Disk, P3, or P4. Render Deployment Acceptance remains blocked. The current system is a governed OCR/Caption/Metadata text bridge with physical dual-index Shadow retrieval, not native multimodal vector retrieval.
