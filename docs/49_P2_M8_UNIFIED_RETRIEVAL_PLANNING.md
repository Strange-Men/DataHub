# P2-M8 Unified Retrieval Planning Gate

## 1. Decision Summary

P2-M8 is a documentation-only architecture gate. It does not implement retrieval, change a database schema, modify the frontend, or connect P2 to CustomerOpsAgent.

The final recommendation is:

```text
User Query
  -> POST /api/v2/retrieval/search
     -> P1 adapter -> sealed P1 text retrieval
     -> P2 adapter -> governed P2 knowledge retrieval
  -> route-local eligibility and deduplication
  -> rank-level RRF late fusion
  -> unified evidence results with complete source trace
  -> future CustomerOpsAgent explicit opt-in only
```

The physical indexes remain separate. The logical retrieval contract is additive and versioned. P1 remains the control and permanent rollback path.

The implementation sequence is fixed to three stages:

1. **P2-M8.1 P2-only Retrieval Foundation**
2. **P2-M8.2 Unified Retrieval Shadow Gate**
3. **P2-M8.3 CustomerOpsAgent Opt-in Integration**

No stage may be skipped.

## 2. Current State and Audit Findings

### 2.1 P1 sealed retrieval plane

P1 remains sealed at `p1-m24.3-real-embedding-online-release`.

| Component | Current responsibility |
|---|---|
| `rag_chunks` | Reviewed P1 customer-service text chunks |
| `rag_embeddings` | P1 vector rows with fixed PostgreSQL `Vector(1536)` |
| Embedding profile | SiliconFlow `Qwen/Qwen3-Embedding-4B`, 1536 dimensions |
| `customerops_vector_retrieval` | Existing semantic mode used by CustomerOpsAgent |
| `POST /api/customer-ops-agent/retrieve` | Stable P1-only endpoint and response contract |
| `retrieval_logs` | Existing P1 trace/log record with extensible `metadata_json` |

The current P1 repository performs pgvector cosine search over `rag_embeddings`. The existing CustomerOpsAgent contract has P1-specific filters, result fields, retrieval modes, keyword fallback, and trace lookup. P2 must not write these tables or modify this behavior.

### 2.2 P2 governed semantic plane

| Component | Current responsibility |
|---|---|
| `knowledge_assets` | Approved, versioned, active/archived governed content |
| `p2_knowledge_index_entries` | P2 index lifecycle, generation, fingerprint, and sync state |
| `p2_knowledge_chunks` | Immutable deterministic text projection |
| `p2_knowledge_embeddings` | Profile-versioned P2 text-bridge vectors and text snapshots |

P2 currently has build and management APIs only. It has no P2 search API, no unified retrieval API, and no CustomerOpsAgent integration.

P2 embedding records retain `index_entry_id`, `chunk_id`, `knowledge_asset_id`, provider, model, dimension, `embedding_profile`, fingerprint, and the full trace:

```text
P2 Embedding
  -> Chunk / Index Entry
  -> Knowledge Asset / version
  -> Snapshot / version
  -> Review / status / version
  -> Extraction / Job / type / version
  -> Asset / file name / hash / status
```

The current DataHub production-verified provider profile is SiliconFlow `Qwen/Qwen3-Embedding-4B` at 1536 dimensions. M7 reuses that provider configuration, but its report correctly makes no claim that a production P2 vector build has been deployed. P2 deliberately stores profile and dimension per row and does not assume that future P2 profiles equal P1.

### 2.3 Serving audit note

M7 atomically changes an Index Entry from `ready` to `serving` after a complete, dimension-valid embedding build. Because P2 has no retrieval API, this status currently creates no external search visibility.

For M8, `status=serving` is necessary but not sufficient. Retrieval eligibility also requires the active release profile, current fingerprint, healthy sync state, complete trace, active Knowledge Asset, and archive exclusion. This separates **technical vector completion** from **release-approved retrieval visibility**.

The audit also found that immutable historical embedding rows support model history, while an operational same-asset profile rebuild/activation path is not yet implemented. M8 does not repair this. M8.1 must review generation/profile switching before any alternate profile can serve.

### 2.4 P2-M7 publication status

Local commit `02bc72bd67d10a299bf0b73a289c522424bb0c9d` (`[P2-M7] feat: add text bridge semantic index`) was pushed to `origin/main` before this planning work. No force push, rebase, or history rewrite was used.

