# P2-M3 Human Review Foundation Report

> Status: Completed
>
> Date: 2026-07-14
>
> Baseline: P2-M2 on sealed P1 `p1-m24.3-real-embedding-online-release`

## 1. Release conclusion

P2-M3 completes the governance boundary `Extraction Result -> Human Review -> Approved/Rejected/Needs-Revision Decision`. Human corrections are stored separately from immutable machine results. Only an approved review produces an immutable snapshot, and approval plus snapshot creation is one database transaction.

The snapshot is not a knowledge publication. P2-M3 adds no real OCR, Caption, Vision LLM, Embedding, RAG synchronization, Knowledge Link, unified retrieval, or Agent call.

## 2. Data models

### `extraction_reviews`

| Field | Responsibility |
|---|---|
| `id` | Review identity |
| `asset_id` | Source Asset trace |
| `extraction_id` | Immutable source Extraction trace |
| `review_status` | `pending`, `approved`, `rejected`, or `needs_revision` |
| `reviewer` | Assigned/final human reviewer |
| `review_comment` | Human decision rationale |
| `original_content` | Audit copy captured from the source Extraction at review creation |
| `revised_content` | Optional human-edited content; never written back to Extraction |
| `version` | Monotonic version per Extraction |
| `created_at`, `updated_at` | Review audit timestamps |

OCR, Caption, and metadata use the same table. A unique Extraction/version constraint protects review history. The service allows at most one pending review per Extraction and returns the existing pending review id on conflict.

### `asset_review_snapshots`

| Field | Responsibility |
|---|---|
| `id` | Immutable snapshot identity |
| `asset_id` | Source Asset trace |
| `extraction_id` | Source machine result trace |
| `review_id` | Unique approved Review trace |
| `extract_type` | OCR/Caption/metadata discriminator |
| `original_content` | Machine content used by the reviewer |
| `approved_content` | Final human-approved content |
| `metadata_json` | Reviewer, comment, approved state, immutable marker |
| `version` | Same lineage version as the approved Review |
| `created_at` | Snapshot creation time; no update timestamp or update service exists |

Snapshot rows are append-only in the application. Later approvals create later versions and never mutate prior snapshots.

## 3. State machine

```text
                    -> approved       -> immutable Review + Snapshot
pending ------------> rejected       -> immutable Review, no Snapshot
                    -> needs_revision -> immutable Review, no Snapshot
```

Rules:

- creation always starts at `pending`;
- PATCH accepts only one terminal decision;
- terminal -> any state is rejected with HTTP 409;
- after a terminal decision, another review can be created as the next version;
- approved content must be non-empty;
- reviewer is mandatory at decision time;
- rejected and needs-revision decisions may retain suggested revised content for the next reviewer but never create a snapshot.

## 4. Immutable snapshot design

Approval is implemented by a row-lock-aware repository operation:

1. lock and re-read the Review;
2. verify it is still pending;
3. set reviewer, comment, revised content, and approved state;
4. add a snapshot containing original and final approved content;
5. commit Review and Snapshot together.

If snapshot persistence fails, the transaction rolls back and the Review does not become approved. There is no snapshot PATCH/DELETE API and no repository update method. Source `asset_extractions.content` is read only; focused tests compare it before and after approval.

The snapshot remains governance evidence. It has no publication status, embedding field, RAG id, or Agent visibility.

## 5. Review Service

`ReviewService` owns:

- Asset and Extraction existence checks;
- Extraction-to-Asset ownership validation;
- pending Review creation and source-content copy;
- reviewer, comment, and revised-content normalization;
- legal decision validation;
- final approved-content selection;
- atomic terminal decision and snapshot orchestration;
- stable not-found, conflict, and illegal-transition errors.

Review and snapshot repositories do not import P1 storage, embedding, RAG, retrieval, Bad Case, or Agent modules.

## 6. APIs

