# P3-M2 Reuse Project and Governed Source Release Report

## 1. Release decision

P3-M2 passes its local Docker release gates. The stage delivers a governed Project and source-selection foundation on top of the frozen P3-M1 eligibility truth source. It does not implement draft assets, review, publish, export, frontend workflow or Provider integration.

## 2. Stage composition

| Stage | Capability | Commit baseline |
| --- | --- | --- |
| P3-M2.1 | `reuse_projects` and `reuse_source_items` schema foundation | `d1360a4` |
| P3-M2.2 | Deterministic Project/Source Repository | `c1f45d8` |
| P3-M2.3 | Lifecycle, eligibility evidence and stale orchestration | `27e8f14` |
| P3-M2.4 | Project/Source API and centralized RBAC | `a85ca32` |
| P3-M2.5 | Stage acceptance and release evidence | this release commit |

Each sub-stage was independently tested, committed, tagged and pushed before the next started.

## 3. Final data model

P3-M2 adds exactly two P3-owned tables:

- `reuse_projects`: Project identity, name/description, `draft|active|archived` status, role/request audit, idempotency key and timestamps.
- `reuse_source_items`: governed source identity, normalized source version, content fingerprint, eligibility policy, Review/Snapshot/Knowledge Asset lineage, immutable Source Trace, role/request audit, logical removal and stale state.

`reuse_source_items.project_id` references `reuse_projects.id` with `ON DELETE RESTRICT`. The source identity uniqueness key is Project + source type + source ID + normalized version key. No foreign key or field was added to a P1/P2 table.

## 4. Project lifecycle

The frozen lifecycle is:

`draft -> active -> archived`

- `draft`: metadata and source selection may change; current sources may be revalidated.
- `active`: source selection is frozen; read and revalidation remain available.
- `archived`: terminal and retained; metadata/source mutation and reactivation are forbidden.

No reverse or skipped transition is accepted.

## 5. Governed source selection

An add-source request contains only Project ID, source type, source ID, optional source version/fingerprint guard, actor role and request ID. The Service:

1. loads the Project through Repository;
2. requires `draft`;
3. calls the P3-M1.1 eligibility core;
4. rejects an ineligible result as a stable business error;
5. derives all evidence from the decision;
6. persists through Repository.

The caller cannot declare approval, archive/current state, Review/Snapshot IDs, Knowledge Asset ID, lineage completeness, Source Trace or stale state.

## 6. Evidence and idempotency

Persisted evidence includes:

- governed source type and ID;
- source version and content fingerprint;
- eligibility policy version;
- approved Review ID;
- Snapshot ID;
- Knowledge Asset ID;
- normalized Source Trace snapshot;
- lineage manifest hash.

Identical Project/source identity and evidence replay returns the existing row. Different fingerprint, version, Review, Snapshot, Knowledge Asset or lineage under the same identity returns a conflict. A logically removed identity is not silently restored.

## 7. Revalidation and stale handling

Revalidation calls M1.1 again with the saved identity and fingerprint guard. It never trusts or overwrites the old evidence.

- unchanged eligible evidence remains valid;
- ineligible evidence becomes `source_stale=true` with the M1 reason code;
- eligible but changed version/fingerprint/Review/Snapshot/Knowledge Asset/lineage becomes stale;
- logically removed sources are skipped;
- stale evidence is retained for audit and cannot be silently replaced.

No automatic background scan is included.

## 8. Activation atomicity

Activation requires:

- at least one non-removed source;
- no already-stale current source;
- at most the bounded 100-source validation set;
- fresh eligibility and exact evidence match for every source.

The Service performs all checks before persisting `active`. Any failure leaves the Project in `draft`; no partial active state is possible. Sources found invalid during validation may be conservatively marked stale while the Project remains draft.

## 9. Public API

Project endpoints:

- `POST /api/p3/reuse-projects`
- `GET /api/p3/reuse-projects`
- `GET /api/p3/reuse-projects/{project_id}`
- `PATCH /api/p3/reuse-projects/{project_id}`
- `POST /api/p3/reuse-projects/{project_id}/activate`
- `POST /api/p3/reuse-projects/{project_id}/archive`

Source endpoints:

- `POST /api/p3/reuse-projects/{project_id}/sources`
- `GET /api/p3/reuse-projects/{project_id}/sources`
- `GET /api/p3/reuse-projects/{project_id}/sources/{source_item_id}`
- `DELETE /api/p3/reuse-projects/{project_id}/sources/{source_item_id}`
- `POST /api/p3/reuse-projects/{project_id}/sources/{source_item_id}/revalidate`
- `POST /api/p3/reuse-projects/{project_id}/sources/revalidate`