## 3. Architecture Alternatives and Final Choice

### 3.1 Option A: independent dual recall plus RRF late fusion — selected

P1 and P2 generate route-local candidates independently. A logical coordinator applies each route's own eligibility rules, preserves original ranks and scores for diagnostics, then combines ranks with Reciprocal Rank Fusion (RRF).

Advantages:

- Preserves the sealed P1 schema, endpoint, embedding profile, and fallback behavior.
- Lets P2 enforce governance, versioning, archive, and source trace independently.
- Supports different provider/model/dimension profiles without cross-index score comparison.
- Allows independent timeouts, feature flags, shadow verification, and rollback.
- Makes P2-only evaluation possible before any fusion or Agent exposure.

Costs:

- Two query embeddings may be required when profiles differ.
- Parallel fan-out, deduplication, fusion, and observability add latency and operational complexity.
- Rank-level fusion requires a labeled evaluation set; it cannot be tuned by intuition.

**Decision:** adopt physical dual indexes plus a logical versioned retrieval layer and rank-level RRF late fusion.

### 3.2 Option B: one unified vector table — rejected

A unified table would mix P1 and P2 lifecycle rules, source traces, versions, dimensions, and rollback boundaries. It would require changing or migrating the sealed P1 data path and would make profile upgrades and P2 withdrawal capable of affecting P1.

**Decision:** reject. P2 content must never be written to P1 `rag_embeddings`, and no unified vector table is planned for P2.

### 3.3 Option C: query router followed by one recall route — rejected as the default

A classifier/router can reduce cost and latency, but routing errors silently suppress relevant evidence from the other source. It also creates a new model and evaluation dependency before the P2 corpus has retrieval evidence.

**Decision:** do not use query routing as the default fusion architecture. Explicit caller source selection remains supported. Learned routing may be reviewed later as an optimization only after shadow logs and labeled route-error metrics exist.

## 4. Additive API Contract

### 4.1 Path and compatibility

The planned contract is:

```http
POST /api/v2/retrieval/search
```

It is additive and versioned because its evidence types, partial-failure semantics, and trace are materially different from the P1 CustomerOpsAgent response.

The existing `POST /api/customer-ops-agent/retrieve` remains P1-only and is never replaced during P2. No field, mode, fallback, authentication behavior, or response shape is changed.

M8.1 may expose the versioned endpoint in restricted `sources=["p2"]` mode only. P1/P2 fan-out is not enabled until M8.2.

### 4.2 Request design

```json
{
  "query": "How long is the warranty for SKU-100?",
  "top_k": 5,
  "sources": ["p1", "p2"],
  "fusion_enabled": true,
  "include_archived": false,
  "debug": false,
  "request_id": "optional-client-correlation-id"
}
```

| Field | Contract |
|---|---|
| `query` | Required non-empty text; proposed maximum 500 characters to align with P1 initially |
| `top_k` | Default 5; proposed range 1–20 |
| `sources` | `p1`, `p2`, or both; default both only after M8.2 is enabled |
| `fusion_enabled` | Uses RRF when both sources are active; when false, P1 remains the control result in shadow/rollback mode |
| `include_archived` | Search contract accepts `false` only; `true` is rejected rather than treated as an admin bypass |
| `debug` | Adds route-local diagnostics for authorized callers; never exposes full vectors or secrets |
| `request_id` | Optional caller correlation id; server still creates a unique `retrieval_id` |

If one source is selected, results are returned in that source's route-local order and no cross-source fusion is performed. If both sources are selected with fusion disabled, P1 is the deterministic production/control result; P2 may run only as non-impacting shadow work.

### 4.3 Response design

```json
{
  "retrieval_id": "unified_retrieval_...",
  "request_id": "optional-client-correlation-id",
  "retrieval_mode": "unified_rrf",
  "source_modes": {
    "p1": {"mode": "customerops_vector_retrieval", "status": "ok", "result_count": 20},
    "p2": {"mode": "p2_vector_retrieval", "status": "ok", "result_count": 20}
  },
  "results": [
    {
      "source_type": "p2_knowledge_asset",
      "source_index": "p2",
      "rank": 1,
      "fused_score": 0.03252,
      "original_rank": 1,
      "original_score": 0.78,
      "candidate_id": null,
      "knowledge_asset_id": "knowledge_asset_...",
      "chunk_id": "p2_chunk_...",
      "evidence_text": "...",
      "source_trace": {}
    }
  ],
  "fallback_used": false,
  "fallback_reason": null,
  "partial": false,
  "latency_ms": {"total": 210, "p1": 170, "p2": 185, "fusion": 2}
}
```

