# ADR: P2-M1 Material Object Storage

> Status: Accepted for P2-M1
>
> Date: 2026-07-14
>
> Scope: Material Ingestion Foundation only

## 1. Context

P2-M1 must persist uploaded material binaries without writing them into PostgreSQL or coupling Asset metadata to one cloud vendor. The stable P1 baseline remains frozen at `p1-m24.3-real-embedding-online-release`; this decision adds a P2 storage boundary and does not modify P1 tables, APIs, retrieval, embedding, or RAG behavior.

The first supported binary types are JPEG, PNG, and WebP images. The Asset model reserves `asset_type` for later `video` and `pdf` milestones, but P2-M1 does not accept those files.

## 2. Decision

Introduce an `AssetStorageAdapter` with this minimum contract:

- atomically save bytes by an opaque object key;
- test whether an object exists;
- delete an object after a failed metadata transaction;
- return an opaque `storage_uri`, never a public URL or credential-bearing endpoint.

P2-M1 implements `LocalFilesystemAssetStorage`. Asset rows store metadata and an opaque URI; binary bytes stay behind the adapter.

```text
POST /api/assets/upload
  -> validate name / MIME / magic bytes / size
  -> SHA-256
  -> deduplicate in PostgreSQL
  -> AssetStorageAdapter.save(object_key, bytes)
  -> assets metadata row
```

The deterministic object key is based on SHA-256 rather than the user file name:

```text
assets/{hash-prefix}/{sha256}.{validated-extension}
```

This prevents path traversal, gives stable object identity, and aligns storage idempotency with the database unique hash constraint.

## 3. Local development profile

- `ASSET_STORAGE_BACKEND=local`
- Default root: ignored `backend/storage/asset_objects/`
- Optional override: `ASSET_STORAGE_ROOT=<absolute-or-relative-path>`
- Default maximum upload: `ASSET_MAX_UPLOAD_BYTES=10485760` (10 MiB)

The default directory is already covered by the repository's `backend/storage/` ignore rule. No uploaded material, object bytes, `.env`, database file, or credential may be committed.

## 4. Render production profile

Render services use an ephemeral filesystem by default, so the default project directory is not a production persistence solution. For the P2-M1 single-instance MVP, attach a paid Render persistent disk and configure:

```text
ASSET_STORAGE_BACKEND=local
ASSET_STORAGE_ROOT=/var/data/datahub-assets
```

Only the configured mount path is persistent. The database remains Render PostgreSQL; the disk stores binary material only. This profile is suitable for the current single web-service demo, but it has important limits:

- a persistent disk is attached to one service instance;
- it constrains horizontal scaling and zero-downtime behavior;
- disk and database backup/restore are separate operations;
- capacity must be monitored and increased deliberately.

The Render profile must not be enabled unless the disk is actually attached and the mount path matches `ASSET_STORAGE_ROOT`. Otherwise uploads would appear successful and disappear on redeploy.

Reference: [Render Persistent Disks](https://render.com/docs/disks).

## 5. S3-compatible migration target

Cloudflare R2 is the preferred future production object store, with AWS S3 or Alibaba Cloud OSS as compatible alternatives. The next adapter will implement the same contract and map opaque keys to `s3://bucket/key`-style internal URIs.

R2 is a good target because it exposes an S3-compatible API and supports time-limited presigned operations. Presigned URLs must be treated as bearer tokens, use short expiry, restrict content type, and never be persisted as `storage_uri`.

Reference: [Cloudflare R2 S3 API](https://developers.cloudflare.com/r2/api/s3/) and [R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/).

P2-M1 deliberately does not add boto3, cloud credentials, public buckets, presigned upload APIs, or an S3 implementation. Those changes require a separate ADR amendment and integration tests. The Asset schema and API will not need to change when that adapter is added.

## 6. Security and lifecycle

- Validate declared MIME type, file extension, and magic bytes; do not trust the browser header alone.
- Accept only JPEG, PNG, and WebP in P2-M1.
- Reject empty files, path-like names, MIME/content mismatch, and content over the configured maximum.
- Compute SHA-256 before persistence and enforce a unique database constraint.
- Store objects privately. P2-M1 exposes metadata only and has no public binary download endpoint.
- Never put credentials, signed URLs, absolute local paths, or provider secrets in `storage_uri` or API responses.
- Keep an uploaded object while its Asset row is active. Archive/delete lifecycle is deferred until the P2 review/publication semantics exist; no automatic deletion job is introduced in M1.
- Orphan cleanup and retention policies must be added before high-volume production use.

## 7. Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| Binary/BLOB in PostgreSQL | Rejected | Inflates relational backups and violates the metadata/binary separation required by P2-M0 |
| Default Render filesystem | Rejected for production | Files are lost on restart/redeploy |
| Render persistent disk | Accepted for single-instance P2-M1 production profile | Minimal implementation and immediately compatible with the local adapter |
| R2/S3/OSS now | Deferred | Better scaling target, but credentials, SDK, lifecycle and integration testing would broaden M1 |
| Public bucket URLs | Rejected | Weak access control and permanent URL leakage |

## 8. Consequences

Positive:

- P2-M1 is runnable locally and on a correctly configured Render disk.
- PostgreSQL remains metadata-only.
- Hash-based storage and database uniqueness provide deterministic deduplication.
- Future S3-compatible migration does not change Asset/API contracts.

Trade-offs:

- The implemented adapter is not horizontally scalable.
- P2-M1 has no binary read/preview endpoint; the frontend shows governed metadata only.
- Lifecycle automation and cloud object storage remain explicit later work.

## 9. Verification gates

- Local adapter atomic-write and path-boundary behavior are tested.
- Upload, illegal file, duplicate, pagination, and detail API tests pass.
- No binary column exists in `assets`.
- `storage_uri` is opaque and contains no absolute path or secret.
- P1 full regression, online harness, and CustomerOpsAgent retrieval remain healthy.
