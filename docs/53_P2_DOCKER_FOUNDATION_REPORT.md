# P2 Docker Foundation Report

## 1. Phase Decision

This report records the reproducible local Docker foundation for DataHub P1/P2. It deliberately separates configuration design from runtime evidence.

| Acceptance item | Current report state |
|---|---|
| Compose configuration validation | **PASS** |
| Image build | **PASS** |
| Service health | **PASS** — PostgreSQL, backend, and frontend healthy |
| PostgreSQL/pgvector initialization | **PASS** — pgvector 0.8.5; 20 application tables |
| Asset and database restart durability | **PASS** |
| real-SiliconFlow P2 chain | **PASS** |
| exact-id P2 Eval | **PASS** |
| sealed P1 Harness | **PASS** — 10/10 |
| Render Deployment Acceptance | **BLOCKED** — no usable Persistent Disk |

The runtime and automated gates above are captured from the completed local Docker run. Only the phase commit and push remain pending at this report update. The semantic result uses real SiliconFlow; mock startup is not used as release evidence.

## 2. Objective and Boundary

The Docker foundation makes a fresh Git clone runnable with PostgreSQL/pgvector, FastAPI, the React console, and persistent local Asset storage after copying `.env.example` to an ignored `.env`.

It does not:

- change the sealed P1 `rag_chunks`, `rag_embeddings`, or CustomerOpsAgent retrieval contract;
- implement Unified Retrieval, RRF, Shadow, or Agent opt-in;
- add S3/R2/OSS/MinIO storage;
- configure Render Persistent Disk or claim Render P2 acceptance;
- implement native image embedding, CLIP, or a multimodal reranker.

The authoritative development environment is local Docker. Render remains a separately blocked deployment target.

## 3. Compose Architecture

The Compose application uses five services with health-gated startup:

```text
postgres (PostgreSQL + pgvector)
    ↓ healthy
volume-init (one-shot persistent-volume ownership/bootstrap)
    ↓ completed successfully
db-init (one-shot extension/table initialization)
    ↓ completed successfully
backend (FastAPI)
    ↓ healthy
frontend (Vite build served as a static SPA)
```

Runtime responsibilities:

| Service | Responsibility |
|---|---|
| `postgres` | PostgreSQL data and the pgvector extension capability |
| `volume-init` | initialize writable persistent directories without putting host-specific paths in Compose |
| `db-init` | create/verify `vector`, then initialize the existing SQLAlchemy schema |
| `backend` | expose existing P1/P2 APIs and write Asset objects to the mounted Asset root |
| `frontend` | serve the existing dark management console and use the configured public API base |

Default host ports are PostgreSQL `5433`, backend `8000`, and frontend `5173`. Container-to-container database traffic stays on `postgres:5432`; the backend never connects through the host mapping.

## 4. Persistence Model

Named volumes isolate mutable runtime state from images and the Git worktree:

- PostgreSQL data survives backend/postgres container replacement and ordinary `docker compose down`;
- Asset binaries survive backend restart and are not stored in PostgreSQL;
- compatibility JSON/runtime directories remain outside the immutable image;
- runtime expected-ID manifests and generated acceptance material are never committed.

The Docker Asset root is a container path backed by a named volume. It must not reference `D:/Claude_workfile/DataHub/.local-data/assets` or any other developer-specific host path.

Persistence proof requires one public Asset upload, backend restart, PostgreSQL restart, and a subsequent Asset row/file check. Physical volume deletion via `docker compose down -v` is explicitly destructive and is not part of normal shutdown.

## 5. Runtime Configuration

`.env.example` provides non-secret Docker ports, an intentionally empty required `POSTGRES_PASSWORD`, and a keyless mock embedding default. Compose fails closed until the ignored `.env` supplies the password. The backend entrypoint URL-encodes URL-reserved password characters before it builds the internal `DATABASE_URL`; Compose dotenv special characters must still follow Compose quoting and escaping rules. Real credentials stay only in ignored `.env`.

Real P2 semantic acceptance uses:

| Field | Required value |
|---|---|
| provider | `siliconflow` |
| model | `Qwen/Qwen3-Embedding-4B` |
| dimension | `1536` |
| profile | `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536` |

The API key is injected at container runtime. It is not a Docker build argument, image layer, README value, log field, test fixture, or committed environment file. The frontend API URL is public build-time configuration and must never contain credentials.

## 6. Health and Initialization Gates