Required response semantics:

- `retrieval_id` is server generated and uses a namespace distinct from P1 retrieval ids.
- `retrieval_mode` distinguishes `p1_only`, `p2_only`, `unified_rrf`, `partial_p1`, `partial_p2`, and `shadow_control`.
- `source_modes` records route status, route-specific retrieval mode, candidate count, profile where applicable, and latency.
- `fused_score` is an RRF score only. It is `null` for an unfused single route.
- `original_score` is route-local diagnostic evidence and must never be compared across P1/P2.
- P1 results carry `candidate_id`; P2 results carry `knowledge_asset_id`. Both carry `chunk_id` and their complete native trace.
- `fallback_used`, `fallback_reason`, `partial`, and latency breakdown make degradation explicit.
- Debug data is opt-in and sanitized. Full vectors, provider credentials, upstream error bodies, and storage URLs are excluded.

## 5. RRF and Candidate Policy

### 5.1 Formula

For a logical evidence item `d` returned by route `i`:

```text
RRF(d) = sum over contributing routes i of w_i / (k0 + rank_i(d))
```

Initial recommendation:

- Rank constant `k0 = 60`.
- Initial weights `w_p1 = 1.0`, `w_p2 = 1.0`.
- Weight changes require labeled eval evidence and a recorded decision; they are not runtime caller controls.
- Raw cosine values are retained only as route-local diagnostics.

P1 and P2 may use the same provider today, but the fusion design must behave correctly when their profiles or dimensions differ. Each route generates its own query embedding and performs its own calibrated thresholding. Only ranks cross the fusion boundary.

### 5.2 Candidate depth and final top-k

For requested `top_k = K`:

- Validate `1 <= K <= 20`.
- Each enabled route recalls `candidate_k = min(max(4 * K, 20), 50)` candidates.
- Each route applies its own eligibility filter, route-specific relevance floor, and deduplication before fusion.
- RRF operates on the remaining route-ranked candidates.
- The final response returns at most `K` items.

The initial `4x` depth is a planning default, not a hard-coded truth. M8.1 and M8.2 eval must measure recall, latency, and dedup loss before release.

### 5.3 Identity, versions, chunks, and diversity

- P1 identity is based on the governed P1 `candidate_id`/chunk lineage.
- P2 identity is based on the current `knowledge_asset_id`, with Asset/version lineage preserved.
- P2 keeps only the current active version for one `(asset_id, content_type)` family. Archived/superseded versions are filtered before fusion.
- At most one result per P2 Knowledge Asset is returned by default.
- At most two P2 chunks from one underlying Asset may enter the final list when future chunking produces independently useful evidence.
- Cross-index records are not merged merely because cosine scores or loose text similarity look alike. Exact normalized-text hash collapse may be evaluated later, but both source traces must be retained.
- When both routes have at least one candidate above their own calibrated relevance floor and `K >= 2`, a soft diversity guard reserves up to one slot for each route. It does not admit a route candidate that failed its own floor. This rule must pass shadow eval before activation.
- No-answer queries must be allowed to return an empty result rather than using a diversity rule to force weak evidence.

### 5.4 Partial failure

- P2 timeout/failure with healthy P1: return P1 results, mode `partial_p1`, and record the P2 reason.
- P1 timeout/failure with healthy P2: the new versioned API may return P2-only evidence, mode `partial_p2`, when the request included P2. A future Agent does not use this degraded behavior unless it explicitly opts in; its safe default remains the old P1 endpoint.
- Fusion failure with healthy P1: return P1 control results. If only P2 is healthy, return P2-only partial results.
- Both routes failed: return a typed 503 response with the same `retrieval_id` and sanitized route errors.
- A route returning zero eligible hits is not a system failure; the other route may return normally and the zero-hit reason is recorded.

## 6. P2 Serving and Governance Gate

