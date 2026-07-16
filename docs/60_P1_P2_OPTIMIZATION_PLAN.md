# P1/P2 Post-Release Optimization Plan

This plan is derived only from confirmed audit evidence in `58_P1_P2_POST_RELEASE_COMPLETENESS_AND_COUPLING_AUDIT.md`. It proposes additive maintenance releases; it does not modify or reinterpret the sealed P1/P2 release tags.

## 1. Principles

- One problem class and no more than two core capabilities per phase.
- Safety and repeatable evidence precede refactoring or performance work.
- Preserve P1 `rag_chunks`, `rag_embeddings`, the old retrieval endpoint and default Agent behavior.
- Prefer additive, reversible changes. Destructive migrations require a separate approval gate.
- Each item exits only with automated tests, Docker evidence, documentation and a rollback path.

## 2. A — Must Fix Before Broader Exposure

### OPT-001 — Administrative authentication and authorization boundary

| Field | Plan |
|---|---|
| Related finding | AUD-001 |
| Goal | Prevent anonymous mutation of governance, review, publish, serve, archive and rebuild operations. |
| Current problem | Validation and CORS exist, but no trusted identity or RBAC boundary exists; reviewer strings and client headers are not authentication. |
| Proposed change | First publish an authorization ADR and route inventory; then add a common dependency/middleware and least-privilege roles without changing public retrieval response contracts. |
| Allowed modules | New auth module, route dependencies, config contract, auth tests and deployment docs. |
| Forbidden changes | P1/P2 index schemas, retrieval ranking, sealed tags, default Agent strategy. |
| Compatibility impact | Read-only/public endpoints must remain explicitly classified; old administrative clients need a documented transition window. |
| Migration impact | None initially; identity persistence, if needed, requires a separate additive migration review. |
| Required tests | T0-04, T0-05, T0-07, T3-01 through T3-03; P1 Harness and full Docker lifecycle. |
| Rollback plan | Disable the new enforcement flag only within a time-boxed local migration mode; retain route inventory and audit logs. |
| Priority / Scope / Phase | P1 / L / M9.1A Security Gate |
| Exit criteria | Anonymous writes are denied, role matrix passes, no secret leakage, and P1 compatibility remains 10/10. |

### OPT-002 — Run-scoped Eval corpus isolation

| Field | Plan |
|---|---|
| Related finding | AUD-003 |
| Goal | Make P2 and Unified exact-ID metrics stable and comparable across repeated runs. |
| Current problem | Acceptance leaves valid historical Assets/Knowledge Assets; semantically competing chunks can consume finite top-k/RRF slots, moving exact recall from historical 0.8571 to 0.7143 despite candidate improvement and zero leakage. |
| Proposed change | Add a run namespace to acceptance metadata/manifests, an Eval-only namespace filter or disposable database fixture, and idempotent finalization. Keep a separate retained-corpus robustness test. |
| Allowed modules | Acceptance/Eval scripts, sample schema documentation, test fixtures, optional additive metadata use. |
| Forbidden changes | Production ranking solely to satisfy IDs, deletion of user corpus/volumes, raw-score cross-index fusion. |
| Compatibility impact | Existing manifests remain readable; new fields are optional until migration. |
| Migration impact | None if metadata is reused; a new table/column requires a later schema gate and is not preferred. |
| Required tests | T2-06, T2-07, T4-06, T4-07 and archive leakage suite. |
| Rollback plan | Run the prior global-corpus Eval mode and preserve both reports; remove only the namespace selector. |
| Priority / Scope / Phase | P1 / M / M9.1B Eval Isolation |
| Exit criteria | Five identical isolated runs produce stable denominators and exact metrics; leakage stays 0 and candidate remains no worse than control. |

### OPT-003 — No-answer confidence and refusal gate

| Field | Plan |
|---|---|
| Related finding | AUD-015 |
| Goal | Prevent irrelevant low-confidence evidence from being presented as an answerable retrieval result. |
| Current problem | The audit no-answer query returned five evidence items; P2 has a threshold but no calibrated cross-mode refusal contract. |
| Proposed change | Label no-answer/near-negative sets, measure score/rank distributions per source, define retrieval abstention semantics, and expose a safe reason without changing RRF to compare raw scores. |
| Allowed modules | Eval datasets/scripts, versioned Unified/P2 response semantics, retrieval policy module and tests. |
| Forbidden changes | Default Agent switch, uncalibrated arbitrary threshold, direct P1/P2 cosine comparison. |
| Compatibility impact | Additive response reason; existing result fields retained. |
| Migration impact | None. |
| Required tests | T4-01, T4-06, no-answer contract and P1/P2 regression. |
| Rollback plan | Disable the abstention policy flag and return prior ranked results while retaining metrics. |
| Priority / Scope / Phase | P1 / M / M9.1C Retrieval Safety |
| Exit criteria | Approved no-answer set meets an explicit false-evidence bound without unacceptable answer recall loss. |

