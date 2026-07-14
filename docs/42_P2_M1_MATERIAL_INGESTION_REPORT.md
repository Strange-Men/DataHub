# P2-M1 Material Ingestion Foundation Report

> Status: Completed
>
> Date: 2026-07-14
>
> Starting point: P2-M0 commit `703c7c8`; sealed P1 baseline `p1-m24.3-real-embedding-online-release`

## 1. Release conclusion

P2-M1 is complete. DataHub now has a bounded material-ingestion foundation: private binary storage behind an adapter, one additive Asset metadata model, validated image upload, SHA-256 deduplication, paginated listing, metadata detail, and a minimal Material Center.

This milestone does not perform OCR, Caption, image understanding, embedding, RAG synchronization, review, or Agent calls. P1 routes, tables, retrieval behavior, embedding flow, and CustomerOpsAgent contracts were not changed.

## 2. Storage decision

The accepted decision is recorded in `docs/41_P2_M1_OBJECT_STORAGE_ADR.md`.

| Environment | P2-M1 decision | Boundary |
|---|---|---|
| Local development/test | `LocalFilesystemAssetStorage`, defaulting to ignored `backend/storage/asset_objects/` | Private files, atomic writes, opaque `local://` URI |
| Render production MVP | Same adapter on an attached paid persistent disk, for example `/var/data/datahub-assets` | Single-instance only; Render's default ephemeral filesystem is prohibited |
| Future production scale | Add an S3-compatible R2/S3/OSS adapter | Deferred; no SDK, credential, public bucket, or signed URL is added in M1 |

The database stores metadata only. It does not store BLOBs, absolute local paths, public object URLs, credentials, or signed URLs. Objects use deterministic keys of the form `assets/{hash-prefix}/{sha256}.{validated-extension}`.

Configuration:

```text
ASSET_STORAGE_BACKEND=local
ASSET_STORAGE_ROOT=
ASSET_MAX_UPLOAD_BYTES=10485760
```

## 3. Additive Asset model

One table was added instead of splitting ingestion into multiple isolated tables:

| Field | Purpose |
|---|---|
| `id` | Asset identifier |
| `asset_type` | `image` in M1; reserves future `video` and `pdf` |
| `file_name` | Original validated display name |
| `mime_type` | Validated canonical MIME type |
| `size` | Binary size in bytes |
| `storage_uri` | Opaque internal object URI |
| `hash` | Unique lowercase SHA-256 digest |
| `status` | Initial lifecycle state, `uploaded` |
| `metadata_json` | Storage/object-key and validation metadata without binary content |
| `created_at`, `updated_at` | Audit timestamps |

The model is additive. Existing P1 table definitions and schemas were not altered.

## 4. API delivered

### `POST /api/assets/upload`

Accepts multipart fields `file` and optional `asset_type` (default `image`). The endpoint:

1. checks a safe base file name;
2. enforces the configured byte limit;
3. accepts only JPEG, PNG, or WebP in M1;
4. cross-checks extension, declared MIME, and magic bytes;
5. calculates SHA-256;
6. returns HTTP 409 when the digest already exists;
7. atomically saves the object and then creates its metadata row.

Relevant responses are HTTP 201 success, 400 malformed/empty/name error, 413 size limit, 415 unsupported or mismatched content, 409 duplicate, and 503 storage failure. A duplicate response includes `existing_asset_id` so the client can select the existing Asset.

### `GET /api/assets`

Returns newest-first metadata with `page`, `page_size`, `total`, and `total_pages`. Pagination is constrained at the API boundary.

### `GET /api/assets/{id}`

Returns one Asset metadata record or HTTP 404. M1 deliberately exposes no binary download or public preview endpoint.

## 5. File safety and deduplication

- Allowed content: JPEG, PNG, and WebP images only.
- Rejected content: empty files, unsafe/path-like names, unsupported extensions or MIME types, MIME/magic/extension mismatch, future `video`/`pdf` asset types, and over-limit content.
- Deduplication: a pre-write lookup provides a fast response; a database unique constraint closes concurrent races; deterministic object keys keep storage idempotent.
- Transaction compensation: when metadata creation fails after a new object write, the service attempts to remove that object. A duplicate race does not delete the shared deterministic object.
- Path safety: the local adapter resolves every object key beneath the configured root and rejects traversal.

