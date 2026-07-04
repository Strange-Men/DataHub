# DataHub Render Deployment Guide

This document explains how to deploy the DataHub FastAPI backend on Render as a Web Service.

## Service Type

**Web Service** — DataHub is a FastAPI HTTP server, not a background worker or static site.

## Repository

- **GitHub**: `Strange-Men/DataHub`
- **Branch**: `main`

## Render Configuration

| Setting | Value |
|---|---|
| **Root Directory** | (leave empty) |
| **Environment** | Python |
| **Python Version** | 3.11.9 (pinned by `.python-version` in repo root) |
| **Build Command** | `pip install -r backend/requirements.txt` |
| **Start Command** | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free (starter) |

## Why `backend/requirements.txt`

DataHub keeps the Python requirements file at `backend/requirements.txt`, not at the repository root. The Render build command must include the `backend/` prefix — otherwise Render fails with:

```
ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'
```

## Python Version

Render defaults to a recent Python (e.g., 3.14.x), but DataHub is developed and tested on Python 3.11+. The `.python-version` file at the repository root pins the version to `3.11.9` so Render picks the correct runtime.

## Verify the Deployment

After Render deploys successfully, check the health endpoint:

```
GET https://<your-service-name>.onrender.com/api/health
```

Expected response:

```json
{
  "status": "ok",
  "phase": "P1-M15"
}
```

Replace `<your-service-name>` with the actual Render service name (e.g., `datahub-api`).

## Common Issues

### 1. `requirements.txt` not found

**Symptom**: `ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'`

**Fix**: Change the Build Command from `pip install -r requirements.txt` to `pip install -r backend/requirements.txt`.

### 2. Uvicorn import path error

**Symptom**: `ModuleNotFoundError: No module named 'main'` or similar.

**Fix**: The Start Command must use the full dotted path: `uvicorn backend.app.main:app`. If the path is wrong, Uvicorn cannot find the FastAPI `app` object.

### 3. Python version mismatch

**Symptom**: Deprecation warnings, unexpected syntax errors, or dependency incompatibilities.

**Fix**: Ensure `.python-version` exists in the repository root with `3.11.9`. Render reads this file to select the Python runtime.

### 4. Render free instance cold start

**Symptom**: First request after idle takes 30–60 seconds.

**Fix**: This is expected behavior for Render's free tier. The service spins down after inactivity and restarts on the next request. Upgrade to a paid plan to eliminate cold starts.

### 5. `backend/storage` is not persistent

**Symptom**: Data disappears after redeploy or restart.

**Fix**: `backend/storage/` uses the local filesystem and the Render free tier does not provide persistent disk. This is acceptable for P1 demonstration — the storage directory holds temporary runtime data only. For production, replace with a database and object storage (planned for Phase 2+).

## Local Development vs Render

| Aspect | Local | Render |
|---|---|---|
| **Start** | `uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000` | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| **Port** | Fixed 8000 | `$PORT` env var (Render assigned) |
| **Reload** | `--reload` for dev | No reload in production |
| **Host** | `127.0.0.1` (localhost only) | `0.0.0.0` (all interfaces) |
| **Storage** | Persistent local disk | Ephemeral (free tier) |

## References

- [Render Web Services Docs](https://render.com/docs/web-services)
- [Render Python Deployment Guide](https://render.com/docs/deploy-fastapi)
- DataHub root `README.md` for local startup instructions.