The acceptance run must prove:

1. `docker compose config --quiet` parses without unresolved required values and does not print expanded secrets.
2. `postgres` becomes healthy before initialization.
3. `volume-init` and `db-init` exit successfully.
4. the `vector` extension is installed and queryable.
5. backend health reports PostgreSQL and pgvector available.
6. frontend responds on the configured host port.
7. Asset upload writes an Asset row and a file to persistent storage.

Expected commands:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/api/health
curl -I http://localhost:5173
```

## 7. Validation Ledger

This table records actual execution; no PASS is inferred from an earlier phase.

| Gate | Command/evidence | Result |
|---|---|---|
| Compose render | `docker compose config --quiet` | **PASS** |
| Images | `docker compose build` | **PASS** |
| Service state | `docker compose ps` | **PASS**; three long-running services healthy; initializers exited successfully |
| pgvector | SQL extension query | **PASS**; pgvector 0.8.5 |
| backend DB access | `/api/health` | **PASS**; 20 application tables initialized |
| frontend | HTTP response | **PASS** |
| Asset upload | `POST /api/assets/upload` | **PASS**; `asset_19c63ea6f3c746649aef` |
| backend restart durability | Asset row and object after restart | **PASS** |
| PostgreSQL restart durability | Asset row and object after restart | **PASS** |
| P2 governed acceptance | `run_p2_local_acceptance.py` | **PASS**; `p2-local-20260715-192631-5058fcd7` |
| P2 exact-id Eval | `run_p2_rag_eval.py` | **PASS**; 12 queries; recall 1.0; leakage 0 |
| P1 sealed regression | `run_p1_pipeline_harness.py` | **PASS**; 10/10; `p1-harness-20260715-192652-456d0f` |
| Docker-focused tests | `pytest backend/tests/test_docker_foundation.py -q` | **PASS**; 9 passed in 0.54 s |
| full backend suite | clean-runtime `pytest backend/tests -q` | **PASS**; 336 passed, 44 existing warnings, 119.35 s |
| Python compilation | `python -m compileall backend/app scripts` | **PASS** |
| frontend build | `npm run build` | **PASS** |
| diff/ignore/secret audit | Git and ignored-runtime checks | **PASS**; no out-of-scope file or secret |

The final update must record safe summaries only: no API key, database password, full `DATABASE_URL`, complete vector, local Asset payload, or runtime manifest IDs.

### 7.1 Container and persistence evidence

- PostgreSQL, backend, and frontend reached healthy status; `volume-init` and `db-init` completed successfully.
- PostgreSQL reported pgvector 0.8.5 and the backend initialized 20 P1/P2 tables.
- The backend process runs as the non-root user with UID 10001.
- Public upload created Asset `asset_19c63ea6f3c746649aef` and its object in the Asset named volume.
- After restarting the backend container, both the database record and named-volume object remained.
- After restarting the PostgreSQL container, both remained available, proving that service recreation does not depend on a container writable layer.

### 7.2 Real P2 governed acceptance

Trace `p2-local-20260715-192631-5058fcd7` passed with real SiliconFlow `Qwen/Qwen3-Embedding-4B`, dimension 1536, and profile `text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536`.

The public-API run proved:

- Embedding build leaves the Entry at `ready` and the target is invisible before explicit Serve.
- Explicit Serve makes the governed target retrievable with complete source trace and no P1 fallback.
- Archive immediately produces zero recall while the physical vector may remain.
- The old Knowledge Asset version is archived and has zero recall after replacement.

### 7.3 P2 Eval

| Metric | Docker result |
|---|---:|
| total_queries | 12 |
| hit_rate@5 | 1.0 |
| query_hit_rate@5 | 1.0 |
| candidate_recall@5 | 1.0 |
| MRR | 0.95 |
| semantic_mode_count | 12 |
| no_hit_count | 2 |
| archived_leakage_count | 0 |
| duplicate_asset_rate | 0.0 |
| avg_top1_score | 0.712 |
| avg_top5_score | 0.6195 |
| avg_latency_ms | 296.388 |
| p95_latency_ms | 373.805 |
| failed_queries | 0 |

This run is materially faster than the earlier host-process baseline, but no broad performance claim is made from twelve queries. The exact-id recall/MRR labels came from the ignored runtime manifest.

### 7.4 Sealed P1 regression

The same Docker backend passed the sealed P1 Harness 10/10 under trace `p1-harness-20260715-192652-456d0f`. PostgreSQL/pgvector, real SiliconFlow embedding, `customerops_vector_retrieval`, no fallback, and Bad Case submit/draft all remained healthy. Docker Foundation did not modify P1 retrieval storage or its legacy endpoint.

## 8. Acceptance Commands

After a real SiliconFlow profile is configured in ignored `.env`, the preferred container-local public-API runners are:

```bash
docker compose exec backend python scripts/run_p2_local_acceptance.py --base-url http://127.0.0.1:8000 --timeout 120 --verbose --keep-data --output-manifest /app/.local-data/p2-eval-expected-manifest.json
docker compose exec backend python scripts/run_p2_rag_eval.py --base-url http://127.0.0.1:8000 --top-k 5 --timeout 120 --verbose --expected-manifest /app/.local-data/p2-eval-expected-manifest.json
docker compose exec backend python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000 --timeout 120 --verbose --stop-on-fail
```

Equivalent host-side runners are available when Python 3.11+ is installed:

```bash
python scripts/run_p2_local_acceptance.py --base-url http://127.0.0.1:8000 --timeout 120 --verbose --keep-data --output-manifest .local-data/p2-eval-expected-manifest.json
python scripts/run_p2_rag_eval.py --base-url http://127.0.0.1:8000 --top-k 5 --timeout 120 --verbose --expected-manifest .local-data/p2-eval-expected-manifest.json
python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000 --timeout 120 --verbose --stop-on-fail
```

The P2 runner must prove embed-keeps-ready, pre-serve zero recall, explicit Serve hit, Archive zero recall, version replacement, complete source trace, and real provider metadata. The P1 Harness must remain 10/10 with `customerops_vector_retrieval` and no fallback.

## 9. README and Operations

`README.md` documents clone-style setup, `.env`, required PostgreSQL variables, optional SiliconFlow settings, mock-versus-real evidence, service URLs, health and database initialization, Asset upload, P2 acceptance/Eval, P1 Harness, logs, ordinary shutdown, destructive volume cleanup, persistence checks, troubleshooting, Render limitations, and secret safety.

Operational commands keep data by default:

```bash
docker compose logs -f --tail=200
docker compose down
```

Only an operator who accepts complete local data deletion may run:

```bash
docker compose down -v --remove-orphans
```

## 10. Render Deployment Boundary

The current Render service has no usable Persistent Disk, so `POST /api/assets/upload` fails closed with HTTP 503 `ASSET_STORAGE_UNAVAILABLE`. Local Docker can establish application behavior, pgvector, real embedding, persistence under Docker named volumes, Serving Gate, and archive withdrawal. It cannot establish Render filesystem durability, restart survival, or an online P2 corpus.

Therefore:

- Local Docker Runtime Acceptance: **PASS** for Compose health, durability, real P2, P2 Eval, and sealed P1 Harness;
- Docker Foundation phase closure: **PASS** for runtime, automated regression, build, and security gates; commit/push pending;
- Render Deployment Acceptance: **BLOCKED**;
- no online P2 enablement or CustomerOpsAgent cutover is claimed.

## 11. Security Review

- `.env`, `.local-data/`, database files, Asset binaries, runtime manifests, `dist`, and `node_modules` remain untracked.
- Dockerfiles do not copy `.env`, secrets, local databases, or runtime material into images.
- secrets are runtime-only and are not emitted in health responses or validation reports.
- P1 and P2 keep independent physical tables.
- mock startup is labeled as infrastructure-only evidence.
- archive visibility is controlled by repository/status gates even if a physical vector remains.

## 12. Exit Gate and Next Phase

Docker Foundation is complete at the implementation and acceptance level: 9 focused tests passed, the authoritative clean-runtime suite passed 336 tests with 44 existing warnings in 119.35 seconds, compileall and the frontend build passed, and the diff/ignore/secret audit found no out-of-scope file or secret. `.env` and `.local-data/` remain ignored.

The remaining Git action is to stage the exact audited Docker phase files, commit them as `[P2-Docker] chore: add reproducible local docker environment`, and push `main`. No commit hash is recorded before that commit exists.

After that gate, the next authorized phase is P2-M8.2 Unified Retrieval Shadow Gate. M8.2 may add logical dual-route retrieval and rank-level fusion, but it must not alter the legacy P1 endpoint or CustomerOpsAgent default behavior.
