# P1-R2 Database Authority Release Report

## 1. Release conclusion

P1-R2 is complete. PostgreSQL is the only normal-runtime business truth source for P1. Legacy JSON remains on disk as immutable history and explicit reconciliation/migration input, but no longer participates in normal business reads, writes, merges, or database-failure fallback.

The user explicitly accepted the Stage E audit exception described in section 15. The audit record is retained; no baseline, preflight, or historical JSON was rewritten to hide it.

## 2. Goal and previous architecture

Before R2, P1 business paths mixed JSON persistence with database persistence. Some paths dual-wrote, some read or merged compatibility JSON, and database failure could expose JSON as an implicit authority. This made ownership ambiguous and made atomic rollback impossible across the two stores.

R2 establishes one rule: PostgreSQL owns current P1 business state. JSON is historical input only. Successful P1 API response shapes remain compatible, while unavailable database persistence fails closed.

## 3. Persistence Map

The frozen map has 14 entries:

- 10 losslessly reconciled and migratable entities: raw batch/message, sanitized batch/message, manual-cleaning record, knowledge candidate, review record, RAG chunk, retrieval log, and Bad Case.
- 3 legacy-audit-only entities with no lossless current P1 table representation: cleaning job, extraction job, and legacy RAG import receipt.
- 1 DB-only-by-design entity: RAG embedding.

Ignored non-business compatibility fields are explicitly declared by the map. IDs in reports are short hashes; reports contain no source content, credentials, or full sensitive identifiers.

## 4. Reconciliation contract and first result

The read-only reconciler inventories both stores, canonicalizes mapped business fields, validates references, and classifies each record as exact, JSON-only, DB-only, conflict, orphan, invalid, DB-only-by-design, or legacy-only-by-design. Conflict, orphan, and invalid are blockers for apply.

First authoritative result:

| Classification | Count |
|---|---:|
| EXACT_MATCH | 0 |
| JSON_ONLY | 53,705 |
| DB_ONLY | 1,205 |
| DB_ONLY_BY_DESIGN | 10 |
| LEGACY_ONLY_BY_DESIGN | 5,521 |
| CONFLICT | 0 |
| ORPHAN | 0 |
| INVALID | 0 |

There was no true conflict to arbitrate.

## 5. Backup and restore drill

Before apply, PostgreSQL was backed up to the ignored local recovery area. The dump was 1,015,557 bytes with SHA-256 `2abce97...`; an isolated restore drill completed successfully. The source database and development volume were not reset.

The legacy snapshot contained 24,961 files / 62,711,653 bytes with aggregate SHA-256 `4bca2561a389b6dff5e3db604f33561a38db2989a90bb9b0d8833d44d794f281`.

## 6. JSON-only backfill

The migration planner emitted only inserts. Apply inserted exactly 53,705 historical P1 records and performed zero updates and zero deletes. The operation was transaction-bound and idempotent; concurrent appearance of a planned ID is a blocker rather than an overwrite.

The 5,521 legacy-only workflow receipts remain historical records because there is no lossless current P1 table representation. The 1,205 DB-only records and 10 DB-only-by-design RAG embeddings remain explained database records, not missing JSON.

## 7. Second and final reconciliation

Final result:

| Classification | Count |
|---|---:|
| EXACT_MATCH | 53,705 |
| JSON_ONLY | 0 |
| DB_ONLY | 1,205 |
| DB_ONLY_BY_DESIGN | 10 |
| LEGACY_ONLY_BY_DESIGN | 5,521 |
| CONFLICT | 0 |
| ORPHAN | 0 |
| INVALID | 0 |

The final database reconciliation manifest is `910327ff27663838468243fbe56e44dc6f3c3cedd1bbcdd43cba8fa2597a5d0f`, matching the Stage B final manifest. The final no-write migration plan contains zero inserts. Direct database reads have parity with the mapped historical business records.

## 8. Runtime cutover and failure behavior

`backend/app/storage.py` is now the DB-only runtime facade. It opens the active SQLAlchemy session, delegates persistence to repositories, commits complete business operations, and rolls back on failure. Runtime JSON write, fallback, and merge counts are all zero.

Database persistence failures are normalized by the stable `P1PersistenceError` contract and returned as safe `503 P1_DATABASE_UNAVAILABLE`. Internal database URLs, hosts, credentials, driver messages, and raw exceptions are not exposed. There is no fallback to stale JSON.

Transaction coverage includes import batch/messages, cleaning results, manual cleaning, candidate/review changes, RAG state, retrieval audit, and Bad Case/draft paths. PostgreSQL rollback, concurrency, idempotency, outage, and absent-legacy-folder tests pass.

## 9. Legacy boundary

Historical JSON access is isolated in `backend/app/p1_legacy_storage.py`. Normal runtime code must not import it. The adapter is read-only and is used only by reconciliation, explicit migration tools, and isolated tests. The persistence-boundary checker prevents runtime reintroduction of file reads/writes.

