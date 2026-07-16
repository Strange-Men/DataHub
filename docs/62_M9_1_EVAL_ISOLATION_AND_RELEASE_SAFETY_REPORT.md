# M9.1 Eval Isolation and Release Safety Report

## 1. Scope and decision

M9.1 is an additive maintenance change on top of `dfbeb9f6d52c29c9bebb703b9e79cd490d1efb74`. It isolates evaluation evidence without changing P1/P2 ranking, RRF, the sealed P1 endpoint, the CustomerOpsAgent default, database schemas, or retained Docker volumes. Local Docker acceptance is **PASS**. Render Deployment Acceptance remains **BLOCKED** by the existing Persistent Disk limitation.

## 2. Original metric contamination

Repeated P2 acceptance runs retained valid, semantically overlapping Assets and Knowledge Assets. A later Unified run could therefore lose a current exact ID from a finite candidate/RRF window even while keyword coverage improved and archived leakage stayed zero. The audit observed Unified exact recall move from approximately `0.8571` to `0.7143`. This was an evaluation-corpus identity problem, not P1/P2 index pollution or a production ranking defect.

## 3. Run-scoped corpus design

`scripts/eval_run_scope.py` defines the backward-compatible scope contract:

- `run_id`: 6-96 safe identifier characters;
- `namespace`: exactly `datahub-eval:<run_id>`;
- `trace_id` and `creator`;
- version `p1-p2-m9.1-run-scope-v1`;
- explicit `test_corpus=true` cleanup guard.

P2 upload accepts an optional validated `eval_run_scope`. The value is stored in existing Asset `metadata_json`, propagated to the published Knowledge Asset, and used only when an Eval request explicitly supplies `evaluation_scope`. Normal retrieval omits it and retains the pre-M9.1 global-corpus behavior.

## 4. Propagation and manifest chain

The scope flows through:

1. P2 Local Acceptance upload and generated runtime manifest;
2. Asset metadata to approved Snapshot publication and Knowledge Asset metadata;
3. P2 retrieval repository/service filtering;
4. Unified P2 adapter while the P1 control remains unfiltered;
5. Unified Eval and CustomerOpsAgent opt-in smoke;
6. current-run exact-ID filtering and metrics.

P1 Harness uses a unique trace-derived source name, conversation/message identifiers and batch content for each run. It does not write P2 metadata.

Runtime manifests are written only below the ignored `.local-data/` host/runtime volume. They record the scope and the exact current-run Asset, Knowledge Asset and Chunk identifiers. No runtime ID or manifest is tracked by Git.

## 5. Cleanup safety boundary

Cleanup is opt-in through `--cleanup-manifest`. It refuses a legacy or malformed manifest, requires `creator=run_p2_local_acceptance` and `test_corpus=true`, and operates only on the manifest's explicit `cleanup_knowledge_asset_ids`. It calls the public archive lifecycle; it does not delete database rows, files, embeddings, volumes, or a broad namespace.

Three accepted runs were cleaned independently. Each archived four explicitly listed active test Knowledge Assets and reported `deleted_records=0`. Non-test P2 counts and states were identical before and after cleanup:

| Record class | Before | After |
|---|---:|---:|
| non-test Assets / uploaded | 24 | 24 |
| non-test Knowledge Assets / active | 13 | 13 |
| non-test Knowledge Assets / archived | 13 | 13 |
| P1 chunks / embeddings | 8 / 8 | 8 / 8 |

All 48 accumulated test Knowledge Assets were archived after the final cleanup. P2 physical chunk/embedding rows were retained by design.

## 6. Legacy compatibility

Manifests without `run_scope` remain readable and use the historical global-corpus metric view. `--no-run-scope-isolation` provides an explicit negative-control view even when a scoped manifest is present. Existing request fields and response fields remain valid; the new evaluation fields are optional. RRF and route-local ranking were not changed.

## 7. Exception reload compatibility fix

The first clean-export run collected 387 tests and produced one failure after another test reloaded `app.asset_service`. The called function raised the correct `AssetValidationFailure` and stable code, but the test held the pre-reload class object, so `pytest.raises(old_class)` did not match the new class identity.