### 6.1 Query-time predicate

A P2 vector is eligible only when all conditions are true at query time:

1. `knowledge_asset.status = active`.
2. `p2_knowledge_index_entries.status = serving`.
3. `sync_state = ready`, with no unresolved build failure.
4. The Entry fingerprint matches the current governed Knowledge Asset projection.
5. The Embedding fingerprint matches its Chunk, generation, provider/model/dimension, and selected profile.
6. `embedding_profile` is the deployment's eval-approved active P2 serving profile.
7. Stored `dimension` equals the selected profile's required dimension.
8. The complete Embedding -> Chunk/Entry -> Knowledge Asset -> Snapshot -> Review -> Extraction/Job -> Asset trace resolves and is internally consistent.
9. Neither the Knowledge Asset nor Index Entry is archived.

These checks must be enforced in the database candidate query where possible and revalidated before response serialization. A vector's physical existence never grants visibility.

### 6.2 `ready -> serving` activation

The target activation sequence is:

```text
ready projection
  -> build every vector for the current fingerprint/profile
  -> validate count, dimension, provider/model/profile, and complete trace
  -> commit vectors and ready -> serving atomically
  -> pass P2-only eval for that profile
  -> activate the profile in deployment configuration
  -> enable P2 retrieval feature flag
```

M7 already implements the atomic technical transition for its current build. M8.1 must add the retrieval-side profile allowlist and eval/release gate. This planning stage adds no activation API or configuration.

The initial M8.1 serving candidate is the derived profile `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536`. It is a candidate because it matches the verified DataHub provider/model/dimension; it does not become the active P2 retrieval profile until a real P2 build passes the M8.1 eval, query-plan, latency, and archive-zero-recall gates.

A profile upgrade must build and evaluate a new generation without overwriting historical vectors, then atomically switch the active serving profile. The missing operational rebuild path identified in the audit must be resolved in M8.1 before alternate-profile serving.

### 6.3 Profile-specific vector index

P2's PostgreSQL vector column is dimension-flexible, so M8.1 must review a profile/dimension-specific pgvector index before production search. The likely design is a partial/expression HNSW index for the selected profile and dimension, but exact DDL, operator class, query plan, rollback, and Render support require a separate implementation review. No DDL is authorized by this document.

### 6.4 Archive zero-recall rule

Archive is a logical visibility transaction, not a physical-delete dependency:

1. Archive/supersede first changes the Knowledge Asset and Index Entry out of eligible state.
2. Every P2 search joins or validates the active Knowledge Asset and serving Entry; it never searches `p2_knowledge_embeddings` alone.
3. Candidate rows are rechecked after vector recall and before serialization to close race windows.
4. Retrieval caches are disabled initially or keyed/invalidation-aware by status, generation, fingerprint, and profile.
5. Background vector cleanup may lag, but archived vectors remain unreachable.
6. `include_archived=true` is forbidden on the retrieval contract; audit/admin visibility stays on management APIs.

Release requires archived leakage rate exactly `0` under normal, concurrent archive, stale-vector, and cached-candidate tests.

## 7. Shadow Validation and CustomerOpsAgent Opt-in

Unified retrieval must not replace P1 directly.

### Phase 1: P2-only validation

- Implement only the P2 adapter and restricted P2-only query mode.
- Prove serving/profile/dimension gates, archive zero recall, trace completeness, version handling, deduplication, no-answer behavior, and latency.
- Keep P1 and CustomerOpsAgent untouched.

### Phase 2: P1/P2 shadow

- The sealed P1 result remains the control returned to callers.
- P1 and P2 run in parallel only when shadow and feature flags permit.
- RRF candidate output is computed and logged as the candidate, not used by CustomerOpsAgent.
- Compare hit rate, source diversity, latency, fallback, archived leakage, duplicates, and result movement by retrieval id.
- Inject route timeout, provider/profile mismatch, fusion failure, and archive races.

### Phase 3: explicit Agent opt-in

- Only after P2-only and shadow release gates pass may M8.3 add an explicit CustomerOpsAgent opt-in.
- Default Agent behavior remains the old P1 endpoint.
- Opt-in must be reversible without migration or data rewrite.
- A failed unified call falls back to the old P1 path by policy; P2-only degraded answering requires a second explicit policy decision.
- Default switching is a future release decision after production smoke evidence, not part of M8.3 completion by default.