All historical JSON remains present and its aggregate hash is unchanged. R2 did not delete, rewrite, compact, or regenerate it.

## 10. P1 complete flow

The isolated Docker test project used PostgreSQL, Alembic head `20260803_0001`, deterministic mock embedding, mock LLM settings, and no real Provider credentials. The ten-step Harness passed:

import → machine cleaning → manual cleaning → extraction/candidate generation → human approval → RAG sync → CustomerOps retrieval → Bad Case → Bad Case draft.

The database contained 28 public tables: 27 baseline business tables plus `alembic_version`. Legacy runtime file count was zero. Approved-only behavior, source trace, P1-only CustomerOps default, Unified=false, and non-auto-approved Bad Case draft behavior were preserved. The exact Docker project ended with zero containers, volumes, and networks.

## 11. PostgreSQL acceptance

An isolated, uniquely named PostgreSQL database was created on the healthy local test server, migrated to `20260803_0001`, and used for all `postgres_integration` tests. Result: **21 passed, 1 skipped, 1,216 deselected, 0 failed in 14.49s**. Temporary schemas were zero; connections were terminated and the exact test database was dropped. The development database and volume were untouched.

## 12. Backend, frontend, and platform gates

- Backend authoritative clean-export: **1,214 passed, 2 skipped, 22 deselected, 2 warnings, 0 failed in 85.70s**; compileall passed.
- Frontend authoritative content-equivalent run: npm ci completed for 297 packages; **6 files / 59 tests passed**; typecheck and production build passed; lint had 0 errors and one existing P1 hook warning.
- Docker P1 Harness: **10 passed, 0 failed, 0 skipped**; Legacy runtime files 0.
- Persistence boundary and CI contract safety: PASS.
- Alembic revision, Health, Capabilities, Auth/RBAC, OpenAPI, Secret scan, conflict-marker scan, and `git diff --check`: PASS.

The frontend tree had no diff from its authoritative validation HEAD, so the completed frontend run remains content-identical evidence.

## 13. Test-failure audit and corrections

Stage E did not hide failed attempts. Early clean-export runs exposed three test-harness problems: a missing/incorrect SQLite migration variable, global `sqlite:///:memory:` environment leakage from `test_database_foundation`, and stale collection-time `SessionLocal` imports. A broad live-engine workaround was evaluated and removed. The final fix restores shared module/environment state in teardown, uses runtime database bindings in affected assertions, and initializes P1 schema only in test fixtures. The exact failed nodes passed before each corrected full run. The final authoritative full result is the zero-failure result in section 12.

The Docker test composition also exposed an invalid `DATAHUB_ENV=docker-test` and an obsolete 20-table initializer. It now uses valid `DATAHUB_ENV=test` and the same Alembic migration gate as production; the corrected isolated flow passed.

## 14. Data protection and cross-phase regression

The only permitted bulk business-data increase was the 53,705 insert-only P1 historical backfill. There were no deletes, status rewrites, review-decision rewrites, RAG rebuild side effects, or Provider-generated business data.

P2 and P3 product semantics and schema were not changed. P3 remains exactly seven business tables. CustomerOpsAgent remains P1-only by default and Unified remains false by default. P2 real OCR/Caption/Vision and durable cloud storage are still not delivered. P3-M9 and P4 have not started.

## 15. Accepted audit exception

During overlapping Stage E activity, `retrieval_logs` changed from 968 to 969 and its selected-data hash changed accordingly. One real SiliconFlow query embedding had been issued by the overlapping acceptance activity and the existing audit contract persisted the row. The user explicitly accepted this exception.

The row is retained. No deletion, rewrite, counter adjustment, preflight rewrite, or historical JSON mutation was performed. Two stable post-event snapshots matched. The other 26 business tables, 107-index fingerprint, 324-constraint fingerprint, and exact seven P3 tables remained stable. This exception does not claim delivery of a real Provider business capability.

## 16. Git and release chain

The release chain uses five independent commits and annotated tags:

1. R2.1 reconciliation tooling — `p1-r2.1-storage-reconciliation`.
2. R2.2 insert-only historical backfill — `p1-r2.2-database-backfill`.
3. R2.3 runtime database authority — `p1-r2.3-database-authority`.
4. R2.4 legacy persistence isolation — `p1-r2.4-persistence-boundary`.
5. R2 closure — `p1-r2-database-authority-release`.

Tag objects are annotated and their peeled commits are verified after push. Historical tags are not moved.

## 17. Known limitations and next Goal entry condition

This is a local release acceptance, not a claim of complete production deployment hardening. Render P2 persistence remains blocked without durable Asset storage. OIDC/human identity is not delivered. P2 real multimodal Providers, P3-M9, and P4 remain outside scope.

The next Goal may begin only from a clean `main` equal to `origin/main`, with all five R2 commits/tags published, the accepted audit record retained, and no temporary database/container/network/volume/clean-export resource remaining.
