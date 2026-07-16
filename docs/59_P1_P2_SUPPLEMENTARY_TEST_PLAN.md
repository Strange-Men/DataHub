# P1/P2 Supplementary Test Plan

This plan converts the evidence-backed gaps from the post-release audit into small, independently releasable test increments. It does not reopen either release tag and does not treat planned tests as implemented.

## 1. Objectives and Rules

- Protect the sealed P1 endpoint, P1 physical index and default CustomerOpsAgent behavior.
- Prove governance invariants against PostgreSQL/pgvector, not only SQLite and mocks.
- Make Docker E2E data run-scoped so repeated acceptance runs are comparable.
- Add fault, rollback, concurrency and contract evidence before coupling refactors.
- Never use production secrets or delete retained Docker volumes as part of a test.

Environment labels used below:

- **Unit**: isolated deterministic test, normally SQLite or a mock provider.
- **PG Integration**: disposable PostgreSQL + pgvector database created for the test run.
- **Docker E2E**: clone-style Compose stack with run-scoped test data.
- **Browser E2E**: production frontend against Docker backend.
- **Fault Injection**: controlled provider/storage/database/branch failure, never production.

## 2. T0 Release Safety

| Test ID | Target | Preconditions | Test data | Steps | Expected result | Automation | Environment | Priority | Related finding | Effort |
|---|---|---|---|---|---|---|---|---|---|---|
| T0-01 | Unreviewed content exclusion | Empty run namespace | pending/rejected/needs-revision reviews with unique phrases | complete ingestion and extraction but do not approve; search P2 and Unified | zero matching evidence; source trace never bypasses Snapshot/Knowledge Asset | automated E2E | Docker E2E | P0 | safety invariant | M |
| T0-02 | Archive and replacement zero recall | serving v1 plus active v2 | unique v1/v2 phrases | retrieve v1; archive entry/asset; publish v2; repeat searches | v1 disappears immediately although vector remains; leakage count 0 | automated integration + E2E | PG Integration, Docker E2E | P0 | AUD-003/AUD-005 | M |
| T0-03 | P1/P2 physical isolation | initialized P1 and P2 schemas | identifiable P1/P2 chunks | build/index each side; inspect table counts and query paths | P2 never writes P1 tables; P1-only request succeeds with P2 disabled | automated integration | PG Integration | P0 | coupling audit | M |
| T0-04 | Agent default compatibility | all Unified flags default false | legacy and opt-in requests | exercise flag/request matrix and compare legacy response schema | no opt-in remains `customerops_vector_retrieval`; disabled flag cannot activate Unified | automated contract | Unit, Docker E2E | P0 | Agent compatibility | S |
| T0-05 | Secret and error safety | sentinel secrets supplied only in process environment | provider/DB/storage failure messages | trigger safe failures; inspect responses/logs/artifacts and tracked files | no key, credential, URL password, vector or stack trace is exposed | automated scan + E2E | Fault Injection | P0 | AUD-001 | M |
| T0-06 | Docker persistence | healthy Compose and named volumes | unique Asset and DB record | create data; restart backend then postgres; fetch record and verify binary | record and binary survive; no volume deletion is required | automated smoke | Docker E2E | P0 | release gate | S |
| T0-07 | Governance authorization matrix | authentication design approved | anonymous, reviewer, publisher, admin identities | call import/review/publish/serve/archive/admin routes per role | unauthorized writes denied; authorized roles are least-privileged; public retrieval contract remains stable | contract + E2E | PG Integration, Docker E2E | P0 | AUD-001 | L |

## 3. T1 State, Failure and Recovery

