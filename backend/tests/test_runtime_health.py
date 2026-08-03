"""Runtime environment, fail-closed auth, and zero-DDL health gates."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
import logging
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import capability_probes, health_service  # noqa: E402
import app.database as database_module  # noqa: E402
import app.main as main_module  # noqa: E402
from app.auth import (  # noqa: E402
    AuthConfigurationError,
    AuthConfigurationIssue,
    AuthSettings,
    Permission,
    ROLE_TOKEN_ENV,
    require_permission,
    validate_auth_configuration,
)
from app.health_routes import router as health_router  # noqa: E402
from app.runtime_environment import (  # noqa: E402
    RuntimeEnvironment,
    RuntimeEnvironmentError,
    resolve_runtime_environment,
)
from app.runtime_config import RuntimeReadinessError  # noqa: E402
from app.storage_readiness import StorageReadiness  # noqa: E402


@pytest.fixture(autouse=True)
def safe_local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "local")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    monkeypatch.delenv("RENDER", raising=False)
    for name in ROLE_TOKEN_ENV.values():
        monkeypatch.delenv(name, raising=False)


def _isolated_health_client() -> TestClient:
    isolated_app = FastAPI()
    isolated_app.include_router(health_router)
    return TestClient(isolated_app)


def _configure_healthy_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health_service,
        "check_database_connection",
        lambda: {"status": "ok", "backend": "postgresql", "enabled": True},
    )
    monkeypatch.setattr(
        health_service,
        "migration_readiness",
        lambda: {
            "status": "ok",
            "current_revision": "head",
            "head_revision": "head",
            "version_table_present": True,
            "schema_matches_baseline": True,
            "reason_codes": [],
        },
    )
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: StorageReadiness(ready=True, local_only=True),
    )
    monkeypatch.setattr(
        capability_probes,
        "export_storage_readiness",
        lambda: StorageReadiness(ready=True, local_only=True),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("local", RuntimeEnvironment.LOCAL),
        ("docker", RuntimeEnvironment.LOCAL),
        ("test", RuntimeEnvironment.TEST),
        ("staging", RuntimeEnvironment.STAGING),
        ("production", RuntimeEnvironment.PRODUCTION),
    ],
)
def test_environment_names_are_centralized_and_normalized(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: RuntimeEnvironment,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", raw)
    assert resolve_runtime_environment().environment is expected


def test_invalid_environment_rejects_startup_and_has_fail_closed_public_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "private-invalid-environment")
    with pytest.raises(RuntimeEnvironmentError):
        resolve_runtime_environment()
    public_context = resolve_runtime_environment(fail_closed=True)
    assert public_context.environment is RuntimeEnvironment.PRODUCTION
    assert public_context.configuration_valid is False


@pytest.mark.parametrize("environment", ["local", "test", "docker"])
def test_disabled_auth_remains_explicitly_compatible_only_for_local_test(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", environment)
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    assert AuthSettings.from_environment().mode.value == "disabled"


def test_main_import_and_startup_contain_no_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    main_path = BACKEND / "app" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    forbidden_names = {"init_database_tables", "ensure_pgvector_extension", "create_all"}
    assert not any(
        isinstance(node, ast.Name) and node.id in forbidden_names
        for node in ast.walk(tree)
    )

    init_guard = Mock(side_effect=AssertionError("startup must not initialize tables"))
    extension_guard = Mock(side_effect=AssertionError("startup must not create extensions"))
    create_all_guard = Mock(side_effect=AssertionError("startup must not create tables"))
    monkeypatch.setattr(database_module, "init_database_tables", init_guard)
    monkeypatch.setattr(database_module, "ensure_pgvector_extension", extension_guard)
    monkeypatch.setattr(database_module.Base.metadata, "create_all", create_all_guard)
    database_probe = Mock(
        return_value={"status": "ok", "backend": "postgresql", "enabled": True}
    )
    migration_probe = Mock(
        return_value={
            "status": "ok",
            "current_revision": "head",
            "head_revision": "head",
            "version_table_present": True,
            "schema_matches_baseline": True,
            "reason_codes": [],
        }
    )
    pgvector_probe = Mock(return_value=True)
    storage_guard = Mock(side_effect=AssertionError("startup must not inspect storage"))
    monkeypatch.setattr(health_service, "check_database_connection", database_probe)
    monkeypatch.setattr(health_service, "migration_readiness", migration_probe)
    monkeypatch.setattr(capability_probes, "pgvector_available", pgvector_probe)
    monkeypatch.setattr(capability_probes, "asset_storage_readiness", storage_guard)
    monkeypatch.setattr(capability_probes, "export_storage_readiness", storage_guard)

    reloaded_main = importlib.reload(main_module)
    with TestClient(reloaded_main.app) as client:
        assert client.get("/health/live").status_code == 200

    database_probe.assert_called_once_with()
    migration_probe.assert_called_once_with()
    pgvector_probe.assert_called_once_with()
    assert storage_guard.call_count == 0
    assert init_guard.call_count == 0
    assert extension_guard.call_count == 0
    assert create_all_guard.call_count == 0


def test_live_health_has_zero_dependency_access(monkeypatch: pytest.MonkeyPatch) -> None:
    dependency_guard = Mock(side_effect=AssertionError("liveness touched a dependency"))
    monkeypatch.setattr(health_service, "check_database_connection", dependency_guard)
    monkeypatch.setattr(health_service, "migration_readiness", dependency_guard)
    monkeypatch.setattr(capability_probes, "pgvector_available", dependency_guard)
    monkeypatch.setattr(capability_probes, "asset_storage_readiness", dependency_guard)
    monkeypatch.setattr(capability_probes, "export_storage_readiness", dependency_guard)
    monkeypatch.setattr(health_service, "inspect_auth_configuration", dependency_guard)

    response = _isolated_health_client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "datahub-api",
        "environment": "local",
    }
    assert dependency_guard.call_count == 0


def test_local_startup_allows_readiness_failure_without_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_service,
        "startup_dependency_readiness",
        lambda: (
            {"status": "error", "reason_codes": ["MIGRATION_NOT_AT_HEAD"]},
            False,
        ),
    )
    with TestClient(main_module.app) as client:
        assert client.get("/health/live").status_code == 200


def test_ready_and_startup_do_not_create_missing_sqlite_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_database = tmp_path / "missing-readiness.db"
    monkeypatch.setattr(
        database_module,
        "DATABASE_URL",
        f"sqlite:///{missing_database.as_posix()}",
    )
    connect_guard = Mock(side_effect=AssertionError("probe must not create SQLite"))
    monkeypatch.setattr(database_module.engine, "connect", connect_guard)
    monkeypatch.setattr(
        health_service,
        "migration_readiness",
        lambda: {
            "status": "ok",
            "current_revision": "head",
            "head_revision": "head",
            "version_table_present": True,
            "schema_matches_baseline": True,
            "reason_codes": [],
        },
    )
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: StorageReadiness(ready=True, local_only=True),
    )
    monkeypatch.setattr(
        capability_probes,
        "export_storage_readiness",
        lambda: StorageReadiness(ready=True, local_only=True),
    )

    startup_payload, startup_ready = health_service.startup_dependency_readiness()
    response = _isolated_health_client().get("/health/ready")

    assert startup_ready is False
    assert startup_payload["checks"]["database"]["status"] == "error"
    assert response.status_code == 503
    assert response.json()["checks"]["database"]["status"] == "error"
    assert str(missing_database) not in response.text
    assert database_module._missing_file_backed_sqlite_database(
        "sqlite:///:memory:"
    ) is False
    assert not missing_database.exists()
    assert connect_guard.call_count == 0


def test_ready_health_reports_all_safe_read_only_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_healthy_readiness(monkeypatch)

    response = _isolated_health_client().get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert set(payload["checks"]) == {
        "database",
        "migration",
        "pgvector",
        "asset_storage",
        "export_storage",
        "auth",
    }
    assert payload["checks"]["pgvector"]["installed"] is True
    assert payload["checks"]["auth"]["safe_for_environment"] is True


def test_migration_readiness_uses_only_the_frozen_status_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = SimpleNamespace(
        ready=True,
        current_revision="revision-head",
        head_revision="revision-head",
        version_table_present=True,
        schema_matches_baseline=True,
        reason_codes=(),
    )
    check = Mock(return_value=status)
    monkeypatch.setattr(
        health_service,
        "import_module",
        lambda name: SimpleNamespace(check_migration_status=check)
        if name == "app.migration_status"
        else None,
    )

    assert health_service.migration_readiness() == {
        "status": "ok",
        "current_revision": "revision-head",
        "head_revision": "revision-head",
        "version_table_present": True,
        "schema_matches_baseline": True,
        "reason_codes": [],
    }
    check.assert_called_once_with()


def test_startup_readiness_is_read_only_and_migration_mismatch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_service,
        "check_database_connection",
        lambda: {"status": "ok", "backend": "postgresql", "enabled": True},
    )
    monkeypatch.setattr(
        health_service,
        "migration_readiness",
        lambda: {
            "status": "error",
            "current_revision": "old",
            "head_revision": "head",
            "version_table_present": True,
            "schema_matches_baseline": True,
            "reason_codes": ["MIGRATION_NOT_AT_HEAD"],
        },
    )
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    storage_guard = Mock(side_effect=AssertionError("startup must not inspect storage"))
    monkeypatch.setattr(capability_probes, "asset_storage_readiness", storage_guard)
    monkeypatch.setattr(capability_probes, "export_storage_readiness", storage_guard)

    payload, ready = health_service.startup_dependency_readiness()

    assert ready is False
    assert payload["reason_codes"] == ["MIGRATION_NOT_AT_HEAD"]
    assert payload["checks"]["pgvector"]["installed"] is True
    assert storage_guard.call_count == 0


@pytest.mark.parametrize(
    "component",
    ["database", "migration", "pgvector", "asset_storage", "export_storage", "auth"],
)
def test_ready_health_fails_503_for_each_required_component(
    monkeypatch: pytest.MonkeyPatch,
    component: str,
) -> None:
    _configure_healthy_readiness(monkeypatch)
    if component == "database":
        monkeypatch.setattr(
            health_service,
            "check_database_connection",
            lambda: {"status": "error", "backend": "postgresql", "enabled": True},
        )
    elif component == "migration":
        monkeypatch.setattr(
            health_service,
            "migration_readiness",
            lambda: {
                "status": "error",
                "current_revision": "old",
                "head_revision": "head",
                "version_table_present": True,
                "schema_matches_baseline": True,
                "reason_codes": ["MIGRATION_NOT_AT_HEAD"],
            },
        )
    elif component == "pgvector":
        monkeypatch.setattr(capability_probes, "pgvector_available", lambda: False)
    elif component == "asset_storage":
        monkeypatch.setattr(
            capability_probes,
            "asset_storage_readiness",
            lambda: StorageReadiness(ready=False, local_only=True),
        )
    elif component == "export_storage":
        monkeypatch.setattr(
            capability_probes,
            "export_storage_readiness",
            lambda: StorageReadiness(ready=False, local_only=True),
        )
    else:
        monkeypatch.setenv("DATAHUB_ENV", "production")
        monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")

    response = _isolated_health_client().get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["checks"][component]["status"] == "error"


def test_legacy_health_contract_is_public_and_never_creates_pgvector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_service,
        "check_database_connection",
        lambda: {"status": "ok", "backend": "postgresql", "enabled": True},
    )
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    ddl_guard = Mock(side_effect=AssertionError("health must not execute DDL"))
    monkeypatch.setattr(database_module, "ensure_pgvector_extension", ddl_guard)
    client = _isolated_health_client()

    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {
            "status",
            "service",
            "phase",
            "p2_phase",
            "database_status",
            "pgvector_status",
        }
        assert payload["pgvector_status"] == {
            "pgvector_available": True,
            "extension_create_ok": True,
            "backend": "postgresql",
        }
        assert payload["database_status"] == {
            "enabled": True,
            "backend": "postgresql",
            "status": "ok",
            "reason_code": None,
        }
    assert ddl_guard.call_count == 0


def test_legacy_health_sanitizes_database_errors_urls_hosts_and_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_url = "postgresql://private-user:private-pass@private-host/datahub"
    secret_path = "D:/private/database/location"
    monkeypatch.setattr(
        health_service,
        "check_database_connection",
        lambda: {
            "enabled": True,
            "status": "error",
            "backend": secret_url,
            "error": f"connection failed at {secret_url}",
            "host": "private-host",
            "path": secret_path,
        },
    )
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: False)
    client = _isolated_health_client()

    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["database_status"] == {
            "enabled": True,
            "backend": "unknown",
            "status": "error",
            "reason_code": "DATABASE_UNAVAILABLE",
        }
        for secret in (secret_url, "private-user", "private-pass", "private-host", secret_path):
            assert secret not in response.text


def test_production_disabled_or_missing_token_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    with pytest.raises(AuthConfigurationError) as disabled:
        AuthSettings.from_environment()
    assert disabled.value.issue is AuthConfigurationIssue.DISABLED_UNSAFE
    with pytest.raises(AuthConfigurationError):
        with TestClient(main_module.app):
            pass

    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    with pytest.raises(AuthConfigurationError) as missing:
        AuthSettings.from_environment()
    assert missing.value.issue is AuthConfigurationIssue.TOKEN_REQUIRED
    with pytest.raises(AuthConfigurationError):
        with TestClient(main_module.app):
            pass


def test_production_token_startup_is_valid_and_never_logs_secret(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "production-secret-that-must-not-leak"
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", secret)
    monkeypatch.setattr(
        health_service,
        "startup_dependency_readiness",
        lambda: ({"status": "ok", "reason_codes": []}, True),
    )

    with caplog.at_level(logging.INFO, logger="app.auth"):
        settings = validate_auth_configuration()

    assert settings.mode.value == "token"
    assert secret not in caplog.text
    with TestClient(main_module.app) as client:
        assert client.get("/health/live").status_code == 200


def test_production_rejects_read_only_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", "production-readiness-token")
    monkeypatch.setattr(
        health_service,
        "startup_dependency_readiness",
        lambda: (
            {"status": "error", "reason_codes": ["MIGRATION_NOT_AT_HEAD"]},
            False,
        ),
    )

    with pytest.raises(RuntimeReadinessError, match="MIGRATION_NOT_AT_HEAD"):
        with TestClient(main_module.app):
            pass


def test_query_tokens_are_rejected_and_header_auth_keeps_401_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_token = "query-test-admin-secret"
    service_token = "query-test-service-secret"
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", admin_token)
    monkeypatch.setenv("DATAHUB_SERVICE_TOKEN", service_token)
    isolated_app = FastAPI()

    @isolated_app.get(
        "/protected",
        dependencies=[Depends(require_permission(Permission.P1_READ))],
    )
    def protected() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(isolated_app)
    missing = client.get("/protected")
    forbidden = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    query = client.get(
        f"/protected?access_token={admin_token}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "AUTHORIZATION_DENIED"
    assert query.status_code == 400
    assert query.json()["detail"]["code"] == "AUTH_QUERY_TOKEN_FORBIDDEN"
    assert admin_token not in query.text


def test_health_openapi_is_public_and_protected_routes_keep_bearer_security() -> None:
    schema = main_module.app.openapi()
    for path in ("/health/live", "/health/ready", "/health", "/api/health"):
        assert not schema["paths"][path]["get"].get("security")
    assert schema["paths"]["/api/sources"]["get"]["security"] == [
        {"DataHubBearer": []}
    ]
