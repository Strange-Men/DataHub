"""Explicit Alembic upgrade and strict legacy-schema adoption workflow."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection, Engine

from app.migration_schema_validation import (
    SchemaValidation,
    validate_baseline_schema,
)
from migrations.baseline_schema import BASELINE_REVISION


_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _ROOT / "alembic.ini"


class MigrationAdoptionError(RuntimeError):
    """Raised before stamping when a legacy schema is not exactly equivalent."""


@dataclass(frozen=True)
class MigrationAdoptionResult:
    action: str
    revision: str
    schema_matches_baseline: bool


def _database_url(database_url: str | None) -> str:
    if database_url:
        return database_url
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        return configured
    return f"sqlite:///{(_ROOT / 'datahub.db').as_posix()}"


def make_alembic_config(
    database_url: str | None = None,
    *,
    connection: Connection | None = None,
) -> Config:
    config = Config(str(_ALEMBIC_INI))
    # ConfigParser interpolation treats percent as special; URL values do not.
    config.set_main_option("sqlalchemy.url", _database_url(database_url).replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def get_head_revision() -> str:
    head = ScriptDirectory.from_config(make_alembic_config()).get_current_head()
    if head is None:
        raise MigrationAdoptionError("Alembic head revision is unavailable.")
    return head


def _current_heads(connection: Connection) -> tuple[str, ...]:
    return tuple(MigrationContext.configure(connection).get_current_heads())


def _upgrade_with_connection(connection: Connection, database_url: str) -> None:
    config = make_alembic_config(database_url, connection=connection)
    command.upgrade(config, "head")


def adopt_or_upgrade(database_url: str | None = None) -> MigrationAdoptionResult:
    """Upgrade an empty/versioned DB or stamp only an exactly matching legacy DB."""

    url = _database_url(database_url)
    engine: Engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            inspector = inspect(connection)
            version_table_present = inspector.has_table("alembic_version")
            business_tables = set(inspector.get_table_names()) - {"alembic_version"}
            current_heads = _current_heads(connection) if version_table_present else ()
            if not current_heads and business_tables:
                validation = validate_baseline_schema(connection)
                if not validation.matches:
                    codes = ",".join(validation.mismatches)
                    raise MigrationAdoptionError(
                        f"Legacy schema does not match the immutable baseline: {codes}"
                    )
                command.stamp(
                    make_alembic_config(url, connection=connection),
                    BASELINE_REVISION,
                )
                action = "adopted"
            else:
                action = "upgraded"

            _upgrade_with_connection(connection, url)
            final_validation = validate_baseline_schema(connection)
            final_heads = _current_heads(connection)
            if not final_validation.matches or final_heads != (get_head_revision(),):
                raise MigrationAdoptionError(
                    "Database did not reach the expected migration head safely."
                )
            return MigrationAdoptionResult(
                action=action,
                revision=final_heads[0],
                schema_matches_baseline=True,
            )
    finally:
        engine.dispose()


__all__ = [
    "MigrationAdoptionError",
    "MigrationAdoptionResult",
    "SchemaValidation",
    "adopt_or_upgrade",
    "get_head_revision",
    "make_alembic_config",
    "validate_baseline_schema",
]
