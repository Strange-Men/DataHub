# DataHub Render Deployment Configuration Guide

This document records the current deployment contract for a Render-style
deployed backend. It is configuration guidance, not evidence that production
deployment, persistent storage, migrations, or end-to-end workflows have been
accepted. Local Docker remains the authoritative runtime environment for the
current release line.

## Service and build contract

DataHub is a Python 3.11 FastAPI web service. Configure the repository root as
the working directory so `alembic.ini`, `backend/migrations`, and `scripts` are
available to both the migration command and the application process.

| Setting | Value |
|---|---|
| Service type | Web service |
| Runtime | Python 3.11 |
| Build command | `python -m pip install -r backend/requirements.txt` |
| Migration/release command | `python scripts/manage_migrations.py upgrade` |
| Start command | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Liveness path | `/health/live` |
| Readiness path | `/health/ready` |

The migration command must complete successfully before the web process is
promoted. It handles a new database, an exactly matching legacy database, and
an already migrated database. A mismatched schema is refused. Do not place
`scripts/init_database.py`, `create_all`, or implicit DDL in the normal start
command.

`python scripts/manage_migrations.py status` is a read-only diagnostic. It
returns a non-zero exit status until the schema is at the repository migration
head. Re-running `upgrade` is the supported idempotent operation; neither
command deletes or resets database data.

## Environment contract

Configure secrets through the deployment platform's secret store. The table
describes whether a secret is configured; real values must never be copied into
repository files, build arguments, logs, health responses, or screenshots.

| Variable | Deployment requirement | Default and scope |
|---|---|---|
| `DATAHUB_ENV` | Required, set to `production` (or `staging`) | No deployed default should be relied on; local Compose injects `local` |
| `RENDER` | Platform-managed marker | Render supplies this marker; do not set it in local `.env`. A true value forces deployed authority even if an unsafe local/test label is present |
| `DATABASE_URL` | Required secret | SQLAlchemy PostgreSQL URL used by migration and backend processes |
| `DATAHUB_AUTH_MODE` | Required, set to `token` | `disabled` is accepted only for trusted local/test authority |
| `DATAHUB_ADMIN_TOKEN`, `DATAHUB_CLEANER_TOKEN`, `DATAHUB_REVIEWER_TOKEN`, `DATAHUB_SERVICE_TOKEN`, `DATAHUB_VIEWER_TOKEN` | Secret; configure at least one unique role token | An unconfigured role is unavailable; token values are never reported |
| `CORS_ALLOWED_ORIGINS` | Required for browser clients | Comma-separated HTTPS origins, no wildcard-with-credentials fallback |
| `ASSET_STORAGE_BACKEND` | Optional | Current implementation: `local` |
| `ASSET_STORAGE_ROOT` | Required only when P2 storage is expected | Must point to an explicitly provisioned persistent mount in a deployed environment |
| `P3_EXPORT_STORAGE_BACKEND` | Optional | Current implementation: `local_filesystem` |
| `P3_EXPORT_STORAGE_ROOT` | Required only when durable P3 exports are expected | Must point to an explicitly provisioned persistent mount |
| `EMBEDDING_PROVIDER` | Optional | `mock`; real provider use is separate acceptance work |
| `EMBEDDING_API_KEY` | Optional secret | Configure only with a reviewed real embedding provider profile |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Deprecated embedding aliases | Direct-runtime compatibility fallback only; prefer `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL`, and do not configure both contracts |
| `P2_RETRIEVAL_MIN_SCORE` | Optional | Frozen current default `0.45`; changing retrieval thresholds requires a separate controlled rollout |
| `P3_LLM_DRAFT_ENABLED` | Optional | `false`; explicit opt-in only |
| `P3_LLM_API_KEY` | Optional secret | Required only when the reviewed P3 LLM draft profile is enabled |
| Unified retrieval and no-answer variables | Optional | Frozen defaults are documented in `.env.example`; changing them is a separate controlled rollout |

Generic `LLM_*`, `LOG_LEVEL`, and `DEBUG` entries are retained only as
deprecated/inert local compatibility settings. The current backend uses
`P3_LLM_*` for governed P3 drafts, and Uvicorn command-line options control its
logging/runtime mode.

Native source deployments use `DATABASE_URL` directly. The discrete
`POSTGRES_*` variables and URL-encoding entrypoint belong to the local Docker
image/Compose contract and are not a substitute for a deployment-platform
database secret.

## Storage boundary

The repository does not provision a Render persistent disk or cloud object
storage. Without separately configured persistent mounts, P2 assets and P3
exports are local/ephemeral and must not be described as production-ready or
durable. A successful web deploy or CI run does not close this storage gap.

Do not point storage roots at repository paths or temporary build directories.
Do not reset a database or remove a volume as part of migration or deployment
troubleshooting.

## Safe verification

After the migration job and web process have started:

```bash
curl --fail https://<service-host>/health/live
curl --fail https://<service-host>/health/ready
curl --fail https://<service-host>/api/capabilities
```

- `/health/live` proves only that the process can respond and does not access
  the database.
- `/health/ready` is read-only and returns HTTP 503 when migrations,
  PostgreSQL/pgvector, storage, or auth safety are not ready.
- `/api/capabilities` reports sanitized runtime status and must not expose a
  database URL, token, provider key, absolute storage path, or internal
  exception.
- `/health` and `/api/health` remain compatibility endpoints; deployment
  orchestration should use `/health/ready`.

Record the actual platform run, migration revision, readiness response, storage
configuration, and restart durability before making any production acceptance
claim. This guide alone does not provide that evidence.
