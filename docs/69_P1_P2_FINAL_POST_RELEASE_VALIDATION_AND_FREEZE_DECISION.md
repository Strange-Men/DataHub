# P1/P2 Final Post-Release Validation and Freeze Decision

## 1. Decision

Final decision: **PATCH REQUIRED**, followed by a formal P1/P2 freeze after the audited patch is pushed and tagged.

The audit found no functional defect, security issue, data-integrity defect, test-environment coupling regression, archived/old-version leakage, or Agent/Unified contract drift. It did confirm two bounded-query performance defects in P2 Source Trace loading. Both were fixed without changing API schemas, lifecycle gates, RRF, embedding configuration, database schema, CustomerOpsAgent's P1-only default, or Unified opt-in.

The existing `p2-m9.5-maintenance-hardening` tag remains the immutable maintenance-release baseline. The patch receives a new tag only after every affected and full gate passes.

## 2. Audit Scope and Baseline

- Baseline commit: `299e08a439a2179303680d19909794824b4de2a0`.
- Protected tags: `p1-m24.3-real-embedding-online-release`, `p2-m9-local-docker-release`, and `p2-m9.5-maintenance-hardening`.
- Reviewed surfaces: final reports 58-68, backend routes/schemas/services/repositories/tests, scripts, frontend source/contracts, Compose/Docker/pytest configuration, README and `.env.example`.
- Runtime boundary: retained local Docker is authoritative for P1/P2; Render P2 persistence remains unvalidated and blocked.
- Recovery evidence and runtime artifacts stayed under ignored `.local-data/` and were not staged.

## 3. Functional Completeness

| Chain | Result | Evidence |
|---|---:|---|
| P1 import through Bad Case | PASS | isolated P1 Harness 10/10; approved-only retrieval and Source Trace |
| CustomerOpsAgent default | PASS | default/legacy path remains P1-only; fallback state is explicit |
| P2 Asset through Archive | PASS | Ready before Serve 0; Serve hit; Archive 0; superseded version 0 |
| P2 physical retention | PASS | archived/superseded vectors retained while retrieval eligibility is removed |
| Unified | PASS | explicit opt-in produces `unified_rrf`; safe default remains disabled |
| Unified parallelism | PASS | 1,581.655 ms total versus 1,411.371/1,495.031 ms branches and 0.105 ms fusion |
| Agent abstention | PASS | unreliable evidence is not cited in enforced mode; failure is distinct from no-answer |

No route, service or frontend action was found to bypass Review, Snapshot, Serving, Archive, Auth or No-answer gates. No fake-success button or production TODO/FIXME/HACK path was confirmed.

## 4. Auth/RBAC Final Audit

The application exposes 60 FastAPI routes: 4 public discovery/docs routes and 56 API routes. Of the API routes, 2 health routes are public and 54 are protected, including authenticated `/api/auth/me`. Missing protected routes: **0**.

- Missing/invalid Token returns stable 401; insufficient permission returns stable 403.
- Admin, cleaner, reviewer, service and viewer permissions match the centralized matrix.
- Cleaner cannot review/Serve/Archive; reviewer cannot import/Embed/Serve; service cannot perform human governance; viewer is read-only.
- Token matching uses constant-time comparison; duplicate Tokens and token mode without usable Tokens fail safely.
- Token is not accepted through query strings and was not found in URL, logs, error responses, source or Git diff.
- The frontend trusts only `/api/auth/me` for role identity and stores only the Token in `sessionStorage`.
- Disabled mode remains explicit compatibility behavior; invalid token-mode configuration does not downgrade to disabled.

Classification: **No security issue**.

## 5. Data Integrity and Test Isolation

Development and isolated test Compose projects ran concurrently. PostgreSQL/pgvector tests used a test-named database and separate network, ports and volumes. Only test-project containers, networks and volumes were removed.

| Development count | Before | After | Interpretation |
|---|---:|---:|---|
| Assets, total | 79 | 89 | two P2 acceptance runs retained ten scoped test Assets |
| Knowledge Assets, total | 92 | 104 | twelve scoped test versions retained and logically archived |
| Knowledge Assets, active | 13 | 13 | no new active test or duplicate active version |
| Knowledge Assets, archived | 79 | 91 | cleanup used logical archive only |
| non-test Assets | 24 | 24 | unchanged |
| non-test Knowledge Assets | 26 | 26 | unchanged |
| P1 RAG embeddings | 10 | 10 | unchanged |

`deleted_records=0`. Eval metrics used current-run manifests and did not read historical test IDs. No test container, test volume, pytest process, test port or test database remained. All three development services stayed healthy and their volumes were neither deleted nor reset.

Classification: **No data integrity risk** and **No test-isolation issue**.

## 6. No-answer Exploratory Review

A new ignored 24-sample exploratory set (12 answerable / 12 no-answer) stressed threshold edges, multi-intent and negative wording, similar names, Chinese/English mixtures, typos, guessing prompts, partial answerability, conflicts, very short and long queries. It did not copy or modify the original 26-sample calibration set or the 48-sample release holdout and was not used for tuning.

| Metric | Result |
|---|---:|
| answerable precision / recall | 0.9167 / 0.9167 |
| no-answer precision / recall / F1 | 0.9167 / 0.9167 / 0.9167 |
| false-answer rate | 0.0833 |
| false-rejection rate | 0.0833 |
| reason accuracy | 0.9167 |
| archived / old-version leakage | 0 / 0 |