## 8. Eval Dataset and Release Gates

### 8.1 Dataset partitions

The unified eval corpus must be separate from the M7 build smoke fixtures and contain labeled expected evidence/source/version outcomes for:

- P1-only customer-service queries.
- P2-only product, policy, FAQ, SKU, OCR, and Caption-derived queries.
- Queries for which both P1 and P2 are relevant.
- Archived Knowledge Asset queries.
- Conflicting old/new version queries.
- No-answer queries.
- Route timeout/provider failure/fusion failure cases for deterministic degradation tests.

### 8.2 Required metrics

- P1 recall@k.
- P2 recall@k.
- Fused recall@k.
- Mean Reciprocal Rank (MRR).
- Expected-source coverage.
- Archived leakage rate.
- Duplicate Asset rate.
- Fallback/partial-response rate and reason distribution.
- Warm p50 and p95 total/P1/P2/fusion latency.
- P1 regression delta against the sealed control.
- Source-trace completeness and no-answer false-positive rate.

### 8.3 Recommended release thresholds

Thresholds must be frozen against the first reviewed dataset in M8.1. Initial recommendations are:

| Gate | Recommended threshold |
|---|---|
| P1 Harness | 10/10 on every implementation stage |
| P1 contract/API regression | 0 changed fields/modes/behavior in the old endpoint |
| P1-only recall@5 delta | No worse than -0.02 absolute vs sealed control |
| P1-only MRR delta | No worse than -0.02 absolute vs sealed control |
| P2-only recall@5 | At least 0.80 overall; no reviewed category below 0.70 |
| Mixed fused recall@5 | At least best single route minus 0.01, and at least +0.05 over P1 control on the mixed subset |
| Expected-source coverage | At least 0.80 on mixed queries |
| Archived leakage | Exactly 0 |
| Source trace completeness | 100% of returned results |
| Duplicate Asset rate | At most 0.05 after the declared quota policy |
| Unexpected fallback rate | At most 0.01 outside injected-failure cases |
| Injected failure degradation | 100% follows the declared partial/fallback contract |
| Latency | Warm p50 <= P1 control × 1.25 + 100 ms; p95 <= P1 control × 1.5 + 250 ms |
| No-answer false-positive rate | No worse than P1 control; absolute target frozen in M8.1 |

If the dataset is too small for stable rates, the gate remains blocked; thresholds are not relaxed solely to ship.

## 9. Rollback, Feature Flags, and Fault Isolation

Planned flags:

- `UNIFIED_RETRIEVAL_ENABLED`
- `P2_RETRIEVAL_ENABLED`
- `UNIFIED_RETRIEVAL_SHADOW_MODE`

They are planning names only; no environment file or code is changed in M8.

Rollback order:

1. Disable `UNIFIED_RETRIEVAL_ENABLED`; new callers use the declared single-route fallback.
2. Disable `P2_RETRIEVAL_ENABLED`; P1 remains available.
3. Keep or enable shadow mode only when it is safe to collect non-impacting evidence.
4. CustomerOpsAgent continues or returns to its old P1 endpoint without schema/data rollback.

Fault rules:

- P2 timeout -> P1-only partial response.
- P1 timeout -> P2-only partial response in the new API only; future Agent use requires explicit degraded-mode authorization.
- Fusion exception -> P1 control when available, otherwise the healthy single route.
- Invalid P2 profile/dimension -> reject P2 serving and record a safe reason.
- P2 index anomaly or archive leak -> immediately disable the P2 flag.
- Unified API failure -> old P1 endpoint remains independently callable and behaviorally unchanged.

## 10. Observability and Log Storage

Every active or shadow retrieval must record at minimum:

- `retrieval_id` and caller `request_id`.
- P1, P2, fusion, and total latency.
- P1/P2 requested and eligible result counts.
- Route mode/status and selected serving profile.
- Fallback/partial reason.
- Final source distribution.
- Selected P1 candidate ids, P2 Knowledge Asset ids, and chunk ids.
- Deduplication and quota actions.
- Shadow control/candidate comparison summary.
- Archive/profile/trace rejection counters.