| Test ID | Target | Preconditions | Test data | Steps | Expected result | Automation | Environment | Priority | Related finding | Effort |
|---|---|---|---|---|---|---|---|---|---|---|
| T1-01 | Illegal state transitions | lifecycle fixtures at every state | Asset/Extraction/Review/KA/Index states | attempt every prohibited transition through public APIs | stable error code; no partial mutation or Snapshot creation | parameterized integration | PG Integration | P1 | AUD-005 | M |
| T1-02 | Transaction rollback | fault hook after first cross-table write | approved Snapshot and active KA | fail publish/index/embed/archive at each write boundary | transaction rolls back or resumes idempotently; no orphan serving content | fault-injection integration | PG Integration | P1 | AUD-005/AUD-007 | L |
| T1-03 | Provider timeout/error | deterministic slow/error provider | valid ready chunks | build/query with timeout, HTTP failure and malformed payload | failed status and safe reason recorded; no fake success or automatic serving | automated fault injection | Unit, PG Integration | P1 | provider boundary | M |
| T1-04 | Provider dimension/partial batch failure | provider returns wrong dimension or fails item N | multi-chunk entry | embed batch, inspect embeddings and entry state | incompatible embeddings rejected; entry never serves a partial invalid generation | automated integration | PG Integration | P1 | AUD-004/AUD-005 | M |
| T1-05 | Storage unavailable | controlled read-only/missing adapter root | valid and invalid uploads | upload and retrieve during outage, then restore adapter | safe 503/error code, no DB-only phantom Asset, recovery succeeds | automated fault injection | Docker E2E | P1 | storage boundary | M |
| T1-06 | Database unavailable | disposable DB connection interrupted | P1-only and P2 requests | interrupt DB around transaction and retrieval | safe response, no credential leakage, subsequent recovery works | automated fault injection | Docker E2E | P1 | AUD-004 | L |
| T1-07 | Retrieval log write failure | log repository forced to fail | successful P1/P2/Unified queries | execute retrieval while logging fails | retrieval behavior follows documented availability policy; no secret leakage | unit + integration | PG Integration | P2 | AUD-010 | S |
| T1-08 | Independent branch failure | configurable P1/P2 branch timeout/error | P1-only, P2-only and mixed queries | fail each branch separately and both together | surviving branch is returned per contract; reason and latency are observable | automated fault injection | Unit, Docker E2E | P1 | Unified fallback | M |
| T1-09 | Process restart recovery | pending/running/ready/serving fixtures | unique jobs and entries | restart backend at each durable state; resume or re-query | persisted state is coherent; no ready-to-serving bypass | Docker smoke | Docker E2E | P1 | lifecycle audit | M |

## 4. T2 Concurrency and Idempotency

| Test ID | Target | Preconditions | Test data | Steps | Expected result | Automation | Environment | Priority | Related finding | Effort |
|---|---|---|---|---|---|---|---|---|---|---|
| T2-01 | Repeat publish/index/embed/serve | approved Snapshot and valid embedding provider | one governed source | issue duplicate requests serially and concurrently | one logical active version/generation; stable IDs or documented idempotent result | concurrency integration | PG Integration | P1 | AUD-005 | M |
| T2-02 | Archive versus embed | ready entry, controllable slow provider | one multi-chunk KA | race archive with embedding completion | archived object never becomes serving and is never retrievable | concurrency integration | PG Integration | P0 | AUD-005 | L |
| T2-03 | Serve versus version replacement | serving v1 and publishable v2 | distinct v1/v2 phrases | race serve/re-serve v1 with v2 activation | v1 remains invisible after replacement; exactly one active version | concurrency integration | PG Integration | P0 | AUD-005 | L |
| T2-04 | Review/publish contention | pending review | competing approve/reject/publish calls | execute barriers around row locks | only legal terminal decision wins; Snapshot lineage is immutable | concurrency integration | PG Integration | P1 | AUD-005 | M |
| T2-05 | Unified branch timeout boundary | deterministic latency near timeout | mixed query | repeat at below/equal/above timeout | stable degradation classification; no thread/task leak | parameterized unit + integration | Unit, Docker E2E | P1 | branch isolation | M |
| T2-06 | Run-scoped Eval isolation | corpus namespace support or disposable DB | identical Eval run executed three times | seed, evaluate, finalize/clean namespace, repeat | each run sees only intended IDs; counts and exact-ID metrics are stable | automated E2E | Docker E2E | P1 | AUD-003 | M |
| T2-07 | Retained-corpus negative control | intentionally retain earlier namespaces | two semantically competing runs | evaluate new namespace with and without namespace filter | isolated metric stays stable; global search impact is reported separately | automated E2E | Docker E2E | P1 | AUD-003 | M |

## 5. T3 Contract and Frontend