Boundary errors:

1. `换货所需凭正有哪些` scored 0.44 against the P1 threshold 0.45 and was falsely rejected.
2. `名称相近的青春版政策可直接用于专业版吗` scored 0.56 against the P2 threshold 0.55 and was falsely accepted.

These two deliberately adjacent samples show boundary sensitivity, not a systematic failure. The authoritative 48-sample holdout remains 0.9583 on answerable/no-answer precision and recall with a 0.0417 false-answer rate. Thresholds remain P1 `0.45`, P2 `0.55`, Unified `1.0`; no expected labels or thresholds were changed.

Classification: **Product limitation / Test gap**, not a release blocker.

## 7. Performance Observation and Confirmed Fixes

Ten-query local Docker observations before the fixes:

| Path | p50 | p95 / max | Error / fallback |
|---|---:|---:|---:|
| P1 Retrieval | 4.64 ms | 26.48 ms | 0 / 0 |
| P2 Retrieval | 1,053.38 ms | 1,468.61 ms | 0 / 0 |
| Unified Retrieval | 1,319.61 ms | 1,952.69 ms | 0 / 0 |
| Source Trace detail | 13.97 ms | 26.21 ms | 0 / 0 |
| CustomerOpsAgent | 1,155.13 ms | 2,398.72 ms | 0 / 0 |

Provider time dominates P2/Agent latency, but two database query amplifications were independently reproduced:

1. **Knowledge Asset list Source Trace N+1**: a page of 20 executed 82 SQL statements. A joined bulk lineage load reduced it to exactly 2 while preserving the stable 409 response for incomplete lineage.
2. **P2 Retrieval governance N+1**: one real PostgreSQL retrieval executed 220 SQL statements and one Query Embedding call. Bulk index/asset/trace loading plus one fresh bounded serving-state race gate reduced it to 8 SQL statements and one Query Embedding call.

The retrieval fix keeps the post-vector-search archive/Serve race check, source fingerprint validation and complete trace. It does not cache mutable Serving state across the request, alter ranking, or expose vectors.

Classification: **2 confirmed Performance issues, fixed**. No other measured performance issue justified a product rewrite.

## 8. Maintainability Review

No unsafe production `pass`, temporary mock success, scattered Auth permission matrix, duplicate No-answer threshold implementation or unused live route was confirmed. The following low-risk items remain intentionally unchanged:

- `frontend/src/pages/AdvancedPage.tsx` appears unused; removal should wait for a separately scoped frontend cleanup.
- FastAPI `@app.on_event("startup")` emits a deprecation warning; migration to lifespan is optional and not a release defect.
- Legacy P1 list APIs should receive pagination before substantially larger deployments.

No database migration, RRF change, Provider replacement, UI redesign or dependency upgrade was performed.

## 9. Findings Matrix

| Category | Count | Result |
|---|---:|---|
| Confirmed defects | 2 | both performance/query-amplification defects fixed |
| Functional defects | 0 | no issue |
| Security issues | 0 | no issue |
| Data integrity risks | 0 | no issue |
| Test isolation issues | 0 | no issue |
| Development drift | 0 | no issue |
| Test gaps | 3 | browser E2E automation; broad query-budget/latency regression; Render persistence acceptance |
| Optional optimizations | 3 | unused page cleanup; FastAPI lifespan migration; legacy-list pagination |

Deferred items remain OIDC/identity lifecycle and secret manager integration, production calibration/drift monitoring, cloud/native multimodal and high-scale load acceptance, Render persistent P2 deployment, and P3/P4.

## 10. Final Test Gates

| Gate | Result |
|---|---|
| maintenance focused matrix | 130 passed, 2 warnings, 3.78 s |
| affected P2/Unified/lineage regression | 70 passed, 14 warnings, 5.93 s |
| PostgreSQL 16 / pgvector | 5 passed (post-fix rerun 4.27 s) |
| P1 Harness | 10/10 PASS |
| P2 Acceptance | PASS; Ready 0, Serve hit, Archive 0, old-version 0, vector retained |
| Unified runtime smoke | PASS; two branches, no fallback, explicit opt-in only |
| CustomerOpsAgent smoke | PASS; default P1-only and safe fallback |
| Auth/RBAC | PASS; 54 protected API routes, no omission |
| clean-export backend | 468 collected; 463 passed, 5 explicit PG skips, 44 warnings, 84.45 s |
| frontend governance contracts | PASS within focused matrix |
| frontend production build | PASS; 54 modules, 1.46 s |
| secret / ignored-artifact / diff checks | PASS |

## 11. Final Risk and Freeze Boundary

The patch changes only bounded repository loading, a fresh retrieval race gate and their regressions. All affected, PostgreSQL, runtime, frontend and full backend gates pass. Archived and old-version leakage remain zero; non-test data counts are unchanged.

After the patch commit and `p2-m9.5.1-post-release-fix` annotated tag are pushed, P1/P2 are formally **FROZEN** again. The prior tags remain unchanged. P3/P4 may begin only under separate authorization, after accepting the documented Render/deployment and scale limits, and without reopening sealed P1/P2 behavior.
