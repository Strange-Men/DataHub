# P2-M9 Final Local Docker Release Report

## 1. Release Decision

P2 reaches **Local Docker Release Closure** as a governed multimodal knowledge system based on OCR, Caption, and Metadata text bridges. The release includes independent P2 semantic retrieval, physical P1/P2 index isolation, rank-only Unified Retrieval Shadow, and an explicit default-off CustomerOpsAgent opt-in.

This is not a native image-vector release and is not a Render online release. Render Deployment Acceptance remains **BLOCKED** because the service has no usable Persistent Disk and Asset upload returns `ASSET_STORAGE_UNAVAILABLE`.

Release tag target:

```text
p2-m9-local-docker-release
```

## 2. Final Architecture

```text
Raw Asset
  -> local persistent object storage
  -> Extraction (Mock foundation; OCR/Caption/Metadata text bridge contract)
  -> Human Review and immutable approved Snapshot
  -> versioned Knowledge Asset
  -> P2 Index Entry and immutable Chunk projection
  -> profile-versioned SiliconFlow Embedding
  -> explicit ready -> serving gate
  -> P2-only Retrieval

Query
  -> sealed P1 adapter -----+
  -> governed P2 adapter ---+-> rank-only RRF -> Unified evidence
                                      |
                                      +-> Shadow comparison
                                      +-> explicit Agent v2 opt-in only
```

The frontend remains the existing dark Chinese governance console. No retrieval UI redesign was required for release closure.

## 3. P1/P2 Physical Boundary

P1 remains sealed at `p1-m24.3-real-embedding-online-release`:

- `rag_chunks` and `rag_embeddings` remain P1-only;
- the old `POST /api/customer-ops-agent/retrieve` remains unchanged;
- the default mode remains `customerops_vector_retrieval`;
- P1 Bad Case behavior remains unchanged.

P2 uses `knowledge_assets`, `p2_knowledge_index_entries`, `p2_knowledge_chunks`, and `p2_knowledge_embeddings`. P2 never writes its content into P1 vector tables. Cross-index combination happens only after independent ranked recall. Raw cosine scores are not compared across indexes.

## 4. Docker Architecture and Clone-style Startup

The tracked Compose environment provides:

- PostgreSQL 16 with pgvector;
- one-shot `volume-init` and `db-init` services;
- non-root FastAPI backend;
- nginx-served React frontend;
- PostgreSQL, Asset, compatibility-storage, and runtime-manifest named volumes;
- health/completion dependency ordering;
- runtime-only secret injection.

Final post-commit verification passed:

- `docker compose config --quiet`;
- full backend/frontend image build;
- healthy Compose startup;
- PostgreSQL/backend/frontend healthy;
- `phase=P1-M24.3`, `p2_phase=P2-M8.3`;
- pgvector 0.8.5;
- all four Unified/Agent flags restored to `false`.

The README documents clone, `.env`, Mock versus real SiliconFlow, build/up, health, complete P2 acceptance, Eval, P1 Harness, Agent opt-in, logs, normal shutdown, retained-data shutdown, explicit destructive volume cleanup, troubleshooting, Render limits, and secret safety.

## 5. Storage and Restart Durability

The final M9 acceptance created Asset `asset_7788ab58f2174634ab7c` through public APIs. Its database row and exact physical object remained present after:

1. backend container restart;
2. PostgreSQL container restart.

The Asset volume retained 12 objects, PostgreSQL retained the Asset row, and pgvector remained at 0.8.5. No volume was deleted or recreated destructively.

## 6. Governed P2 Lifecycle

Final full-chain trace:

```text
p2-local-20260716-034412-258b8ba0
```

The public-API acceptance executed:

```text
Asset Upload
-> Extraction
-> Review approved
-> Snapshot
-> Knowledge Asset publish
-> Index/Chunk
-> real SiliconFlow Embedding
-> ready
-> zero recall before Serve
-> explicit Serve
-> P2 hit
-> Archive
-> zero recall
-> version replacement
```

Embedding evidence:

- provider: `siliconflow`;
- model: `Qwen/Qwen3-Embedding-4B`;
- dimension: 1536;
- profile: `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536`.

The archive vector remained physically retained while logical recall was zero. The old Knowledge Asset/index version was archived, the new version became current/serving, and the old version was not returned.

## 7. Serving and Archive Gates

Embedding build leaves the Index Entry at `ready`. Only explicit `/serve` can transition it to `serving`. Activation requires active Knowledge Asset, ready/synchronized Entry, current immutable Chunk/Embedding coverage, compatible provider/model/dimension/profile, matching fingerprints, and complete trace.

P2 retrieval revalidates governance at repository and response time. Archive removes logical visibility immediately even if the physical vector is retained. Final P2, Unified, and Agent checks all reported archived leakage `0`.

## 8. Final P2 Eval

The new M9 corpus produced:

| Metric | Result |
|---|---:|
| total / semantic queries | 12 / 12 |
| keyword hit rate@5 | 1.0 |
| query hit rate@5 | 1.0 |
| exact candidate recall@5 | 1.0 over 10 |
| MRR | 0.525 |
| archived leakage | 0 |
| duplicate Asset rate | 0.0 |
| failed queries | 0 |
| average / p95 latency | 407.086 / 705.431 ms |

Exact recall did not regress from the M8.1 baseline of 1.0. MRR remains valid and positive. It is lower than the earlier isolated-corpus 0.95 because retained acceptance generations add semantically similar governed items and the runtime manifest labels one canonical version; this is recorded rather than hidden. No-answer cases still lack a calibrated refusal threshold.

## 9. Unified Retrieval and RRF

The additive API is:

```text
POST /api/v2/retrieval/search
```

P1 and P2 branches execute independently with bounded capacity and timeout isolation. RRF uses `k=60` and route rank only. Source-aware deduplication, current-version filtering, a P2 per-Asset chunk quota of 2, and result-time P2 governance apply before evidence is returned.

Single-branch failures degrade with explicit reasons; both-branch failure is safe. Shadow returns P1 control as visible results and records the Unified candidate separately.

## 10. Final Unified Shadow Eval

The expanded retained-corpus M9 run completed 11/11:

| Metric | Control | Candidate |
|---|---:|---:|
| query hit rate@5 | 0.5556 | 1.0 |
| exact recall@5 | 0.0 | 0.8571 |
| MRR | 0.0 | 0.4286 |

Additional gates:

- candidate not below control: true;
- source coverage: 1.0;
- candidate distribution: P1=35, P2=20;
- duplicate Asset rate: 0.0;
- archived leakage: 0 across 3 exact negatives;
- Shadow contract violations: 0;
- fallback count: 0;
- failed queries: 0;
- average/p50/p95 latency: 392.214/389.488/646.962 ms.

The original M8.2 controlled corpus remains recorded at candidate exact recall 1.0 and MRR 0.6071. The expanded M9 run retained the required candidate-over-control, source coverage, zero-leakage, and contract gates. Five no-answer results reiterate the deferred refusal-threshold boundary.

## 11. CustomerOpsAgent Explicit Opt-in

The old endpoint stays P1-only. The additive versioned endpoint is:

```text
POST /api/v2/customer-ops-agent/retrieve
```

Active Unified evidence requires explicit `retrieval_strategy=unified`, Agent/Unified/P2 flags enabled, and Shadow disabled. The independent Agent kill switch defaults off.

Final default-off trace `agent-opt-in-smoke-20260716-034915-889151` proved:

- old endpoint P1;
- v2 default P1;
- flag-off opt-in P1;
- safe reason `customerops_unified_retrieval_disabled`.

Final active trace `agent-opt-in-smoke-20260716-034826-d5dd31` proved:

- old endpoint and v2 default remained P1;
- explicit opt-in used `customerops_unified_retrieval`;
- evidence included P1 and P2 with source trace;
- fallback false;
- archived leakage 0.

A 50 ms branch-timeout injection produced sealed P1 fallback with `fallback_used=true` and safe reason `unified_retrieval_failed:branches_unavailable:p1_timeoutp2_timeout`. All flags were restored false afterward.