### `POST /api/assets/{asset_id}/reviews`

Creates a pending Review for `extraction_id`. A duplicate pending request returns HTTP 409 with `existing_review_id`, allowing the frontend to resume it. Missing/mismatched source records are rejected.

### `GET /api/reviews/{review_id}`

Returns status, source trace, machine-content copy, human revision, reviewer, comment, version, and timestamps.

### `PATCH /api/reviews/{review_id}`

Accepts `approved`, `rejected`, or `needs_revision`, plus reviewer, optional comment, and optional revised content. Approved returns both Review and Snapshot. Other decisions return `snapshot=null`. A terminal Review returns HTTP 409.

### `GET /api/assets/{asset_id}/snapshots`

Returns all immutable approved snapshots for the Asset, newest first. It is an audit/read API, not a knowledge or retrieval API.

## 7. Frontend

The existing dark Material Center now includes one compact Human Review section:

- loads the selected Asset's Extraction results and approved snapshots;
- displays source Extraction content as read-only;
- creates or resumes one pending Review;
- edits human content, reviewer, and comment;
- submits approve, reject, or needs-revision;
- disables edits after a terminal decision;
- displays immutable snapshot history.

It does not add a complex queue, image annotation, auto-extraction button, role management, publishing controls, or RAG status.

## 8. Verification

Focused P2-M3 tests:

```text
python -m pytest -q backend/tests/test_human_review_foundation.py
6 passed
```

Coverage includes create, approve, reject, needs revision, pending conflict, illegal terminal transition, snapshot generation/versioning, and source Extraction immutability.

P2 M1/M2/M3 focused regression:

```text
19 passed
```

Full clean isolated repository suite:

```text
python -m pytest -q backend/tests
268 passed, 28 warnings in 110.08s
```

Additional gates:

```text
python -m compileall -q backend/app backend/tests/test_human_review_foundation.py
PASS

npm run build
tsc && vite build
PASS
```

Warnings are existing FastAPI lifecycle, pytest-asyncio configuration, and intentional provider-fallback warnings, not failures.

## 9. P1 regression

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 120 --verbose --stop-on-fail
```

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 73.9 s |
| Trace | `p1-harness-20260714-135549-167d01` |
| Health | P1-M24.3; PostgreSQL healthy |
| pgvector | Available; extension enabled |
| Vector sync | 32 chunks, 32 embeddings, 0 failures |
| Embedding | SiliconFlow, 1536 dimensions |
| Retrieval | `customerops_vector_retrieval`, no fallback |
| Bad Case | Feedback and pending-review draft passed |

The harness performed its documented test-data writes. P2 Review and Snapshot modules do not import or call the P1 retrieval path.

## 10. Files changed

Backend:

- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/extraction_repositories.py`
- `backend/app/review_schemas.py`
- `backend/app/review_repositories.py`
- `backend/app/review_service.py`
- `backend/app/review_routes.py`
- `backend/tests/test_human_review_foundation.py`

Frontend:

- `frontend/src/types.ts`
- `frontend/src/pages/P2MaterialCenter.tsx`
- `frontend/src/styles.css`

Documentation:

- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/44_P2_M3_HUMAN_REVIEW_FOUNDATION_REPORT.md`

## 11. P2-M4 recommendation

P2-M4 should begin with a Knowledge Link and Publication Boundary decision before writing any vector:

1. project only approved snapshots into an immutable, versioned knowledge payload;
2. prove pending/rejected/needs-revision isolation;
3. define one active version, supersession, withdrawal, idempotency, and complete Asset -> Extraction -> Review -> Snapshot trace;
4. keep P2 writes isolated from sealed P1 tables;
5. decide explicitly whether the milestone stops at non-indexing Knowledge Links or separately authorizes text-bridge Embedding and a P2-only index;
6. do not switch CustomerOpsAgent to unified retrieval without a later explicit gate and P1/P2 eval.
