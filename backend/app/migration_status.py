"""Pure-read Alembic head and immutable-schema readiness checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.url import make_url

from app.migration_adoption import (
    _database_url,
    get_head_revision,
)
from app.migration_schema_validation import validate_baseline_schema
from migrations.baseline_schema import BASELINE_REVISION
from migrations.baseline_schema import BASELINE_TABLE_NAMES


@dataclass(frozen=True)
class MigrationStatus:
    ready: bool
    current_revision: str | None
    head_revision: str
    version_table_present: bool
    schema_matches_baseline: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def check_migration_status(
    database_url: str | None = None,
    *,
    deep_validate: bool = False,
) -> MigrationStatus:
    """Inspect migration state without creating tables, extensions, or version rows.

    The default readiness hot path checks the immutable revision and exact table
    set only. ``deep_validate=True`` additionally performs the per-column,
    constraint, and index comparison used by legacy-schema adoption.
    """

    head = BASELINE_REVISION
    engine = None
    try:
        head = get_head_revision()
        resolved_url = _database_url(database_url)
        parsed_url = make_url(resolved_url)
        if parsed_url.get_backend_name() == "sqlite" and parsed_url.database not in {
            None,
            "",
            ":memory:",
        }:
            sqlite_path = Path(parsed_url.database)
            if not sqlite_path.exists():
                return MigrationStatus(
                    ready=False,
                    current_revision=None,
                    head_revision=head,
                    version_table_present=False,
                    schema_matches_baseline=False,
                    reason_codes=("MIGRATION_REQUIRED", "SCHEMA_MISMATCH"),
                )
        engine = create_engine(resolved_url, pool_pre_ping=True)
        with engine.connect() as connection:
            inspector = inspect(connection)
            actual_tables = set(inspector.get_table_names())
            version_table_present = "alembic_version" in actual_tables
            business_tables = actual_tables - {"alembic_version"}
            current_heads = (
                tuple(MigrationContext.configure(connection).get_current_heads())
                if version_table_present
                else ()
            )
            current = current_heads[0] if len(current_heads) == 1 else None
            table_set_matches = business_tables == set(BASELINE_TABLE_NAMES)
            schema_matches = table_set_matches and current == head
            if deep_validate:
                schema_matches = validate_baseline_schema(connection).matches
            reasons: list[str] = []
            if not version_table_present:
                reasons.append("MIGRATION_REQUIRED")
            elif current != head:
                reasons.append("MIGRATION_NOT_AT_HEAD")
            if not schema_matches:
                reasons.append("SCHEMA_MISMATCH")
            return MigrationStatus(
                ready=not reasons,
                current_revision=current,
                head_revision=head,
                version_table_present=version_table_present,
                schema_matches_baseline=schema_matches,
                reason_codes=tuple(reasons),
            )
    except Exception:
        return MigrationStatus(
            ready=False,
            current_revision=None,
            head_revision=head,
            version_table_present=False,
            schema_matches_baseline=False,
            reason_codes=("MIGRATION_STATUS_UNAVAILABLE",),
        )
    finally:
        if engine is not None:
            engine.dispose()


__all__ = ["MigrationStatus", "check_migration_status"]