Archive/delete retention, malware scanning, content disarm, object preview, and orphan sweeping are later operational work; they are not silently claimed in M1.

## 6. Frontend delivered

The existing P2 Material Center route now provides:

- one-file JPEG/PNG/WebP upload with clear size/type guidance;
- a paginated Asset list;
- a metadata detail panel;
- duplicate handling that selects the existing Asset;
- explicit boundary copy showing that extraction and RAG work have not started.

The page reuses the existing dark palette, spacing, controls, and responsive layout. It does not redesign P1 pages and does not add image preview or extraction controls.

## 7. Verification results

### P2-M1 tests

```text
python -m pytest -q backend/tests/test_asset_ingestion.py
7 passed
```

Coverage includes upload success, illegal/mismatched files, duplicate content, pagination, detail/404, size/type limits, and storage path traversal.

### Full repository suite

```text
python -m pytest -q backend/tests
256 passed, 20 warnings in 113.36s
```

The authoritative full run used the exact current source in a clean isolated Git workspace. This avoids loading the developer machine's ignored historical `backend/storage/` corpus while preserving the P1 test assertion that the storage directory is Git-ignored. An initial isolated run without minimal Git metadata reached 255 passes and failed only its `git check-ignore backend/storage` environment assertion; adding `.gitignore` and `git init` produced the clean 256/256 result. The warnings are existing FastAPI lifecycle, pytest-asyncio configuration, and intentional unknown-provider fallback warnings, not test failures.

### Static/build checks

```text
python -m compileall -q backend/app backend/tests/test_asset_ingestion.py
PASS

npm run build
tsc && vite build
PASS
```

## 8. Sealed P1 regression gate

The deployed P1 service at `https://datahub-jr8x.onrender.com` was verified after the P2-M1 changes using:

```text
python scripts/run_p1_pipeline_harness.py \
  --base-url https://datahub-jr8x.onrender.com \
  --timeout 120 --verbose --stop-on-fail
```

Final result:

| Gate | Result |
|---|---|
| Pipeline Harness | PASS 10/10, 0 failed, 34.5 s |
| Trace | `p1-harness-20260714-112100-f652eb` |
| Health | P1-M24.3, PostgreSQL healthy, pgvector available and extension enabled |
| Vector sync | 28 chunks, 28 embeddings, 0 failures |
| Embedding | SiliconFlow, 1536 dimensions |
| Retrieval | HTTP 200, `customerops_vector_retrieval`, no fallback |
| Bad Case flow | Feedback and pending-review draft both passed |

The first 30-second attempts encountered a Render cold-start health timeout and then a long vector-sync timeout. After waking the service and using a 120-second harness timeout, all ten gates passed. No P1 code or deployed data was modified to manufacture the result.

## 9. Files changed

Backend and configuration:

- `.env.example`
- `backend/requirements.txt`
- `backend/app/db_models.py`
- `backend/app/main.py`
- `backend/app/asset_schemas.py`
- `backend/app/asset_storage.py`
- `backend/app/asset_repositories.py`
- `backend/app/asset_service.py`
- `backend/app/asset_routes.py`
- `backend/tests/test_asset_ingestion.py`

Frontend:

- `frontend/src/types.ts`
- `frontend/src/pages/P2MaterialCenter.tsx`
- `frontend/src/styles.css`

Documentation:

- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/41_P2_M1_OBJECT_STORAGE_ADR.md`
- `docs/42_P2_M1_MATERIAL_INGESTION_REPORT.md`

## 10. Recommended P2-M2 boundary

P2-M2 should begin with an Extraction Foundation design, not with RAG publication. Recommended first slice:

1. define one extraction job/state model with retry, idempotency, timeout, provider, cost, and error metadata;
2. select a bounded OCR-first provider abstraction and fixture-based tests;
3. persist immutable extraction evidence linked to Asset without mutating source metadata;
4. keep extracted text in a non-approved state;
5. continue to prohibit embedding, RAG synchronization, and Agent consumption until later review/publication gates;
6. repeat the 256-test repository suite and sealed P1 10/10 online harness.

Caption, native visual embedding, broad video/PDF processing, and review/publication remain separately gated work.