| Test ID | Target | Preconditions | Test data | Steps | Expected result | Automation | Environment | Priority | Related finding | Effort |
|---|---|---|---|---|---|---|---|---|---|---|
| T3-01 | OpenAPI contract snapshot | approved API compatibility policy | normalized OpenAPI JSON | compare methods, paths, required fields and response schemas to baseline | accidental breaking changes fail CI; additive change is reviewed | automated contract | Unit/CI | P1 | API audit | M |
| T3-02 | Legacy P1 endpoints | P2 disabled/unavailable | historical request fixtures | execute import/review/retrieve/Bad Case contracts | status, fields and default retrieval mode remain compatible | automated contract + E2E | PG Integration, Docker E2E | P0 | P1 seal | M |
| T3-03 | Agent opt-in matrix | flags independently controllable | four flag/request combinations plus branch failure | call CustomerOpsAgent and inspect actual mode/reason | only flag-on plus explicit opt-in activates Unified; failure returns P1 | automated contract | Unit, Docker E2E | P0 | Agent compatibility | S |
| T3-04 | Chinese P1 operator flow | production frontend and seeded P1 | import/review/RAG fixture | drive cleaning and approval in browser | controls perform real API mutations; status and errors are Chinese and accurate | browser E2E | Browser E2E | P1 | AUD-006 | L |
| T3-05 | Chinese P2 governed flow | full P2 APIs and real/mock profile explicitly labeled | upload through serve/archive fixture | drive every exposed operator action | UI reaches supported lifecycle or explicitly links to CLI; no stale M6 banner | browser E2E | Browser E2E | P1 | AUD-002/AUD-006 | L |
| T3-06 | Disabled roadmap surfaces | production frontend | P3/P4 and unavailable native multimodal entries | inspect and click navigation/cards | unavailable capabilities are visibly deferred and have no fake action | component + browser | Browser E2E | P2 | documentation drift | S |
| T3-07 | Error UX and safe detail | controlled API error catalogue | invalid file/state/provider/profile inputs | exercise forms and detail pages | actionable safe message, stable code, no internal stack/secret | component + browser | Browser E2E | P1 | AUD-002/AUD-006 | M |
| T3-08 | Health dependency presentation | backend with DB healthy/unhealthy | nested health payloads | load frontend and direct health endpoint in both states | frontend does not report fully connected when DB/pgvector is unavailable | component + E2E | Docker E2E | P2 | configuration audit | S |

## 6. T4 Performance and Repeat-Run Stability

| Test ID | Target | Preconditions | Test data | Steps | Expected result | Automation | Environment | Priority | Related finding | Effort |
|---|---|---|---|---|---|---|---|---|---|---|
| T4-01 | Retrieval latency breakdown | fixed corpus sizes and warm-up policy | P1/P2/mixed query sets | measure embed, P1, P2, fusion, trace and log latency | p50/p95 reported per component; threshold derived from measured baseline | benchmark smoke | Docker E2E | P2 | AUD-008 | M |
| T4-02 | Source-trace query count | SQL query instrumentation | top-k 1/5/20 | execute P2 and Unified retrieval | bounded documented query count; N+1 trend made visible | integration instrumentation | PG Integration | P2 | AUD-008 | M |
| T4-03 | Duplicate embedding calls | provider call counter | mixed Unified queries and repeated embed builds | execute build/retrieval paths | fingerprints skip duplicate builds; query embedding calls match intended branches | unit + integration | PG Integration | P2 | AUD-008/AUD-011 | S |
| T4-04 | pgvector plan/index threshold | generated corpora at several sizes | profile-compatible vectors | run `EXPLAIN (ANALYZE, BUFFERS)` before/after candidate index in disposable DB | evidence defines when ANN is warranted without recall regression | manual-to-automated benchmark | PG Integration | P2 | AUD-008 | L |
| T4-05 | Pagination and vector omission | large history | assets, KAs, index and embedding metadata | page through management APIs and inspect payload | stable bounds/order; no full vector returned | automated integration | PG Integration | P2 | performance audit | S |
| T4-06 | Eval metric semantics | isolated manifest with and without expected IDs | answer/no-answer/archive cases | calculate proxy hit, exact recall, MRR and leakage | keyword proxy never labeled recall; denominators and exclusions are explicit | unit + E2E | Unit, Docker E2E | P1 | AUD-003 | M |
| T4-07 | Repeat-run release comparison | isolated corpus fixture | at least five consecutive identical runs | seed/evaluate/finalize repeatedly | exact recall/MRR variance is zero or within an approved explained tolerance | automated E2E | Docker E2E | P1 | AUD-003 | M |
| T4-08 | Large history and archive selectivity | generated active/archived/version history | 1x, 10x and 100x current corpus | retrieve and inspect plan/latency/leakage | leakage remains 0; latency curve and index need are quantified | benchmark integration | PG Integration | P2 | AUD-008 | L |

## 7. Delivery Sequence and Gates

1. **M9.1 Release Safety and Eval Isolation**: T0-01 through T0-06, T2-06/T2-07, T4-06/T4-07 and the PostgreSQL foundation required by them. Authorization implementation must first pass T0-07 design/contract review.
2. **M9.2 State and Coupling Evidence**: T1 and T2 concurrency/rollback cases, schema/orphan inventory and configuration contract tests.
3. **M9.3 Frontend and Lifecycle Effectiveness**: T3 browser flows plus retry lifecycle decision.
4. **M9.4 Measured Retrieval Optimization**: T4 performance cases; change query/index behavior only after plans and thresholds are measured.

Every phase must retain P1 Harness 10/10, archive leakage 0, default Agent P1-only behavior, exact source trace, clean secret scans and unchanged sealed tags. A test phase may add disposable infrastructure, but must never clean or mutate a developer's retained Docker volumes.