## 3. B — Recommended Fixes

### OPT-004 — PostgreSQL lifecycle, failure and concurrency suite

| Field | Plan |
|---|---|
| Related finding | AUD-004, AUD-005, AUD-007 |
| Goal | Exercise real pgvector SQL, locks, transactions and cross-table invariants in CI. |
| Current problem | The 379-test suite passes mainly on SQLite/mocks; Docker runners cover positive real paths but not rollback and races. |
| Proposed change | Add a disposable PostgreSQL/pgvector test profile, transaction fault hooks and small deterministic concurrency cases. |
| Allowed modules | Test infrastructure, fixtures and test-only provider/storage adapters. |
| Forbidden changes | Developer retained volumes, destructive production migrations, weakening application gates. |
| Compatibility impact | None to runtime contracts. |
| Migration impact | Test database only. |
| Required tests | T0-01 through T0-03, T1-01 through T1-09, T2-01 through T2-05. |
| Rollback plan | Make PG suite an explicit CI job until stable; unit suite remains available. |
| Priority / Scope / Phase | P1 / L / M9.2A State Safety |
| Exit criteria | Real rollback/race tests pass repeatedly and no orphan/dual-active/archived-visible state is observed. |

### OPT-005 — Frontend truthfulness and critical-path E2E

| Field | Plan |
|---|---|
| Related finding | AUD-002, AUD-006 |
| Goal | Align the Chinese UI with released capabilities and prove its mutations. |
| Current problem | Home disables P2, the P2 banner says M6, and Extraction/Embed/Serve have no UI action; no frontend tests exist. |
| Proposed change | First fix release/status copy and add browser coverage; then expose only approved missing lifecycle actions with confirmation and safe errors. |
| Allowed modules | Existing P1/P2 pages, API client, component/browser tests and UI docs. |
| Forbidden changes | New RAG feature, P3/P4 activation, database-aware UI shortcuts, bypassing Review/Snapshot. |
| Compatibility impact | Additive UI only; backend contracts stay stable. |
| Migration impact | None. |
| Required tests | T3-04 through T3-08 plus production build. |
| Rollback plan | Hide the new action while retaining corrected status copy and API tests. |
| Priority / Scope / Phase | P2 / M / M9.3A Operator UX |
| Exit criteria | Browser can complete every supported governed step or clearly directs to a documented CLI; no stale phase claim remains. |

### OPT-006 — Executable environment/configuration contract

| Field | Plan |
|---|---|
| Related finding | AUD-009, AUD-011 |
| Goal | Make every effective runtime variable documented, typed and consistently resolved. |
| Current problem | `P2_RETRIEVAL_MIN_SCORE` is undocumented in Compose/template; several advertised variables are not read; embedding config is resolved independently across P1/P2. |
| Proposed change | Inventory variables from code, publish a typed resolved startup summary with secrets redacted, document ownership/defaults and mark/remove inert knobs. |
| Allowed modules | Config module, `.env.example`, Compose pass-through, startup diagnostics and tests. |
| Forbidden changes | Printing secret values, silent default changes, profile bypass. |
| Compatibility impact | Deprecation notices precede removal of inert variables. |
| Migration impact | None. |
| Required tests | Config snapshot, mock/real profile matrix, secret scan and Docker startup. |
| Rollback plan | Restore prior environment parsing while keeping the generated inventory. |
| Priority / Scope / Phase | P2 / M / M9.2B Config Contract |
| Exit criteria | Code, template and Compose variable sets reconcile; P1/P2 resolved profiles are explicit and compatible. |

## 4. C — Optional, Evidence-Gated Optimization