Lists are paginated at 1–100. Project revalidation is capped at 100. `DELETE` is logical removal only.

## 10. RBAC

Central permissions:

- `p3.project.read`
- `p3.project.write`
- `p3.source.manage`
- `p3.project.activate`
- `p3.project.archive`

Permission matrix:

| Role | Read | Project write | Source manage | Activate | Archive |
| --- | --- | --- | --- | --- | --- |
| admin | yes | yes | yes | yes | yes |
| cleaner | yes | yes | yes | yes | no |
| reviewer | yes | no | no | no | no |
| viewer | yes | no | no | no | no |
| service | yes | no | no | no | no |

No authentication role or user table was added. Disabled mode remains compatible; token mode retains stable 401/403 behavior.

## 11. Stable error contract

Known errors use safe HTTP mappings:

- 404: `P3_PROJECT_NOT_FOUND`, `P3_SOURCE_ITEM_NOT_FOUND`
- 409: `P3_PROJECT_STATE_INVALID`, `P3_PROJECT_IDEMPOTENCY_CONFLICT`, `P3_SOURCE_INELIGIBLE`, `P3_SOURCE_EVIDENCE_CONFLICT`, `P3_SOURCE_STALE`
- 422: request validation and `P3_SOURCE_LIMIT_EXCEEDED`
- 503: `P3_STORAGE_UNAVAILABLE`

Responses exclude database URLs, Token values, stack traces, complete governed content and vectors.

## 12. Docker API acceptance

The existing development PostgreSQL volume was preserved. The backend image alone was rebuilt to the M2.4 commit.

Disabled-mode Smoke passed:

- create draft and identical idempotent replay: 201;
- add eligible P1 and P2 serving source: 201;
- archived P2 rejection: 409 `P3_SOURCE_INELIGIBLE`;
- source list, single revalidation and batch revalidation: 200;
- activation and frozen active selection: 200 then 409;
- admin archive and terminal mutation rejection: 200 then 409;
- disabled-mode list compatibility: 200.

The development volume contained no active `ready`-only P2 row. The stage did not mutate frozen P2 state to fabricate one. Ready-not-serving remains explicitly covered by the isolated eligibility and Service tests.

The exact P3 Smoke Project and two source rows were removed after the run. P1 Candidate/Review and P2 Knowledge Asset/Snapshot counts were identical before and after: `36 / 10 / 104 / 104`.

## 13. Auth acceptance

An ephemeral token-mode backend container used the same retained development database and was removed afterward:

- missing Token: 401 `AUTHENTICATION_REQUIRED`;
- wrong Token: 401 `AUTHENTICATION_INVALID`;
- admin/cleaner/reviewer/viewer/service read: 200;
- viewer write: 403 `AUTHORIZATION_DENIED`.

The normal backend remained healthy and was verified back at `DATAHUB_AUTH_MODE=disabled`.

## 14. Test evidence

| Gate | Result |
| --- | --- |
| M2.4 Route/API/RBAC | 15 passed |
| M2.3/M2.2/M2.1/M1/Auth affected regression | 198 passed, 3 skipped |
| Isolated PostgreSQL M2 model/repository/service | 3 passed |
| Authoritative ignored clean-export backend | 653 passed, 8 skipped, 44 warnings |
| Python compileall | PASS |
| Secret scan | PASS |
| `git diff --check` | PASS |

The eight clean-export skips are explicit environment-dependent integration gates. Existing warnings are FastAPI lifecycle deprecations and two intentional mock-provider fallback warnings.

## 15. Freeze protection and limitations

- P1/P2 business code, schema and governed source rows were not changed.
- M1.1 remains the only source-eligibility truth source.
- Route never accesses ORM or Repository directly.
- Service persists only through Repository and performs no raw SQL.
- No Provider, LLM, Embedding, Retrieval or Agent call occurs.
- No physical delete is exposed as a business operation.
- No draft asset, review, publish, export or frontend implementation exists.
- A Project supports at most 100 current sources in one activation/revalidation operation in v1.

## 16. P3-M3 entry condition

P3-M3 may start only after this report, release commit and annotated tag are pushed and the worktree is clean. Its first permitted increment is the additive draft-asset schema foundation defined by the frozen M0 contract. It must not retroactively alter M1 eligibility or M2 Project/source evidence.
