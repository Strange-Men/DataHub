"""Safety helpers for deterministic DataHub test processes.

This module deliberately does not load the project ``.env``.  Test launchers
must opt in to one of the explicit offline/PostgreSQL/Docker layers and must
never inherit provider credentials or a development database implicitly.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


class TestEnvironmentSafetyError(RuntimeError):
    """Raised before a test can target a non-test resource."""


_HOST_KEYS = (
    "COMSPEC",
    "HOME",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
)


def _database_name(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+psycopg2://", "postgresql://", 1))
    if parsed.scheme.startswith("sqlite"):
        return Path(parsed.path).name.lower()
    return parsed.path.rsplit("/", 1)[-1].lower()


def require_test_database_url(
    database_url: str,
    *,
    development_url: str | None = None,
) -> str:
    """Reject empty, ambiguous, or development database targets."""

    normalized = database_url.strip()
    if not normalized:
        raise TestEnvironmentSafetyError("A dedicated test DATABASE_URL is required.")
    if "test" not in _database_name(normalized):
        raise TestEnvironmentSafetyError(
            "Refusing database target: the database name must contain 'test'."
        )
    if development_url and normalized == development_url.strip():
        raise TestEnvironmentSafetyError(
            "Refusing database target: test and development DATABASE_URL are identical."
        )
    return normalized


def require_offline_environment(environment: dict[str, str]) -> None:
    """Fail closed when an offline test could use a real provider or database."""

    if environment.get("DATAHUB_TEST_MODE") != "offline":
        raise TestEnvironmentSafetyError("Offline tests require DATAHUB_TEST_MODE=offline.")
    if environment.get("EMBEDDING_PROVIDER", "").lower() != "mock":
        raise TestEnvironmentSafetyError("Offline tests require EMBEDDING_PROVIDER=mock.")
    if environment.get("LLM_PROVIDER", "").lower() != "mock":
        raise TestEnvironmentSafetyError("Offline tests require LLM_PROVIDER=mock.")
    for key in ("EMBEDDING_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        if environment.get(key):
            raise TestEnvironmentSafetyError(
                f"Offline tests must not receive the real provider variable {key}."
            )
    require_test_database_url(environment.get("DATABASE_URL", ""))


def require_test_compose_identity(
    project_name: str,
    *,
    test_ports: set[int],
    development_ports: set[int] | None = None,
) -> None:
    """Reject a Docker test stack that can collide with the development stack."""

    if "test" not in project_name.lower():
        raise TestEnvironmentSafetyError(
            "Docker test project name must contain 'test'."
        )
    overlap = test_ports & (development_ports or {5433, 8000, 5173})
    if overlap:
        raise TestEnvironmentSafetyError(
            "Docker test ports collide with development ports."
        )


def build_offline_subprocess_environment(
    project_root: Path,
    sqlite_path: Path,
) -> dict[str, str]:
    """Build a minimal deterministic environment for an offline child process."""

    root = project_root.resolve()
    database_path = sqlite_path.resolve()
    if "test" not in database_path.name.lower():
        raise TestEnvironmentSafetyError(
            "Offline SQLite filename must contain 'test'."
        )
    environment = {
        key: value
        for key in _HOST_KEYS
        if (value := os.environ.get(key)) is not None
    }
    environment.update(
        {
            "PYTHONPATH": str(root / "backend"),
            "DATAHUB_TEST_MODE": "offline",
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "DATAHUB_TEST_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "ASSET_STORAGE_ROOT": str(database_path.parent / "asset-storage-test"),
            "EMBEDDING_PROVIDER": "mock",
            "EMBEDDING_MODEL": "mock-deterministic",
            "EMBEDDING_DIMENSION": "1536",
            "LLM_PROVIDER": "mock",
            "LLM_MODEL": "mock",
            "DATAHUB_AUTH_MODE": "disabled",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    require_offline_environment(environment)
    return environment
