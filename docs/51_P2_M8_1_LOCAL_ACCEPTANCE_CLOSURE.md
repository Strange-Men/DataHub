# P2-M8.1.1 Local Acceptance Closure

## 1. Acceptance Decision

P2-M8.1.1 closes the development acceptance gap with a real local runtime rather than treating Render's missing Asset storage as a P2 application failure.

The acceptance states are deliberately separate:

- **M8.1 Development Acceptance: PASS** for the governed P2 chain, real PostgreSQL/pgvector, real SiliconFlow embedding, explicit serving, isolated retrieval, archive withdrawal, exact-id Eval, and safe logging.
- **M8.1 Render Deployment Acceptance: BLOCKED** because the current Render service has no usable persistent Asset disk and `POST /api/assets/upload` fails closed with HTTP 503 `ASSET_STORAGE_UNAVAILABLE`.
- The local P1 Harness and the final automated regression/build gates passed. P2-M8.2 Shadow development and testing may proceed locally under a separately authorized scope; this does not authorize Render Shadow traffic or any Agent switch.

This closure does not claim that Render file persistence, restart durability, or the online P2 end-to-end path has passed.

## 2. Why Local Acceptance Was Required

The deployed M8.1 route and sealed P1 regression were already verified, but Render could not create the first Asset because the production-safe local storage adapter refuses to use an unconfigured ephemeral filesystem. With no Asset, it was impossible to build a governed serving corpus online. The resulting empty-corpus Eval was therefore a deployment-environment observation, not evidence that P2 retrieval logic failed.

The local acceptance uses the same public APIs and the same application code with:

- a persistent project-local Asset root on the D drive;
- PostgreSQL with pgvector rather than SQLite;
- the configured SiliconFlow provider rather than the mock provider;
- a runtime expected-id manifest excluded from Git;
- no direct inserts into any P2 business table.

The original Render empty-corpus results remain unchanged in `docs/50_P2_M8_1_P2_ONLY_RETRIEVAL_FOUNDATION_REPORT.md`.

## 3. Local Configuration and Secret Safety

The ignored local `.env` preserves existing values and supplies only the runtime values needed by the current code. Secrets and connection credentials are not printed, copied into scripts, or committed.

The Asset root is:

```text
D:/Claude_workfile/DataHub/.local-data/assets
```

Both `.env` and `.local-data/` are ignored. The local Asset objects, runtime manifest, PostgreSQL credentials/data, API logs, and generated test material remain outside version control. The acceptance script prints identifiers and safe provider metadata, but never a full vector, API key, or `DATABASE_URL`.

## 4. PostgreSQL and pgvector Runtime

The acceptance runtime uses PostgreSQL 16 with the `vector` extension available and enabled (`pgvector 0.8.5`). Application initialization can access both the sealed P1 tables and the isolated P2 tables. PostgreSQL credentials are supplied locally without exposing the password in the report or command output.

SQLite was not used as proof of semantic retrieval. The P2 query executed the production PostgreSQL cosine-distance path over `p2_knowledge_embeddings`.

## 5. SiliconFlow Embedding Profile

The provider was validated with a real online call before the governed chain ran:

| Field | Accepted value |
|---|---|
| provider | `siliconflow` |
| model | `Qwen/Qwen3-Embedding-4B` |
| dimension | `1536` |
| embedding profile | `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536` |

The persisted build and retrieval response used this profile. No mock embedding was accepted as local semantic-index proof.

## 6. Governed P2 End-to-end Smoke

The accepted run used trace:

```text
p2-local-20260716-014332-34783c6a
```

The script called only public APIs and executed:

```text
Asset Upload
  -> Extraction Job and immutable Extraction
  -> Human Review with revised governed content
  -> approved Snapshot
  -> active Knowledge Asset
  -> ready Index Entry and immutable Chunk
  -> real SiliconFlow Embedding
  -> Entry remains ready
  -> pre-serve P2 search returns no target
  -> explicit Serve
  -> P2-only search returns the target with full trace
  -> Archive
  -> the same query returns no archived target
```

The archive-smoke lineage was:

| Object | Runtime id |
|---|---|
| Asset | `asset_5cf1bfb863d54593a6bd` |
| Extraction Job | `asset_extract_job_020d45fb141e42a1ab96` |
| Extraction | `asset_extract_fb7337c92f1046f380cb` |
| Review | `extraction_review_30d3adb4749248c09e82` |
| Snapshot | `asset_review_snapshot_5514cc4423b848dfa2ec` |
| Knowledge Asset | `knowledge_asset_0a9ef62045df44c485c8` |
| Index Entry | `p2_index_c9a6edec18cd4c0f8194` |
| Chunk | `p2_chunk_f465b51276a90e9b3f9e` |
| Embedding | `p2_embedding_278b2dfb49df22174327` |

