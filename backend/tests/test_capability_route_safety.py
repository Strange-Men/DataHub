"""Route, OpenAPI, storage-contract, and side-effect safety tests."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import asset_storage, capability_probes, p3_export_storage  # noqa: E402
import app.database as database_module  # noqa: E402
from app.auth import ROLE_TOKEN_ENV  # noqa: E402
from app.capability_routes import router  # noqa: E402
from app.capability_service import get_capabilities  # noqa: E402
from app.storage_readiness import StorageReadiness  # noqa: E402


_REAL_DATABASE_PROBE = capability_probes.database_available
_REAL_PGVECTOR_PROBE = capability_probes.pgvector_available
_REAL_ASSET_STORAGE_PROBE = capability_probes.asset_storage_readiness
_REAL_EXPORT_STORAGE_PROBE = capability_probes.export_storage_readiness


class _Result:
    @staticmethod
    def scalar_one() -> bool:
        return True


class _Connection:
    def __init__(self, statements: list[str]) -> None:
        self.statements = statements

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement):
        self.statements.append(str(statement))
        return _Result()


class _RecordingEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, statements: list[str]) -> None:
        self.statements = statements

    def connect(self) -> _Connection:
        return _Connection(self.statements)


@pytest.fixture(autouse=True)
def capability_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "local")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    for name in ROLE_TOKEN_ENV.values():
        monkeypatch.delenv(name, raising=False)
    for name in (
        "RENDER",
        "P3_LLM_DRAFT_ENABLED",
        "UNIFIED_RETRIEVAL_ENABLED",
        "P2_RETRIEVAL_ENABLED",
        "UNIFIED_RETRIEVAL_SHADOW_MODE",
        "CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(capability_probes, "database_available", lambda: True)
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: capability_probes.StorageProbeResult(ready=True, local_only=True),
    )
    monkeypatch.setattr(
        capability_probes,
        "export_storage_readiness",
        lambda: capability_probes.StorageProbeResult(ready=True, local_only=True),
    )


def _assert_select_only(statements: list[str]) -> None:
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert not any(
        keyword in " ".join(statements).upper()
        for keyword in ("CREATE ", "ALTER ", "DROP ", "INSERT ", "UPDATE ", "DELETE ")
    )


def test_public_route_needs_no_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", "configured-but-not-sent")
    isolated_app = FastAPI()
    isolated_app.include_router(router)

    response = TestClient(isolated_app).get("/api/capabilities")

    assert response.status_code == 200
    assert response.json()["auth"] == {
        "mode": "token",
        "safe_for_environment": True,
    }
    operation = isolated_app.openapi()["paths"]["/api/capabilities"]["get"]
    assert not operation.get("security")


def test_openapi_separates_runtime_and_planned_module_status_enums() -> None:
    isolated_app = FastAPI()
    isolated_app.include_router(router)
    schemas = isolated_app.openapi()["components"]["schemas"]
    module_properties = schemas["ModuleCapabilities"]["properties"]

    assert module_properties["p1"]["$ref"].endswith("/RuntimeModuleCapability")
    assert module_properties["p4"]["$ref"].endswith("/PlannedModuleCapability")
    runtime_status_ref = schemas["RuntimeModuleCapability"]["properties"]["status"][
        "$ref"
    ]
    planned_status_ref = schemas["PlannedModuleCapability"]["properties"]["status"][
        "$ref"
    ]
    runtime_status_schema = runtime_status_ref.rsplit("/", 1)[-1]
    planned_status_schema = planned_status_ref.rsplit("/", 1)[-1]
    assert schemas[runtime_status_schema]["enum"] == [
        "available",
        "local_only",
        "degraded",
        "unavailable",
    ]
    assert schemas[planned_status_schema]["enum"] == ["planned"]


def test_storage_factories_and_readiness_share_configuration_resolvers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "shared-asset-root"
    export_root = tmp_path / "shared-export-root"
    asset_configuration = asset_storage._AssetStorageConfiguration(
        root=asset_root,
        persistent_deployment=True,
    )
    export_configuration = p3_export_storage._P3ExportStorageConfiguration(
        root=export_root,
    )
    asset_resolver = Mock(return_value=asset_configuration)
    export_resolver = Mock(return_value=export_configuration)
    asset_directory_probe = Mock(return_value=True)
    export_directory_probe = Mock(return_value=True)
    asset_adapter = object()
    export_adapter = object()
    asset_factory = Mock(return_value=asset_adapter)
    export_factory = Mock(return_value=export_adapter)
    monkeypatch.setattr(asset_storage, "_asset_storage_configuration", asset_resolver)
    monkeypatch.setattr(
        p3_export_storage,
        "_p3_export_storage_configuration",
        export_resolver,
    )
    monkeypatch.setattr(asset_storage, "existing_directory_ready", asset_directory_probe)
    monkeypatch.setattr(
        p3_export_storage,
        "existing_directory_ready",
        export_directory_probe,
    )
    monkeypatch.setattr(asset_storage, "LocalFilesystemAssetStorage", asset_factory)
    monkeypatch.setattr(
        p3_export_storage,
        "LocalFilesystemP3ExportStorage",
        export_factory,
    )

    assert asset_storage.check_asset_storage_readiness() == StorageReadiness(True, False)
    assert p3_export_storage.check_p3_export_storage_readiness() == StorageReadiness(
        True, True
    )
    assert asset_storage.get_asset_storage_adapter() is asset_adapter
    assert p3_export_storage.get_p3_export_storage() is export_adapter
    assert asset_resolver.call_count == 2
    assert export_resolver.call_count == 2
    asset_directory_probe.assert_called_once_with(asset_root)
    export_directory_probe.assert_called_once_with(
        export_root,
        reject_root_symlink=True,
    )
    asset_factory.assert_called_once_with(asset_root)
    export_factory.assert_called_once_with(export_root)


def test_response_never_exposes_secrets_paths_urls_or_probe_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_token = "capability-secret-token"
    secret_database_url = "postgresql://secret-user:secret-pass@private-host/datahub"
    secret_provider_url = "https://private-provider.example/v1"
    asset_root = tmp_path / "private-assets"
    export_root = tmp_path / "private-exports"
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", secret_token)
    monkeypatch.setenv("DATABASE_URL", secret_database_url)
    monkeypatch.setenv("P3_LLM_BASE_URL", secret_provider_url)
    monkeypatch.setenv("P3_LLM_API_KEY", "private-provider-key")
    monkeypatch.setenv("ASSET_STORAGE_ROOT", str(asset_root))
    monkeypatch.setenv("P3_EXPORT_STORAGE_ROOT", str(export_root))
    monkeypatch.setattr(
        capability_probes,
        "database_available",
        lambda: (_ for _ in ()).throw(RuntimeError(secret_database_url)),
    )
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: (_ for _ in ()).throw(RuntimeError(str(asset_root))),
    )

    response_text = get_capabilities().model_dump_json()

    for private_value in (
        secret_token,
        secret_database_url,
        secret_provider_url,
        "private-provider-key",
        str(asset_root),
        str(export_root),
        "private-host",
    ):
        assert private_value not in response_text


def test_probes_use_only_metadata_and_select_without_creating_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "assets"
    export_root = tmp_path / "exports"
    asset_root.mkdir()
    export_root.mkdir()
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ASSET_STORAGE_ROOT", str(asset_root))
    monkeypatch.setenv("P3_EXPORT_STORAGE_BACKEND", "local_filesystem")
    monkeypatch.setenv("P3_EXPORT_STORAGE_ROOT", str(export_root))
    before = {
        asset_root: tuple(asset_root.iterdir()),
        export_root: tuple(export_root.iterdir()),
    }
    statements: list[str] = []
    monkeypatch.setattr(capability_probes, "engine", _RecordingEngine(statements))
    monkeypatch.setattr(capability_probes, "pgvector_available", _REAL_PGVECTOR_PROBE)
    monkeypatch.setattr(
        capability_probes, "asset_storage_readiness", _REAL_ASSET_STORAGE_PROBE
    )
    monkeypatch.setattr(
        capability_probes, "export_storage_readiness", _REAL_EXPORT_STORAGE_PROBE
    )
    ddl_guard = Mock(side_effect=AssertionError("DDL must not run"))
    monkeypatch.setattr(database_module, "ensure_pgvector_extension", ddl_guard)

    assert capability_probes.pgvector_available() is True
    assert capability_probes.asset_storage_readiness().ready is True
    assert capability_probes.export_storage_readiness().ready is True

    _assert_select_only(statements)
    assert ddl_guard.call_count == 0
    assert tuple(asset_root.iterdir()) == before[asset_root]
    assert tuple(export_root.iterdir()) == before[export_root]


def test_real_router_service_probe_chain_is_select_only_and_zero_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "route-assets"
    export_root = tmp_path / "route-exports"
    asset_root.mkdir()
    export_root.mkdir()
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ASSET_STORAGE_ROOT", str(asset_root))
    monkeypatch.setenv("P3_EXPORT_STORAGE_BACKEND", "local_filesystem")
    monkeypatch.setenv("P3_EXPORT_STORAGE_ROOT", str(export_root))
    before = {
        asset_root: tuple(asset_root.iterdir()),
        export_root: tuple(export_root.iterdir()),
    }
    statements: list[str] = []
    fake_engine = _RecordingEngine(statements)
    monkeypatch.setattr(database_module, "engine", fake_engine)
    monkeypatch.setattr(capability_probes, "engine", fake_engine)
    monkeypatch.setattr(capability_probes, "database_available", _REAL_DATABASE_PROBE)
    monkeypatch.setattr(capability_probes, "pgvector_available", _REAL_PGVECTOR_PROBE)
    monkeypatch.setattr(
        capability_probes, "asset_storage_readiness", _REAL_ASSET_STORAGE_PROBE
    )
    monkeypatch.setattr(
        capability_probes, "export_storage_readiness", _REAL_EXPORT_STORAGE_PROBE
    )
    ddl_guard = Mock(side_effect=AssertionError("DDL must not run"))
    mkdir_guard = Mock(side_effect=AssertionError("readiness must not mkdir"))
    monkeypatch.setattr(database_module, "ensure_pgvector_extension", ddl_guard)
    monkeypatch.setattr(Path, "mkdir", mkdir_guard)
    isolated_app = FastAPI()
    isolated_app.include_router(router)

    response = TestClient(isolated_app).get("/api/capabilities")

    assert response.status_code == 200
    assert response.json()["infrastructure"] == {
        "database": "available",
        "pgvector": "available",
        "asset_storage": "local_only",
        "export_storage": "local_only",
    }
    assert len(statements) == 2
    _assert_select_only(statements)
    assert ddl_guard.call_count == 0
    assert mkdir_guard.call_count == 0
    assert tuple(asset_root.iterdir()) == before[asset_root]
    assert tuple(export_root.iterdir()) == before[export_root]


def test_main_registers_capability_router_without_importing_startup_module() -> None:
    main_path = BACKEND / "app" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    imports_router = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.capability_routes"
        and any(
            alias.name == "router" and alias.asname == "capability_router"
            for alias in node.names
        )
        for node in tree.body
    )
    registers_router = any(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "include_router"
        and any(
            isinstance(argument, ast.Name) and argument.id == "capability_router"
            for argument in node.value.args
        )
        for node in tree.body
    )
    assert imports_router is True
    assert registers_router is True
