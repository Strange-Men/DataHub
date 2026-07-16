# P2-M8.3 CustomerOpsAgent Explicit Opt-in Report

## 1. Outcome and Recovery Scope

P2-M8.3 adds a versioned, explicitly requested CustomerOpsAgent path to the already accepted M8.2 Unified Retrieval service. It does not replace the sealed P1 endpoint, change the old request/response schema, change P1 vector tables, or make Unified Retrieval the default.

The phase resumed after an unexpected workstation shutdown. Recovery found `HEAD == origin/main == e0eb6b6`, one edited recovery-ledger file, and three untracked M8.3 modules. There was no local commit, divergence, merge conflict, secret, or unknown user change. Those files were preserved and completed in place. The Docker engine had stopped, but the original named volumes and corpus were intact after Docker Desktop resumed.

## 2. Compatibility Decision

The additive endpoint is:

```text
POST /api/v2/customer-ops-agent/retrieve
X-DataHub-Client: CustomerOpsAgent
```

The existing endpoint remains unchanged and permanently P1-only:

```text
POST /api/customer-ops-agent/retrieve
```

The v2 request reuses `query`, `top_k`, `filters`, `conversation_id`, and `agent_session_id`, and adds:

- `retrieval_strategy`: `p1` by default; `unified` is the only opt-in value;
- `request_id`: optional caller correlation id.

The v2 response keeps the familiar retrieval id/query/top-k/mode/results/fallback fields and adds requested/actual strategy, native legacy/unified ids, branch modes, RRF/source fields, and governed source trace. The old endpoint returns its original P1 response unchanged.

## 3. Activation Matrix and Feature Flags

Active Agent Unified Retrieval requires all of the following:

1. the caller uses the new v2 endpoint;
2. `retrieval_strategy=unified` is explicit;
3. `CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED=true`;
4. `UNIFIED_RETRIEVAL_ENABLED=true`;
5. `P2_RETRIEVAL_ENABLED=true`;
6. `UNIFIED_RETRIEVAL_SHADOW_MODE=false`;
7. no unsupported P1-only filter is supplied.

All switches default to `false` in `.env.example` and Compose.

| Server flags | Request | Actual result |
|---|---|---|
| Agent flag off | default P1 | sealed P1 |
| Agent flag off | explicit Unified | sealed P1, `fallback_used=true`, reason `customerops_unified_retrieval_disabled` |
| all active flags on | default P1 | sealed P1 |
| all active flags on, Shadow off | explicit Unified | active P1+P2 RRF evidence |
| Shadow on | explicit Unified | sealed P1, reason `unified_shadow_mode_active` |
| unsupported P1-only filter | explicit Unified | sealed P1, reason `unified_filters_not_supported` |

Shadow is never treated as active Agent evidence. The independent Agent flag is the immediate kill switch even when the general Unified API is enabled.

## 4. P1 Compatibility and Payload-aware Adapter

M8.3 does not edit `backend/app/storage.py`, the legacy CustomerOps schemas, P1 repositories, `rag_chunks`, or `rag_embeddings`. `main.py` only imports/registers the new router and advances the P2 phase string.

The M8.2 P1 adapter gained an optional request factory. M8.2 callers keep the old default behavior. The Agent v2 path injects the original legacy-compatible payload so conversation/session context is not silently lost inside the P1 branch. P1-only filters are not projected onto P2; an explicit Unified request with such filters fails safe to the original filtered P1 retrieval.

The legacy endpoint was tested with an extra `retrieval_strategy` field: the sealed request schema ignored it as before, `run_customerops_retrieval` was called, Unified was not called, the mode remained `customerops_vector_retrieval`, and no v2 response field appeared.

## 5. Active Evidence and Governance

Only a healthy M8.2 result with `candidate_mode=unified_rrf` is accepted as active Agent Unified evidence. A partial P1 or P2 candidate is not used as an Agent answer source; it falls back to a fresh sealed P1 retrieval.

Each v2 evidence item carries:

- actual `source_index` (`p1` or `p2`);
- rank, fused rank score, and route-local diagnostic score;
- candidate/Knowledge Asset/Asset/Chunk ids where applicable;
- evidence text and content type;
- complete governed source trace and metadata.

M8.3 reuses M8.2 rank-only RRF (`k=60`). It never directly compares P1 and P2 cosine scores. P2 evidence is still subject to the active/serving/sync/fingerprint/profile/dimension/source-trace/current-version gate before and after recall. No embedding vector is returned.

## 6. Failure, Fallback, and Rollback

Unified failure, timeout, both-branch failure, or degraded single-branch output causes a new call to sealed P1 retrieval. The response records:

- `actual_retrieval_strategy=p1`;
- `fallback_used=true`;
- a bounded sanitized reason;
- the attempted Unified retrieval id when one exists;
- the actual legacy retrieval id and legacy mode.

Exception messages, stacks, keys, and database URLs are not exposed. If both Unified and P1 fail, the versioned endpoint returns a safe 503 envelope.

Rollback requires no schema or data change: set `CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED=false`. Disabling either general Unified/P2 flag also returns explicit opt-in calls to P1. The old endpoint is unaffected by every M8.3 flag.

## 7. Docker Agent Smoke Evidence

The public-API runner is `scripts/run_customerops_unified_opt_in_smoke.py`. It reads the ignored runtime P2 manifest, calls both CustomerOps endpoints, checks actual strategy/mode, verifies source trace, and validates exact archived ids without printing vectors or secrets.

Default-off Docker run:

- trace `agent-opt-in-smoke-20260716-025833-409038`;
- all four feature flags `false`;
- old endpoint mode `customerops_vector_retrieval`;
- v2 default actual strategy `p1`;
- explicit opt-in actual strategy `p1`;
- fallback reason `customerops_unified_retrieval_disabled`;
- PASS.

Active Docker run:

- trace `agent-opt-in-smoke-20260716-025912-83cfd3`;
- Agent/Unified/P2 flags true and Shadow false;
- old endpoint and v2 default both remained P1;
- explicit opt-in returned `customerops_unified_retrieval`;
- evidence sources were P1 and P2;
- fallback was false;
- archived leakage was `0`;
- PASS.

A controlled Docker fault set the branch timeout to 50 ms. Both Unified branches timed out, then the v2 integration returned sealed `customerops_vector_retrieval`, `fallback_used=true`, and safe reason `unified_retrieval_failed:branches_unavailable:p1_timeoutp2_timeout`. All four flags were restored to `false` after the smoke.

## 8. P1, P2, and Shadow Regression

The latest Docker P1 Harness passed 10/10 under trace `p1-harness-20260716-030109-dbcb8c`:

- PostgreSQL and pgvector healthy;
- real SiliconFlow 1536-dimensional embedding sync healthy;
- `customerops_vector_retrieval` remained the default;
- retrieval fallback remained false;
- Bad Case submit and draft passed.

The independent P2 Eval remained at 12/12 semantic queries:

- keyword hit/query-hit `1.0/1.0`;
- exact `candidate_recall@5=1.0` over 10 labeled positives;
- `MRR=0.95`;
- archived leakage `0`;
- duplicate Asset rate `0.0`;
- zero failures.

The rerun Unified Shadow Eval completed 11/11:

- control/candidate query hit `0.5556/1.0`;
- control/candidate exact recall `0.0/1.0` over 7 labels;
- control/candidate MRR `0.0/0.6071`;
- source coverage `1.0`;
- duplicate Asset rate `0.0`;
- archived leakage `0` across 3 labeled negative cases;
- Shadow contract violations `0`;
- fallback and failed-query counts `0`.

The observed p50/p95 latency was 315.017/6279.542 ms. The high p95 is recorded as a local external-provider outlier, not converted into an invented production SLO. Four no-answer results also confirm that no calibrated refusal threshold exists yet.

## 9. Automated Test and Build Gates

- recovery compatibility check: 31 passed;
- M8.3-only tests: 14 passed;
- M8.2/M8.3 plus M4/M6/M7/M8.1/P1 focused matrix: 98 passed;
- authoritative ignored clean-export full backend suite: **379 passed**, 44 existing warnings, 139.19 seconds;
- Python compileall: PASS;
- frontend production build: PASS;
- Docker config/build/healthy-up: PASS.

The working-directory full suite was safely stopped after local historical-data scanning exceeded its prior baseline; no corpus was deleted. The authoritative clean export contained the current uncommitted implementation but no `.env` or `.local-data` and completed normally.

## 10. Boundaries and Next Stage

M8.3 does not implement default Agent cutover, answer generation, native image embedding, CLIP, multimodal reranking, cloud Asset storage, Render disk configuration, P3, or P4. The versioned endpoint is an explicit retrieval/evidence surface; the old Agent and Bad Case paths remain available.

Render Deployment Acceptance remains **BLOCKED** by missing Persistent Disk and `ASSET_STORAGE_UNAVAILABLE`. All evidence in this report is local Docker development acceptance, not Render online acceptance.

M8.3 implementation, acceptance, and the final 18-file diff/ignore/secret audit are complete. Only the phase commit and normal push remain. After that Git closure, the next and only phase is P2-M9 Final Local Docker Release Closure.
