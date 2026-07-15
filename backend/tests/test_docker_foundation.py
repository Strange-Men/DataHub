"""Static and syntax gates for the reproducible Docker foundation."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT_DIR / relative_path).read_text(encoding="utf-8")


def test_compose_defines_health_gated_runtime_and_one_shot_initializers() -> None:
    compose = _read("compose.yaml")

    for service in ("postgres", "volume-init", "db-init", "backend", "frontend"):
        assert f"  {service}:" in compose

    assert "pgvector/pgvector:pg16" in compose
    assert "pg_isready -h 127.0.0.1" in compose
    assert "psql -h 127.0.0.1" in compose
    assert 'PGPASSWORD="$${POSTGRES_PASSWORD}"' in compose
    assert "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'" in compose
    assert '127.0.0.1:${POSTGRES_PORT:-5433}:5432' in compose
    assert '127.0.0.1:${BACKEND_PORT:-8000}:8000' in compose
    assert '127.0.0.1:${FRONTEND_PORT:-5173}:80' in compose
    assert "python scripts/check_pgvector_support.py && python scripts/init_database.py" in compose
    assert compose.index("python scripts/check_pgvector_support.py") < compose.index(
        "python scripts/init_database.py"
    )
    assert compose.count("condition: service_healthy") >= 2
    assert compose.count("condition: service_completed_successfully") >= 3
    assert 'user: "0:0"' in compose
    assert "network_mode: none" in compose
    assert "chown -R 10001:10001" in compose
    assert "VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8000}" in compose
    assert "CORS_ALLOWED_ORIGINS:" in compose
    assert "FRONTEND_PORT:-5173" in compose


def test_compose_persists_database_assets_p1_storage_and_runtime_manifests() -> None:
    compose = _read("compose.yaml")

    expected_mounts = {
        "postgres_data:/var/lib/postgresql/data",
        "asset_storage:/data/assets",
        "backend_storage:/app/backend/storage",
        "runtime_manifest:/app/.local-data",
    }
    for mount in expected_mounts:
        assert mount in compose
    for volume in ("postgres_data", "asset_storage", "backend_storage", "runtime_manifest"):
        assert f"  {volume}:" in compose

    assert "ASSET_STORAGE_BACKEND: local" in compose
    assert "ASSET_STORAGE_ROOT: /data/assets" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}" in compose
    assert "DATABASE_URL: postgresql" not in compose
    assert "EMBEDDING_API_KEY: ${EMBEDDING_API_KEY:-}" in compose


def test_pgvector_is_enabled_before_application_table_initialization() -> None:
    init_sql = _read("docker/postgres/init/001-enable-vector.sql")
    compose = _read("compose.yaml")

    assert "CREATE EXTENSION IF NOT EXISTS vector;" in init_sql
    assert "/docker-entrypoint-initdb.d/001-enable-vector.sql:ro" in compose
    assert "db-init:" in compose
    assert "postgres:" in compose
    assert "condition: service_healthy" in compose


def test_backend_image_contains_runtime_tools_and_runs_as_non_root() -> None:
    dockerfile = _read("backend/Dockerfile")

    assert "FROM python:3.11-slim-bookworm" in dockerfile
    assert "COPY --chown=10001:10001 backend/app /app/backend/app" in dockerfile
    assert "COPY --chown=10001:10001 scripts /app/scripts" in dockerfile
    assert "COPY --chown=10001:10001 samples /app/samples" in dockerfile
    assert "COPY docker/backend-entrypoint.sh /usr/local/bin/datahub-entrypoint" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "uvicorn" in dockerfile
    assert "0.0.0.0" in dockerfile
    assert "COPY .env" not in dockerfile
    assert "DATABASE_URL=" not in dockerfile
    assert "API_KEY=" not in dockerfile


def test_backend_entrypoint_url_encodes_database_credentials_without_logging_them() -> None:
    entrypoint = _read("docker/backend-entrypoint.sh")
    attributes = _read(".gitattributes")

    assert 'if [ -z "${DATABASE_URL:-}" ]' in entrypoint
    assert 'quote(os.environ["POSTGRES_USER"], safe="")' in entrypoint
    assert 'quote(os.environ["POSTGRES_PASSWORD"], safe="")' in entrypoint
    assert 'quote(os.environ["POSTGRES_DB"], safe="")' in entrypoint
    assert 'exec "$@"' in entrypoint
    assert "set -x" not in entrypoint
    assert "echo $DATABASE_URL" not in entrypoint
    assert "*.sh text eol=lf" in attributes.splitlines()
    assert "\r\n" not in (ROOT_DIR / "docker/backend-entrypoint.sh").read_bytes().decode(
        "utf-8"
    )


def test_cors_runtime_override_preserves_existing_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _read("backend/app/main.py")
    tree = ast.parse(source)
    selected_nodes = [
        node
        for node in tree.body
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name)
                and target.id == "_DEFAULT_CORS_ALLOWED_ORIGINS"
                for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
            )
        )
        or (isinstance(node, ast.FunctionDef) and node.name == "_cors_allowed_origins")
    ]
    namespace = {"os": os}
    module = ast.fix_missing_locations(ast.Module(body=selected_nodes, type_ignores=[]))
    exec(compile(module, "backend/app/main.py", "exec"), namespace)
    get_origins = namespace["_cors_allowed_origins"]

    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    assert get_origins() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://data-hub-flame.vercel.app",
    ]

    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5199/, http://127.0.0.1:5199, *, http://localhost:5199",
    )
    assert get_origins() == ["http://localhost:5199", "http://127.0.0.1:5199"]


def test_frontend_image_is_multistage_and_serves_spa_with_health_endpoint() -> None:
    dockerfile = _read("frontend/Dockerfile")
    nginx = _read("frontend/nginx.conf")

    assert "FROM node:20-alpine AS build" in dockerfile
    assert "ARG VITE_API_BASE_URL=http://localhost:8000" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "FROM nginx:1.27-alpine" in dockerfile
    assert "COPY --from=build /app/dist /usr/share/nginx/html" in dockerfile
    assert "location = /healthz" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_docker_build_context_excludes_secrets_and_local_runtime_data() -> None:
    dockerignore = _read(".dockerignore")

    for ignored in (
        ".git",
        ".env",
        ".env.*",
        ".local-data",
        "*.db",
        "backend/storage",
        "backend/tests",
        "frontend/node_modules",
        "frontend/dist",
    ):
        assert ignored in dockerignore.splitlines()


def test_compose_config_is_valid_when_docker_compose_is_available() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not installed in this test environment.")

    environment = os.environ.copy()
    environment["POSTGRES_PASSWORD"] = "contract-test-password"
    result = subprocess.run(
        [docker, "compose", "-f", "compose.yaml", "config", "--quiet"],
        cwd=ROOT_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
