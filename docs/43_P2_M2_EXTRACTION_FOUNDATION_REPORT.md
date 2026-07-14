# P2-M2 Extraction Foundation Report

> Status: Completed
>
> Date: 2026-07-14
>
> Baseline: P2-M1 on sealed P1 `p1-m24.3-real-embedding-online-release`

## 1. Release conclusion

P2-M2 establishes the reliable `Asset -> Extraction Job -> Versioned Extraction Result` pipeline boundary. It adds no real AI capability. The only provider is a deterministic Mock used to verify orchestration, persistence, state transitions, failure, and retry behavior.

No real OCR provider, Caption model, Vision LLM, Embedding, RAG synchronization, review publication, or Agent call is implemented. Existing P1 tables, vector models, retrieval behavior, and CustomerOpsAgent logic are unchanged.

## 2. Data models

### `extraction_jobs`

One row represents a provider-neutral attempt to extract one kind of evidence from one Asset.

| Field | Responsibility |
|---|---|
| `id` | Namespaced `asset_extract_job_*` identity |
| `asset_id` | Source Asset reference |
| `extract_type` | `ocr`, `caption`, or `metadata` |
| `provider` | Provider adapter name; only `mock` is registered |
| `status` | `pending`, `running`, `success`, `failed`, or `retrying` |
| `retry_count` | Number of service-layer retries after initial execution |
| `error_message` | Safe provider error; unexpected exceptions are reduced to a generic message |
| `started_at`, `completed_at` | Attempt execution timing |
| `created_at`, `updated_at` | Job audit timing |

P2 ids are deliberately distinct from P1 `extract_job_*` ids so the shared lookup endpoint can dispatch without changing existing P1 behavior.

### `asset_extractions`

One row is the normalized output of one successful job.

| Field | Responsibility |
|---|---|
| `id` | Extraction result identity |
| `asset_id` | Source Asset trace |
| `job_id` | Unique successful job trace |
| `extract_type` | Shared OCR/Caption/metadata discriminator |
| `content` | Normalized text output for future review, not approved knowledge |
| `metadata_json` | Provider-neutral structured evidence and source metadata |
| `version` | Monotonic version per Asset and extract type |
| `created_at` | Immutable result creation time |

A unique job constraint prevents duplicate result creation. A composite Asset/type/version constraint protects version identity. No `ocr_results`, `caption_results`, or provider-specific table is created.

## 3. State design

Initial synchronous MVP execution:

```text
pending -> running -> success
                   -> failed
```

Service-layer retry:

```text
failed -> retrying -> running -> success
                            -> failed
```

- `pending` is committed before provider execution.
- `running` and `started_at` are committed before the provider is called, making the state observable to a future worker/monitor.
- `success` is set only after a normalized result is committed.
- `failed` stores a safe message and completion time without creating a result.
- `retrying` increments `retry_count`; the same job/provider contract is reused.

P2-M2 runs synchronously to stay deterministic, but the persisted state machine does not assume that the API process is the future executor. A queue/worker can later call the same service without changing the job/result schema.

## 4. Service and Provider abstraction

`ExtractionService` owns:

- Asset existence and extraction-type validation;
- job creation;
- state transitions and timestamps;
- provider execution;
- output validation and result persistence;
- safe failure handling;
- failed-job retry and retry counting.

`ExtractionProvider` exposes one method:

```text
extract(ExtractionContext) -> ExtractionOutput
```

The context carries job id, extraction type, and stable Asset metadata. Output contains normalized content and provider-neutral metadata. Future OCR or Vision adapters can implement the interface without changing routes, service orchestration, jobs, or results.

`MockExtractionProvider` performs no media parsing and no network call. Its deterministic result is marked `synthetic=true`, `foundation_only=true`, and `mock_execution=true` so it cannot be mistaken for real extracted evidence.

Real-provider readiness checks, credentials, timeouts, rate limits, exponential backoff, model/prompt versions, cost accounting, and queue execution remain required design work before a real adapter is enabled.

## 5. APIs

