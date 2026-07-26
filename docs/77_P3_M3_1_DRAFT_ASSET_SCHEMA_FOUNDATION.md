# P3-M3.1 Draft Asset Schema Foundation

## 1. Decision and scope

P3-M3.1 passes its schema-foundation gates. It adds exactly:

1. `reuse_asset_versions`
2. `reuse_asset_version_sources`

This stage contains no draft persistence Repository, Service, API, deterministic generator, Provider, review, approval, publish, export or frontend capability. P3-M3 as a whole is not complete.

## 2. Migration strategy

The project continues its frozen additive database strategy:

- models register on the existing SQLAlchemy `Base`;
- `Base.metadata.create_all(checkfirst)` creates missing tables;
- repeated startup is idempotent;
- application rollback may leave additive tables in place;
- no Alembic or destructive down migration is introduced;
- no P1/P2 table, column, constraint or data row is changed.

## 3. `reuse_asset_versions`

Responsibility: store one versioned P3 output payload and its deterministic source-manifest identity.

| Field | Contract |
| --- | --- |
| `id` | stable primary key |
| `project_id` | required FK to `reuse_projects.id`, `ON DELETE RESTRICT` |
| `asset_type` | frozen five-value enum |
| `version_number` | positive integer |
| `status` | frozen AssetVersion lifecycle enum |
| `generation_mode` | M3.1 only accepts `deterministic_template` |
| `template_key`, `template_version` | required deterministic template identity |
| `content_payload` | required JSON payload |
| `content_hash` | required nonblank payload fingerprint |
| `source_manifest_hash` | required nonblank frozen-source-set fingerprint |
| `idempotency_key` | required globally unique generation identity |
| `created_by_role`, `request_id` | v1 role/request audit; no user Token |
| `created_at`, `updated_at` | UTC lifecycle timestamps |
| `approved_at`, `published_at`, `superseded_at`, `archived_at` | nullable future lifecycle evidence |
| `failure_code`, `failure_message` | nullable safe failure metadata |

Constraints:

- `(project_id, asset_type, version_number)` is unique;
- `idempotency_key` is unique;
- version is at least 1;
- template identity, content hash and source-manifest hash cannot be blank.

The table has no Token, Token Hash, API key, password, vector or P1/P2 foreign key.

## 4. Asset types

Frozen P3 v1 asset types:

- `training_material`
- `sop`
- `service_script`
- `qa_bank`
- `sft_dataset`

The type is stored as a checked string enum for SQLite/PostgreSQL consistency.

## 5. AssetVersion status

Frozen values:

- `generating`
- `generated`
- `pending_review`
- `needs_revision`
- `approved`
- `published`
- `rejected`
- `failed`
- `superseded`
- `archived`

M3.1 stores a valid enum value but implements no transition logic. Generated does not imply approved; approved does not imply published. Publish/supersede/archive behavior remains a later stage.

## 6. Generation mode

The only accepted M3.1 value is:

`deterministic_template`

`llm_draft` is reserved for a separately authorized future stage and is intentionally not present in the enum. A model/database write using it fails. No real Provider, LLM request, prompt or Secret exists in M3.1.

## 7. `reuse_asset_version_sources`

Responsibility: freeze the exact governed source evidence used by one AssetVersion.

| Field | Contract |
| --- | --- |
| `id` | stable primary key |
| `asset_version_id` | required FK to `reuse_asset_versions.id`, `ON DELETE RESTRICT` |
| `source_item_id` | required FK to `reuse_source_items.id`, `ON DELETE RESTRICT` |
| `source_type`, `source_id`, `source_version` | copied governed identity |
| `source_fingerprint` | immutable content fingerprint used by this version |
| `approved_review_id` | nullable approved Review reference |
| `snapshot_id` | nullable immutable governance Snapshot reference |
| `knowledge_asset_id` | nullable P2 Knowledge Asset reference |
| `lineage_manifest_hash` | required nonblank lineage fingerprint |
| `source_trace_snapshot` | required immutable JSON trace snapshot |
| `created_at` | binding creation time |

`(asset_version_id, source_item_id)` is unique. The table references only P3-owned tables physically; P1/P2 identifiers remain logical trace fields.

## 8. Snapshot immutability

The association row copies source identity and evidence rather than reading live values for historical output:

- later `source_stale=true` does not change the snapshot;
- later `removed_at` does not delete or change the snapshot;
- later SourceItem fingerprint/Trace changes do not rewrite the snapshot;
- AssetVersion and its source binding are protected from parent physical deletion by RESTRICT.

Creation of a version and all source snapshots must be one transaction in a later Repository/Service stage. M3.1 defines the constraints but does not implement that transaction.

## 9. SQLite evidence

Focused result:

`35 passed, 1 skipped`

Coverage includes:

- exact current P3 table inventory and repeated `create_all`;
- five asset types;
- ten frozen statuses;
- deterministic mode acceptance and `llm_draft` rejection;
- Project/version/source foreign keys;
- Project/type/version and idempotency uniqueness;
- nonblank hashes and positive version;
- JSON payload and trace round trip;
- duplicate binding rejection;
- snapshot immutability after SourceItem stale/removal/change;
- no Secret/vector/P1/P2 FK fields.

The one skip is the explicit PostgreSQL integration case when no test URL is present.

## 10. PostgreSQL evidence

An isolated `datahub-m31-test` PostgreSQL stack used an ephemeral test-only password, database, port, network and volume. Result:

`4 passed`

It verified:

- M3.1 Project FK, two binding FKs and all `ON DELETE RESTRICT` behavior;
- Project/type/version uniqueness;
- AssetVersion/source binding uniqueness;
- rollback after constraint failure;
- retained M2 normalized source uniqueness, repository idempotency and activation failure atomicity.

The exact test container, network and volume were removed. The development Docker stack and volumes were not stopped or reset.

## 11. Regression evidence

| Gate | Result |
| --- | --- |
| M3.1 SQLite focused | 35 passed, 1 skipped |
| M2 Model/Repository/Service + M1 core | 144 passed, 3 skipped |
| isolated PostgreSQL M3.1 + key M2 | 4 passed |
| compileall | PASS |
| Secret scan | PASS |
| `git diff --check` | PASS |

The goal's single authoritative clean-export full backend run already passed at P3-M2 closure with `653 passed, 8 skipped, 44 warnings`. M3.1 did not repeat the full suite because it changed only the scoped P3 model and model-regression expectations; no common database engine, API or P1/P2 implementation changed.

## 12. Explicit non-deliverables

M3.1 does not add:

- `reuse_reviews`
- `export_jobs`
- `export_artifacts`
- draft Repository or Service
- create/read/generate API
- deterministic template registry or generator
- LLM/Provider support
- review, approve, publish, supersede or archive operations
- JSONL/CSV export
- P3 frontend

## 13. P3-M3.2 entry gate

P3-M3.2 has not started. It requires a separate explicit instruction after:

1. M3.1 focused and PostgreSQL tests pass;
2. compileall, Secret and diff checks pass;
3. only M3.1 model/test/status files are committed;
4. the M3.1 commit and annotated tag are pushed;
5. the worktree is clean.

Any M3.2 work must use these constraints, keep `deterministic_template` as the only generation mode and must not enter review, publish or export scope.