The chain preserved the full Index Entry -> Knowledge Asset -> Snapshot -> Review -> Extraction/Job -> Asset trace. The binary was saved under the ignored local Asset root and created an Asset row without making Git dirty.

## 7. Ready, Serve, Archive, and Version Results

### 7.1 Build remains ready

After the embedding build:

- Entry status was `ready`;
- `sync_state` was `ready`;
- the stored provider/model/dimension/profile matched the accepted SiliconFlow profile;
- the target was not retrievable before explicit activation.

This proves the M8.1 correction: the embed endpoint cannot bypass the Serving Gate.

### 7.2 Explicit serve

`POST /api/knowledge-index/{id}/serve` passed the active-source, status/sync, Chunk/Embedding coverage, provider/profile/dimension, fingerprint, and source-trace gates. The Entry changed to `serving`; the next P2-only search returned the governed target with `retrieval_mode=p2_vector_retrieval`, `fallback_used=false`, and complete trace.

### 7.3 Archive withdrawal

After archive, the same query returned no archived target even though the physical `p2_knowledge_embeddings` record remained. Logical query visibility is therefore independent of delayed physical vector cleanup.

### 7.4 Superseded version withdrawal

A second governed version was created for the same source Asset. The old Knowledge Asset `knowledge_asset_e7b61ecd65d64c9da34f` and old Chunk `p2_chunk_f6300342fdd16919f8ad` were forbidden, while the new active/serving Knowledge Asset `knowledge_asset_4d3a33057fd64f998efa` and Chunk `p2_chunk_f81766aee276d83d6303` were expected. Eval returned the new version and no old-version evidence.

## 8. Runtime Expected Manifest

`scripts/run_p2_local_acceptance.py` generated the ignored runtime manifest:

```text
D:/Claude_workfile/DataHub/.local-data/p2-eval-expected-manifest.json
```

It maps each query to runtime Knowledge Asset, Asset, and Chunk ids and marks archived/forbidden ids explicitly. Runtime ids are not hard-coded into the committed sample corpus. `scripts/run_p2_rag_eval.py --expected-manifest` uses one canonical identity grain per query and can therefore report formal candidate recall and MRR rather than promoting keyword overlap to recall.

## 9. Local P2 Eval

The governed local corpus covers product material/specification, warranty, cancellation, returns, OCR-derived content, Caption-derived content, Metadata-derived content, FAQ, version conflict, archive withdrawal, semantic paraphrase, and no-answer behavior.

| Metric | Result |
|---|---:|
| total_queries | 12 |
| hit_rate@5 | 1.0 (keyword proxy) |
| query_hit_rate@5 | 1.0 |
| candidate_recall@5 | 1.0 |
| candidate_recall_query_count | 10 |
| MRR | 0.95 |
| mrr_query_count | 10 |
| semantic_mode_count | 12 |
| no_hit_count | 2 |
| archived_leakage_count | 0 |
| duplicate_asset_rate | 0.0 |
| avg_top1_score | 0.712 |
| avg_top5_score | 0.6195 |
| avg_latency_ms | 2387.681 |
| p95_latency_ms | 2900.276 |
| failed_queries | 0 |

All responses used the P2-only route and none fell back to P1. Formal recall and MRR are calculated over the ten positive, id-labeled queries; the archive and no-answer negatives are excluded from those denominators and evaluated by their own expectations. The no-answer sample returned no hit in this run, but one negative query is not sufficient to claim a generally calibrated refusal policy; score-floor calibration remains an M8.2 evaluation concern.

## 10. Retrieval Log Verification

The local database check sampled 64 P2 retrieval records at verification time and confirmed:

- ids use the `p2_retrieval_*` namespace;
- `metadata_json.namespace=p2_retrieval_v1`;
- retrieval/request ids, query, top_k, matched Chunk and Knowledge Asset ids, similarity scores, provider/model/dimension/profile, latency, fallback state/reason, and source-trace summaries are present;
- no complete vector, API key, or `DATABASE_URL` is stored.

This reuses the existing flexible log table without modifying the P1 retrieval writer or adding a new observability table.

## 11. Local P1 Regression

The sealed P1 Harness ran against the same local PostgreSQL/pgvector backend and passed:

| Gate | Result |
|---|---|
| trace | `p1-harness-20260715-175644-34b47c` |
| Pipeline Harness | 10/10 PASS; failed 0, skipped 0 |
| duration | 9.5 s |
| PostgreSQL | healthy |
| pgvector | available; extension create check PASS |
| RAG sync | 2 Chunks, 2 Embeddings, 0 failed Embeddings, vector sync enabled |
| provider/model/dimension | SiliconFlow / `Qwen/Qwen3-Embedding-4B` / 1536 |
| CustomerOpsAgent | `customerops_vector_retrieval`, `fallback_used=false` |
| Bad Case | submit and draft PASS |

This confirms that the local P2 runtime did not break the sealed P1 vector path. The P2 implementation remains physically isolated from P1 `rag_chunks` and `rag_embeddings` and does not call the CustomerOpsAgent endpoint.

The Harness API process was launched from an ignored clean export of the current HEAD while using the same `.env`, PostgreSQL database, pgvector extension, and SiliconFlow account. This excluded unrelated historical files under the developer's ignored `backend/storage` directory; it did not change application source, the database schema, or the Harness contract.

## 12. Automated Tests and Frontend Build

Final closure verification passed:

| Gate | Result |
|---|---|
| focused M8.1.1/Eval plus M4/M6/M7/M8.1 regression | 59 passed; 18 warnings; 8.25 s |
| full `pytest backend/tests -q` | 327 passed; 44 warnings; 146.62 s in an ignored clean runtime copy |
| `python -m compileall backend/app scripts` | PASS; 0.132 s |
| frontend `npm run build` | PASS; 49 modules; Vite build 948 ms |
| `git diff --check` | PASS |

The authoritative full-suite run used `.local-data/full-test-runtime`, exported from the current HEAD and overlaid with every tracked change plus both new files. The overlaid file hashes matched the working tree and `backend/storage` was clean. This was necessary because ignored historical developer storage in the main workspace made a full run process old local corpus data; that non-authoritative run was stopped without changing source. The 327-test result is the actual M8.1.1 tree and exceeds the 319-test baseline. Warnings were limited to existing FastAPI `on_event` deprecations, pytest-asyncio loop-scope deprecation, and expected mock-provider fallback warnings.

## 13. Local Acceptance Versus Render Acceptance

The local result proves:

- governed public-API material ingestion and lineage;
- PostgreSQL/pgvector P2 semantic retrieval;
- real SiliconFlow embedding with the accepted profile;
- embed-keeps-ready and explicit Serving Gate behavior;
- serving retrieval with complete trace and no P1 fallback;
- archive and superseded-version zero recall;
- exact-id Eval and safe retrieval logging.

It does not prove:

- Render Asset persistence;
- Render restart durability for uploaded material;
- a complete Render P2 chain or production serving corpus;
- online P2 Retrieval enablement or CustomerOpsAgent integration.

Accordingly, Development Acceptance is PASS for the P2 chain, while Render Deployment Acceptance stays BLOCKED.

## 14. M8.2 Entry Decision

Local P2 gates already satisfy the full governed chain, real SiliconFlow build, pre-serve zero recall, post-serve hit, post-archive/old-version zero recall, `archived_leakage_count=0`, `query_hit_rate@5=1.0`, and `candidate_recall@5=1.0`.

Authorization for **P2-M8.2 local Shadow Gate development and testing** is granted under a separately authorized scope because both final records passed:

1. local P1 Harness = 10/10;
2. focused/regression/full tests and build = PASS.

Local M8.2 work may therefore proceed when explicitly requested. That permission does not authorize online P2 enablement, Render Shadow traffic, RRF replacement of P1, or any CustomerOpsAgent switch. Render Shadow remains constrained by the storage deployment blocker.

## 15. Render Follow-up Options

The two acceptable future infrastructure reviews are:

1. attach and configure a Render Persistent Disk for the existing local filesystem adapter; or
2. implement and separately review an S3/R2-compatible Storage Adapter.

Neither option is implemented in P2-M8.1.1. This milestone does not upgrade Render, purchase a disk, or add S3, R2, OSS, or MinIO.

## 16. Scope Boundary

This closure adds no Unified Retrieval, RRF, Shadow Retrieval runtime, CustomerOpsAgent integration, P1 retrieval change, P1 vector-table change, frontend retrieval page, native multimodal embedding, P3, or P4 capability. Local runtime data and secrets remain uncommitted, and no tag is created.