| Optimization ID | Related finding | Goal and proposed change | Allowed modules | Forbidden changes | Compatibility / migration | Required tests | Rollback | Priority / Scope / Phase | Exit criteria |
|---|---|---|---|---|---|---|---|---|---|
| OPT-007 | AUD-008 | Measure plans/corpus growth; add profile-compatible pgvector ANN index only when EXPLAIN and recall justify it; replace full serving-row profile pre-scan with a bounded aggregate/metadata gate. | P2 repository, additive migration, benchmarks | unmeasured index, raw-score fusion, P1 table changes | query contract unchanged; additive index migration | T4-01/02/04/08, recall/leakage | drop additive index and restore query | P2 / M / M9.4A | measured p95 improvement with unchanged recall/leakage |
| OPT-008 | AUD-010 | Formalize retrieval log namespace, reader filters, indexes and retention while keeping one table initially. | logging repository, metadata schema, docs/tests | coupling log failure to retrieval availability | additive metadata/index only | T1-07, all-mode trace tests | revert readers/index | P3 / S / M9.2C | no cross-mode trace and bounded log query plan |
| OPT-009 | AUD-011 | Introduce immutable resolved embedding config objects shared intentionally by provider construction, with per-index compatibility validation. | config/provider composition | changing stored profiles or old embeddings | internal additive refactor, no data migration | config/profile/real-mode regression | restore old resolver | P3 / M / M9.2B | one documented resolution path and unchanged P1/P2 results |
| OPT-010 | AUD-012 | Move P1/P2 extraction job compatibility dispatch from `main.py` behind a small additive coordinator/router after contract characterization. | composition root, compatibility service/tests | old path removal, response drift | internal refactor | OpenAPI and legacy path contract | restore direct dispatch | P3 / S / M9.2D | main composition shrinks and contracts are byte/field compatible |
| OPT-011 | AUD-013 | Decide whether retry is a supported operator lifecycle; either expose an authorized idempotent retry route or formally narrow the state model in a future migration. | Extraction service/routes/UI/tests or later migration | deleting state before history audit | additive route preferred; schema change separately gated | retry failure/recovery/idempotency | disable route | P3 / S / M9.3B | retry is reachable and governed, or documented as compatibility-only |
| OPT-012 | AUD-014 | Prove callers, then remove one obsolete class at a time: Advanced page, inert envs, uncalled helpers, redundant scripts. | one candidate class per commit | bulk cleanup, removal of compatibility code without telemetry | possible docs/client impact reviewed per item | import/route/CLI/frontend build | revert individual cleanup commit | P3 / S / M9.3C | zero proven caller and all contracts/tests pass |

## 5. D — Preserve Deliberately

| Decision | Reason and protection |
|---|---|
| Keep P1 and P2 physical chunk/embedding tables separate | Isolation is confirmed and enables independent lifecycle, profile gates and rollback. Do not consolidate tables merely for convenience. |
| Keep the old P1 endpoint and default Agent P1-only | Compatibility and independent P1 operation are release invariants. Unified remains explicit opt-in. |
| Keep rank-level RRF | Cross-index raw cosine scores are not calibrated; rank fusion is the correct current boundary. |
| Keep explicit ready-to-serving and archive visibility gates | Runtime evidence proves zero recall before serve and after archive. |
| Keep shared `retrieval_logs` for now | Namespaces and ID prefixes work and P1 trace lookup rejects P2/Unified IDs. Optimize readers/retention before considering a new table. |
| Keep application source-trace double validation | It is a valuable safety layer even if future migrations add foreign keys. |
| Keep feature flags default off | Default Agent behavior and rapid rollback depend on this. |

## 6. E — Deferred by Product Scope

Do not implement these in maintenance phases unless a new product gate explicitly authorizes them: native multimodal/image embeddings, image-to-image retrieval, CLIP, multimodal reranking, real OCR/Caption/Vision providers, S3/R2/OSS adapters, Render Persistent Disk and online P2 acceptance, default CustomerOpsAgent Unified cutover, P3/P4, model fine-tuning, complex asynchronous index clusters and large-scale performance testing.

## 7. Recommended Small-Phase Roadmap

1. **M9.1 Release Safety and Eval Isolation**: OPT-001 design/guardrails plus OPT-002; land OPT-003 only after the labeled no-answer baseline is approved. No coupling refactor.
2. **M9.2 State and Coupling Evidence**: OPT-004 and OPT-006; optional small OPT-008/009/010 changes only after tests characterize behavior.
3. **M9.3 Operator Effectiveness**: OPT-005, then make a separate retry/obsolete-code decision (OPT-011/012).
4. **M9.4 Measured Retrieval Performance**: OPT-007 only when corpus-size evidence meets an agreed threshold.

No P0 defect was confirmed, so the sealed releases should not be rewritten. Start maintenance with safety tests and Eval isolation, require a normal additive commit/release trail, and keep every change independently reversible.