## 12. P1 Release Regression

Final Docker P1 Harness trace:

```text
p1-harness-20260716-034452-187174
```

Result: 10/10 PASS. PostgreSQL, pgvector, real SiliconFlow embedding sync, `customerops_vector_retrieval`, fallback false, Bad Case submit, and Bad Case draft all passed. P1 had 5 current chunks/embeddings after the final harness sync and zero reported embedding failures.

## 13. Automated Tests and Build

Final post-M8.3 commit results:

- M8.2 targeted: 29 passed;
- M8.3 targeted: 14 passed;
- P1/P2 lifecycle regression: 55 passed;
- authoritative clean-HEAD full backend suite: **379 passed**, 44 existing warnings, 135.30 seconds;
- Python compileall: PASS;
- frontend TypeScript/Vite production build: PASS;
- Docker config/build/up/health: PASS.

The clean export contained only tracked `HEAD`, no `.env`, `.local-data`, runtime corpus, or secret.

## 14. Retrieval Logs and Security

The final database contained both P2 and Unified retrieval logs. Successful Unified records used namespace `unified_retrieval_v1`, retained native branch ids and source distribution, and returned no complete vector. A database scan found zero log rows containing an API-key pattern, `DATABASE_URL`, `API_KEY`, or a raw `embedding` field.

The final Git audit passed immediately before the release commit: the diff is limited to README plus docs 08/09/52/55/56, the protected P1 diff is empty, `.env` and `.local-data` remain ignored, Git history contains no tracked `.env`, and current/history strong-secret scans found no candidates. Runtime manifests, Assets, databases, Docker volume data, `dist`, and `node_modules` remain untracked.

## 15. Rollback

Rollback is operational and non-destructive:

1. set `CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED=false` to disable Agent opt-in;
2. set `UNIFIED_RETRIEVAL_ENABLED=false` to close the additive Unified API;
3. set `P2_RETRIEVAL_ENABLED=false` to remove the P2 branch;
4. continue using the permanent old P1 endpoint;
5. archive a P2 Entry/Knowledge Asset for immediate zero visibility.

No P1 schema/data rollback, vector migration, history rewrite, or index merge is required.

## 16. Git Release Chain

- `935fc04` - P2-M8.1.1 local acceptance closure baseline;
- `cbf0e3d` - Overnight execution plan;
- `64c95c0` - reproducible Docker Foundation;
- `e0eb6b6` - Unified Retrieval Shadow Gate;
- `8113150` - CustomerOpsAgent explicit opt-in;
- `[P2-M9] release: close local docker release` - this final report/status closure commit; exact hash is recorded by the pushed commit and final handoff because a commit cannot contain its own hash.

The annotated tag is created only after the final diff/secret gate, release commit, normal push, clean worktree, and remote synchronization pass.

## 17. Render Deployment Status

Render Deployment Acceptance: **BLOCKED**.

The current Render service has no usable Persistent Disk, so P2 Asset upload fails closed. Local Docker results prove application behavior, database/vector behavior, storage-volume durability, and governance/retrieval gates; they do not prove Render file persistence or online P2 acceptance. This release does not retry or modify Render infrastructure.

## 18. Deferred Capabilities

- native multimodal/image embedding;
- image-to-image retrieval;
- CLIP;
- multimodal reranking;
- S3/R2/OSS/MinIO adapter;
- Render Persistent Disk and Render online P2 acceptance;
- default CustomerOpsAgent Unified cutover;
- calibrated no-answer threshold;
- P3 and P4;
- model fine-tuning;
- complex asynchronous index clusters;
- large-scale performance testing.

## 19. Final Scope Definition

P2 is complete locally as:

> A governed multimodal knowledge-asset and unified-retrieval system based on OCR, Caption, and Metadata text bridges, with immutable review lineage, independent semantic indexing, explicit serving, archive zero recall, Shadow RRF, and default-off Agent opt-in.

Native Multimodal Retrieval remains an optional future enhancement and is not required for this P2 release.