The final fix imports the module object and resolves `asset_service.AssetValidationFailure` at test execution time. It does not catch `Exception`, remove an assertion, or weaken behavior. The test still requires the exact business exception and `EVAL_RUN_SCOPE_INVALID`.

## 8. Automated gates

| Gate | Result |
|---|---|
| M9.1 focused suite | 37 passed in 1.79 s |
| clean-export backend suite | 387 passed, 44 warnings in 112.77 s |
| Python compileall | PASS |
| frontend TypeScript/Vite build | PASS; 49 modules transformed |
| `git diff --check` | PASS |
| known local secret value scan | zero matches |

The authoritative source was an export under ignored `.local-data/m9.1-clean-export-20260717-000523`, built from `HEAD` plus the 22 preserved M9.1 worktree paths. An initial invocation from the export's `backend/` directory stopped during collection because the new namespace helper was not on the root import path. The authoritative rerun from the export root collected and passed all 387 tests; no application test had run in the incorrect invocation.

## 9. Docker runtime evidence

- PostgreSQL/pgvector, backend and frontend: healthy.
- Embedding provider: SiliconFlow `Qwen/Qwen3-Embedding-4B`, dimension 1536.
- P1 Pipeline Harness: 10/10 PASS; `customerops_vector_retrieval`; fallback false.
- P2 Acceptance: Ready-before-Serve zero recall, Serve hit, Archive zero recall, physical embedding retained, superseded version zero recall.
- Agent smoke: legacy/default strategy P1; explicit opt-in strategy Unified with P1+P2 evidence; fallback false; archived leakage zero.
- Final runtime flags: Unified, P2, Shadow and Agent switches all restored to `false`.

## 10. Three-run Eval stability

Runs used independent IDs and namespaces:

- `p2-m91-20260717-001-r1`
- `p2-m91-20260717-001-r2`
- `p2-m91-20260717-001-r3`

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| P2 query hit@5 | 1.0 | 1.0 | 1.0 |
| P2 candidate recall@5 | 1.0 | 1.0 | 1.0 |
| P2 MRR | 0.95 | 0.95 | 0.95 |
| P2 duplicate Asset rate | 0.0 | 0.0 | 0.0 |
| P2 archived leakage | 0 | 0 | 0 |
| Unified candidate query hit@5 | 1.0 | 1.0 | 1.0 |
| Unified candidate exact recall@5 | 1.0 | 1.0 | 1.0 |
| Unified candidate MRR | 0.6071 | 0.6071 | 0.6071 |
| Unified source coverage | 1.0 | 1.0 | 1.0 |
| Unified duplicate Asset rate | 0.0 | 0.0 | 0.0 |
| Unified archived leakage | 0 | 0 | 0 |
| historical P2 results filtered | 3 | 3 | 3 |

Current expected IDs remained stable while old-run P2 candidates were removed from the metric view. P1 control candidates were retained. No ranking or RRF adjustment was used to obtain these results.

## 11. Release safety gates

- Unreviewed content remains excluded by the existing Review/Snapshot/Serve gates and the passing full regression suite.
- Archived and superseded content had zero recall in Acceptance, P2 Eval, Unified Eval and Agent smoke.
- P1 and P2 physical indexes remained separate; cleanup did not change P1 counts.
- The legacy and default Agent paths remained P1-only; Unified required both server flags and explicit request opt-in.
- Runtime artifacts, build output and clean exports are ignored.
- The only generic secret-scan match was an intentional redaction-test sentinel; no real `.env` secret value matched a changed file.

## 12. Known limitations and next entry

M9.1 does not add authentication/RBAC, frontend governance workflow changes, reliability/concurrency infrastructure, or a calibrated no-answer gate. The Unified no-answer sample still returned five evidence rows; this is the already documented calibration gap and no threshold was guessed in M9.1. Native multimodal retrieval, cloud object storage, Render Persistent Disk, P3 and P4 remain out of scope.

M9.2 may begin later with an authentication ADR and route/role inventory. It has **not started** as part of this report.