### `POST /api/assets/{asset_id}/extract`

Request:

```json
{
  "extract_type": "ocr",
  "provider": "mock"
}
```

The API creates and synchronously executes a job, then returns both final job state and optional result. A provider execution failure still means job creation succeeded: the response contains `job.status=failed` and `result=null`, allowing clients to treat job state as authoritative.

Only `ocr`, `caption`, and `metadata` are accepted. Only `mock` is accepted. A missing Asset returns HTTP 404.

### `GET /api/extraction/jobs/{job_id}`

This path already exists in sealed P1. P2 therefore uses `asset_extract_job_*` ids and adds a prefix-only compatibility dispatch inside the existing handler:

- P1 `extract_job_*` continues through the original JSON-backed P1 lookup and response contract;
- P2 `asset_extract_job_*` reads the additive database table;
- unknown ids retain HTTP 404 and `EXTRACTION_JOB_NOT_FOUND`.

No existing P1 job payload or known-id behavior is changed.

### `GET /api/assets/{asset_id}/extractions`

Returns all versioned results for the Asset, newest first. A missing Asset returns HTTP 404. Results are unreviewed and have no publication or Agent visibility semantics.

No public retry endpoint is added in M2; retry orchestration is verified at the service layer for a future worker/API milestone.

## 6. Test results

Focused P2-M2 suite:

```text
python -m pytest -q backend/tests/test_extraction_foundation.py
6 passed
```

Coverage:

- API job creation and lookup;
- observable `pending -> running -> success` transition;
- successful result persistence;
- provider failure and safe failed state;
- retry transition and `retry_count=1`;
- per-Asset/type result versioning;
- missing Asset, result list, and job behavior.

Focused P1/P2 extraction and ingestion regression:

```text
14 passed
```

Full repository suite in the same clean isolated Git workspace strategy used by P2-M1:

```text
python -m pytest -q backend/tests
262 passed, 24 warnings in 105.57s
```

Python compile and `git diff --check` passed. The warnings are existing FastAPI lifecycle, pytest-asyncio configuration, and intentional provider-fallback warnings, not failures. No frontend files or dependencies changed, so no new frontend build surface was introduced.

## 7. P1 regression gate

Online command:

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 120 --verbose --stop-on-fail
```

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 74.2 s |
| Trace | `p1-harness-20260714-132244-22fa96` |
| Health | P1-M24.3; PostgreSQL healthy |
| pgvector | Available; extension enabled |
| Vector sync | 30 chunks, 30 embeddings, 0 failures |
| Embedding | SiliconFlow, 1536 dimensions |
| Retrieval | `customerops_vector_retrieval`, no fallback |
| Bad Case | Feedback and pending-review draft passed |

The harness performed its documented test-data writes. P2 extraction code does not import or call P1 embedding, RAG, retrieval, Bad Case, or Agent modules.

## 8. Files changed

Backend:

- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/extraction_schemas.py`
- `backend/app/extraction_providers.py`
- `backend/app/extraction_repositories.py`
- `backend/app/extraction_service.py`
- `backend/app/extraction_routes.py`
- `backend/tests/test_extraction_foundation.py`

Documentation:

- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/43_P2_M2_EXTRACTION_FOUNDATION_REPORT.md`

No frontend, dependency, environment template, storage adapter, uploaded object, or P1 table file is changed beyond the additive P2 model registration and namespaced shared-route dispatch described above.

## 9. P2-M3 recommendation

P2-M3 should implement a Human Review Foundation around an Asset extraction bundle:

1. create one review aggregate, not OCR/Caption-specific review tables;
2. preserve immutable source extraction ids, versions, machine values, human corrections, decision, reviewer, and note;
3. support `approved`, `rejected`, and `needs_revision` without mutating machine results;
4. define a non-Agent-visible approved snapshot boundary;
5. keep Embedding, RAG synchronization, native visual retrieval, and CustomerOpsAgent integration outside the milestone unless separately authorized;
6. repeat full pytest and the sealed P1 online harness.
