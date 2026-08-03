"""Pure-read liveness, readiness, and legacy health aggregation."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from app import capability_probes
from app.auth import inspect_auth_configuration
from app.database import check_database_connection
from app.runtime_environment import resolve_runtime_environment


SERVICE_NAME = "datahub-api"
_SAFE_DATABASE_BACKENDS = frozenset({"postgresql", "sqlite", "unknown"})


def live_health() -> dict[str, object]:
    """Report process liveness without touching external dependencies."""

    context = resolve_runtime_environment(fail_closed=True)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "environment": context.environment.value,
    }


def _reason_values(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(getattr(value, "value", value)) for value in values]


def migration_readiness() -> dict[str, object]:
    """Call the migration subsystem through a narrow, optional pure-read boundary."""

    try:
        module = import_module("app.migration_status")
        result = module.check_migration_status()
    except Exception:
        return {
            "status": "error",
            "current_revision": None,
            "head_revision": None,
            "version_table_present": False,
            "schema_matches_baseline": False,
            "reason_codes": ["MIGRATION_STATUS_UNAVAILABLE"],
        }

    ready = bool(getattr(result, "ready", False))
    return {
        "status": "ok" if ready else "error",
        "current_revision": getattr(result, "current_revision", None),
        "head_revision": getattr(result, "head_revision", None),
        "version_table_present": bool(getattr(result, "version_table_present", False)),
        "schema_matches_baseline": bool(
            getattr(result, "schema_matches_baseline", False)
        ),
        "reason_codes": _reason_values(getattr(result, "reason_codes", ())),
    }


def _safe_database_status() -> dict[str, object]:
    try:
        result = check_database_connection()
    except Exception:
        result = {}
    ready = result.get("status") == "ok"
    raw_backend = str(result.get("backend", "unknown"))
    backend = raw_backend if raw_backend in _SAFE_DATABASE_BACKENDS else "unknown"
    return {
        "enabled": bool(result.get("enabled", True)),
        "backend": backend,
        "status": "ok" if ready else "error",
        "reason_code": None if ready else "DATABASE_UNAVAILABLE",
    }


def _database_readiness() -> tuple[dict[str, object], bool]:
    result = _safe_database_status()
    ready = result["status"] == "ok"
    return {
        "status": result["status"],
        "backend": result["backend"],
        "reason_codes": [] if ready else ["DATABASE_UNAVAILABLE"],
    }, ready


def _pgvector_readiness() -> tuple[dict[str, object], bool]:
    try:
        installed = bool(capability_probes.pgvector_available())
    except Exception:
        installed = False
    return {
        "status": "ok" if installed else "error",
        "installed": installed,
        "reason_codes": [] if installed else ["PGVECTOR_UNAVAILABLE"],
    }, installed


def _storage_readiness(
    probe: Any,
    unavailable_code: str,
) -> tuple[dict[str, object], bool]:
    try:
        result = probe()
        ready = bool(result.ready)
        local_only = bool(result.local_only)
    except Exception:
        ready = False
        local_only = False
    return {
        "status": "ok" if ready else "error",
        "local_only": local_only,
        "reason_codes": [] if ready else [unavailable_code],
    }, ready


def _auth_readiness() -> tuple[dict[str, object], bool]:
    context = resolve_runtime_environment(fail_closed=True)
    auth = inspect_auth_configuration(context)
    ready = (
        context.configuration_valid
        and auth.configuration_valid
        and auth.safe_for_environment
    )
    reason_codes: list[str] = []
    if not context.configuration_valid or not auth.configuration_valid:
        reason_codes.append("AUTH_CONFIGURATION_INVALID")
    elif not auth.safe_for_environment:
        reason_codes.append("AUTH_UNSAFE_FOR_ENVIRONMENT")
    return {
        "status": "ok" if ready else "error",
        "mode": auth.mode.value,
        "safe_for_environment": auth.safe_for_environment,
        "reason_codes": reason_codes,
    }, ready


def ready_health() -> tuple[dict[str, object], bool]:
    """Aggregate only safe, read-only readiness checks."""

    context = resolve_runtime_environment(fail_closed=True)
    database, database_ready = _database_readiness()
    migration = migration_readiness()
    migration_ready = migration["status"] == "ok"
    pgvector, pgvector_ready = _pgvector_readiness()
    asset_storage, asset_ready = _storage_readiness(
        capability_probes.asset_storage_readiness,
        "ASSET_STORAGE_UNAVAILABLE",
    )
    export_storage, export_ready = _storage_readiness(
        capability_probes.export_storage_readiness,
        "EXPORT_STORAGE_UNAVAILABLE",
    )
    auth, auth_ready = _auth_readiness()
    ready = all(
        (
            database_ready,
            migration_ready,
            pgvector_ready,
            asset_ready,
            export_ready,
            auth_ready,
        )
    )
    return {
        "status": "ok" if ready else "error",
        "service": SERVICE_NAME,
        "environment": context.environment.value,
        "checks": {
            "database": database,
            "migration": migration,
            "pgvector": pgvector,
            "asset_storage": asset_storage,
            "export_storage": export_storage,
            "auth": auth,
        },
    }, ready


def startup_dependency_readiness() -> tuple[dict[str, object], bool]:
    """Check only DB, migration head, and installed pgvector for startup policy."""

    database, database_ready = _database_readiness()
    migration = migration_readiness()
    migration_ready = migration["status"] == "ok"
    pgvector, pgvector_ready = _pgvector_readiness()
    reason_codes = [
        *database["reason_codes"],
        *migration["reason_codes"],
        *pgvector["reason_codes"],
    ]
    ready = database_ready and migration_ready and pgvector_ready
    return {
        "status": "ok" if ready else "error",
        "checks": {
            "database": database,
            "migration": migration,
            "pgvector": pgvector,
        },
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }, ready


def legacy_health() -> dict[str, object]:
    """Preserve the legacy payload while replacing DDL with installed-state reads."""

    database = _safe_database_status()
    try:
        pgvector_installed = bool(capability_probes.pgvector_available())
    except Exception:
        pgvector_installed = False
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "phase": "P1-M24.3",
        "p2_phase": "P2-M8.3",
        "database_status": database,
        "pgvector_status": {
            "pgvector_available": pgvector_installed,
            "extension_create_ok": pgvector_installed,
            "backend": database["backend"],
        },
    }


__all__ = [
    "legacy_health",
    "live_health",
    "migration_readiness",
    "ready_health",
    "startup_dependency_readiness",
]