The first choice is to reuse the existing `retrieval_logs` common columns and namespaced `metadata_json`, with a distinct `unified_retrieval_*` id namespace. Before doing so, M8.1 must prove that the P1 trace reader and retention behavior cannot misinterpret unified records. If compatibility cannot be preserved without changing the old P1 contract, use structured application logs for M8.1 and review a minimal additive retrieval-event table no earlier than M8.2.

No new table is required or authorized by this planning gate. A table decision is evidence-driven by shadow volume, queryability, retention, and P1-reader compatibility—not assumed in advance.

## 11. Three-Stage Implementation Roadmap

### P2-M8.1: P2-only Retrieval Foundation

- Implement the P2 retriever against the existing P2 tables only.
- Initially expose `POST /api/v2/retrieval/search` only for `sources=["p2"]`.
- Select one serving profile and validate query dimension/profile compatibility.
- Review and, only with explicit authorization, add the dimension/profile-specific pgvector index.
- Resolve the alternate-profile generation/activation lifecycle noted by the audit.
- Enforce active/serving/sync/fingerprint/trace/archive gates twice.
- Add P2 eval, deduplication, no-answer, archive-race, latency, and rollback tests.
- Run full repository tests, frontend build, and P1 Harness 10/10.

Exit: P2-only eval and archive-zero-recall gates pass. No P1 fan-out, fusion, or Agent integration.

### P2-M8.2: Unified Retrieval Shadow Gate

- Add P1/P2 parallel adapters behind the versioned contract.
- Add RRF, source quotas, route-local thresholds, partial failure, and feature flags.
- Return P1 control while computing/logging unified candidates in shadow.
- Add unified eval partitions, load/latency tests, fallback injection, and observability.
- Decide whether existing `retrieval_logs` is sufficient; review a minimal new table only if evidence proves it is not.
- Run full repository tests, frontend build, and P1 Harness 10/10.

Exit: shadow release thresholds pass with zero archive leakage and no P1 regression. CustomerOpsAgent is still unchanged.

### P2-M8.3: CustomerOpsAgent Opt-in Integration

- Add explicit, default-off Agent opt-in to the versioned unified API.
- Preserve the old P1 endpoint and one-step rollback.
- Define Agent behavior for partial results; default to old P1 when unified retrieval fails.
- Run production shadow/smoke, rollback drill, eval, full tests, and P1 Harness 10/10.

Exit: explicit opt-in is proven. Default Agent switching remains a separately approved release decision.

## 12. Required Architecture Decisions

1. **Use dual indexes plus RRF?** Yes: physical P1/P2 isolation, logical versioned retrieval, route-local filtering, and RRF late fusion.
2. **Implement P2-only retrieval first?** Yes. M8.1 must pass its own eval before P1/P2 fusion exists.
3. **Add a versioned unified API?** Yes: `POST /api/v2/retrieval/search`, initially restricted to P2-only mode.
4. **Keep the old P1 endpoint?** Yes, permanently through P2 as the default control and rollback path.
5. **When does `ready` become `serving`?** Only after the complete current-profile vector build passes count, dimension, provider/model/profile, fingerprint, and trace validation and commits atomically. The initial release candidate is the derived SiliconFlow/Qwen/1536 profile; retrieval additionally requires its P2 eval approval and the P2 feature flag.
6. **How is archive zero recall guaranteed?** Logical status changes first; every query filters and revalidates active/serving/current state; cleanup can lag; retrieval never accepts archived access.
7. **How are different profiles fused?** Each route embeds and ranks independently; RRF combines ranks only. Raw cosine scores are never compared across indexes.
8. **When may CustomerOpsAgent connect?** Only in M8.3 after M8.1 eval and M8.2 shadow gates pass, through explicit default-off opt-in.
9. **Is a new database table needed?** Not now. Earliest review is M8.1 for compatibility; earliest evidence-driven addition is M8.2 if existing logs cannot safely support shadow observability. A profile-specific vector index is reviewed separately and is not a table.
10. **What is the next stage?** P2-M8.1 P2-only Retrieval Foundation, under a new explicit implementation authorization.

## 13. Non-Negotiable Anti-Drift Rules

