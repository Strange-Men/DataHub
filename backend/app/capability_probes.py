"""Read-only infrastructure probes used by public capability discovery."""

from __future__ import annotations

from sqlalchemy import text

from app.asset_storage import check_asset_storage_readiness
from app.database import check_database_connection, engine
from app.p3_export_storage import check_p3_export_storage_readiness
from app.storage_readiness import StorageReadiness as StorageProbeResult


def database_available() -> bool:
    """Return database reachability without exposing connection details."""

    try:
        return check_database_connection().get("status") == "ok"
    except Exception:
        return False


def pgvector_available() -> bool:
    """Return whether pgvector is installed, using metadata-only SQL."""

    try:
        if engine.dialect.name != "postgresql":
            return False
        with engine.connect() as connection:
            installed = connection.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                    ")"
                )
            ).scalar_one()
        return bool(installed)
    except Exception:
        return False


def asset_storage_readiness() -> StorageProbeResult:
    """Delegate P2 readiness to its storage module's shared configuration."""

    return check_asset_storage_readiness()


def export_storage_readiness() -> StorageProbeResult:
    """Delegate P3 readiness to its storage module's shared configuration."""

    return check_p3_export_storage_readiness()


__all__ = [
    "StorageProbeResult",
    "asset_storage_readiness",
    "database_available",
    "export_storage_readiness",
    "pgvector_available",
]