1. The P1 endpoint is never directly replaced during P2.
2. No fusion is implemented before P2-only retrieval passes eval.
3. Unified Retrieval cannot connect to Agent before shadow verification passes.
4. Until explicit Agent opt-in, the default remains P1.
5. Every implementation stage must pass the sealed P1 Harness 10/10.
6. Archived leakage must equal zero.
7. Raw cosine scores from different indexes must never be directly compared or mixed.
8. Unreviewed Extraction content cannot bypass Snapshot and Knowledge Asset governance.
9. P2 content must never be written into P1 `rag_embeddings`.
10. Eval and rollback gates may not be skipped to accelerate delivery.

## 14. Risks and Controls

| Risk | Control |
|---|---|
| P1 behavior pollution | Additive API/adapters, permanent old endpoint, separate indexes, P1 Harness |
| Archived vector leakage | Query-time joins, post-recall recheck, no archive override, concurrency tests |
| Incomparable vector scores | Route-local thresholds and ranks; RRF only |
| Weak P2 candidates reducing P1 quality | P2-only gate, route floors, shadow control, recall/MRR delta limits |
| Latency/cost doubling | Parallel fan-out, timeout budgets, candidate caps, profile-aware caching only after archive-safe design |
| Duplicate versions/assets | Active-version filter, Knowledge Asset collapse, per-Asset chunk quota |
| Profile/dimension drift | Explicit active profile, dimension validation, profile-specific vector index, reject serving on mismatch |
| Incomplete lineage | Resolve and validate full trace before response; completeness gate 100% |
| Log-table coupling to P1 reader | Compatibility test first; structured logs or later minimal table if needed |
| Premature Agent cutover | Shadow first, explicit opt-in, default P1, feature-flag rollback |
| Model upgrade lifecycle gap | M8.1 generation/profile activation review before alternate profile serving |

## 15. Scope Audit

P2-M8 changes documentation only.

- No Python or TypeScript business code is changed.
- No database schema, table, column, migration, or vector index is added.
- No retrieval or activation API is implemented.
- No P1 `rag_chunks`, `rag_embeddings`, CustomerOpsAgent endpoint, retrieval mode, or response contract is modified.
- No RRF, parallel recall, feature flag, Embedding call, Agent call, frontend change, P3, or P4 work is implemented.
- No `.env`, API key, `DATABASE_URL`, secret, uploaded binary, or tag is added.

Completion of this document authorizes only a request to enter P2-M8.1. It does not authorize that implementation by itself.

## 16. P2-M8.1 Implementation Outcome

P2-M8.1 implemented the isolated prerequisite without entering unified retrieval:

- The concrete P2-only route is `POST /api/v2/retrieval/p2/search`.
- The planned unified `POST /api/v2/retrieval/search` route remains unimplemented and is deferred to M8.2.
- Embedding build and serving activation are now separate: build remains `ready`; explicit `/serve` performs the release gate.
- P2 retrieval queries only `knowledge_assets`, `p2_knowledge_index_entries`, `p2_knowledge_chunks`, and `p2_knowledge_embeddings`.
- Active/serving/sync/profile/dimension/fingerprint/trace eligibility is checked before vector recall and again before response serialization.
- Archive visibility is removed synchronously while physical P2 vectors remain available for audit/cleanup.
- No P1 fan-out, RRF, shadow execution, CustomerOpsAgent integration, or frontend retrieval surface was added.

M8.2 remains separately gated by P2 online eval, archive leakage `0`, P1 Harness 10/10, and explicit authorization.

## 17. P2-M8.1 Online Gate Outcome

The M8.1 feature commit `bebf92c` is deployed. The sealed P1 Harness passed 10/10 with PostgreSQL/pgvector healthy, 41 SiliconFlow embeddings at 1536 dimensions, `customerops_vector_retrieval`, and no fallback. The deployed P2-only Eval remained isolated (`semantic_mode_count=10`, no P1 fallback) and reported `archived_leakage_count=0`.

The online P2 retrieval-quality gate did not pass: Render rejected the initial Asset upload with `ASSET_STORAGE_UNAVAILABLE` because the P2-M1-required persistent disk root is not configured. With no serving P2 corpus, `query_hit_rate@5=0.0` and formal recall/MRR are unavailable. M8.2 shadow work is therefore not authorized until deployment storage is fixed and the complete ready-zero-hit -> explicit-serve-hit -> archive-zero-hit proof plus the >=0.75 query-hit threshold pass.
