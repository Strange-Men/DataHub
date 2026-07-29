"""Forward-only compatibility for governed P3 asset publication."""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text


_TABLE = "reuse_asset_versions"
_SUPERSEDED_BY_FK = "fk_reuse_asset_versions_superseded_by"
_PUBLISH_KEY = "uq_reuse_asset_versions_publish_idempotency_key"
_ARCHIVE_KEY = "uq_reuse_asset_versions_archive_idempotency_key"
_CURRENT_PUBLISHED = "uq_reuse_asset_versions_current_published"
_SUPERSEDED_BY_INDEX = (
    "ix_reuse_asset_versions_superseded_by_asset_version_id"
)
_COLUMN_SQL = {
    "published_by_role": "VARCHAR(50)",
    "publish_request_id": "VARCHAR(200)",
    "publish_idempotency_key": "VARCHAR(200)",
    "superseded_by_asset_version_id": (
        "VARCHAR(200) REFERENCES reuse_asset_versions(id) "
        "ON DELETE RESTRICT"
    ),
    "archived_by_role": "VARCHAR(50)",
    "archive_request_id": "VARCHAR(200)",
    "archive_idempotency_key": "VARCHAR(200)",
}


def _table_exists(engine: Engine) -> bool:
    return inspect(engine).has_table(_TABLE)


def _protected_rows(connection) -> list[tuple[object, ...]]:
    return list(
        connection.execute(
            text(
                "SELECT id, status, generation_mode, content_hash, "
                "source_manifest_hash, published_at, superseded_at, "
                "archived_at FROM reuse_asset_versions ORDER BY id"
            )
        ).tuples()
    )


def _assert_single_current_slot(connection) -> None:
    duplicate = connection.execute(
        text(
            "SELECT project_id, asset_type "
            "FROM reuse_asset_versions "
            "WHERE status = 'published' "
            "GROUP BY project_id, asset_type "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add the current-published constraint while duplicate "
            "published asset slots exist."
        )


def _sqlite_upgrade(engine: Engine) -> bool:
    changed = False
    with engine.begin() as connection:
        columns = {
            str(row[1])
            for row in connection.exec_driver_sql(
                'PRAGMA table_info("reuse_asset_versions")'
            )
        }
        indexes = {
            str(row[1])
            for row in connection.exec_driver_sql(
                'PRAGMA index_list("reuse_asset_versions")'
            )
        }
        before = _protected_rows(connection)
        for column, definition in _COLUMN_SQL.items():
            if column in columns:
                continue
            connection.exec_driver_sql(
                f"ALTER TABLE reuse_asset_versions "
                f"ADD COLUMN {column} {definition}"
            )
            changed = True
        _assert_single_current_slot(connection)
        statements = {
            _PUBLISH_KEY: (
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_PUBLISH_KEY} ON reuse_asset_versions "
                "(publish_idempotency_key)"
            ),
            _ARCHIVE_KEY: (
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_ARCHIVE_KEY} ON reuse_asset_versions "
                "(archive_idempotency_key)"
            ),
            _CURRENT_PUBLISHED: (
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_CURRENT_PUBLISHED} ON reuse_asset_versions "
                "(project_id, asset_type) WHERE status = 'published'"
            ),
            _SUPERSEDED_BY_INDEX: (
                "CREATE INDEX IF NOT EXISTS "
                f"{_SUPERSEDED_BY_INDEX} ON reuse_asset_versions "
                "(superseded_by_asset_version_id)"
            ),
        }
        for name, statement in statements.items():
            if name not in indexes:
                connection.exec_driver_sql(statement)
                changed = True
        if _protected_rows(connection) != before:
            raise RuntimeError(
                "M6 compatibility changed existing governed asset versions."
            )
        violations = list(
            connection.exec_driver_sql("PRAGMA foreign_key_check")
        )
        if violations:
            raise RuntimeError(
                "M6 compatibility broke foreign-key integrity."
            )
    return changed


def _postgresql_upgrade(engine: Engine) -> bool:
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns(_TABLE)}
    foreign_keys = {
        item.get("name") for item in inspector.get_foreign_keys(_TABLE)
    }
    indexes = {item["name"] for item in inspector.get_indexes(_TABLE)}
    unique_constraints = {
        item["name"] for item in inspector.get_unique_constraints(_TABLE)
    }
    changed = False
    with engine.begin() as connection:
        before = _protected_rows(connection)
        for column, definition in _COLUMN_SQL.items():
            if column in columns:
                continue
            if column == "superseded_by_asset_version_id":
                connection.exec_driver_sql(
                    "ALTER TABLE reuse_asset_versions "
                    "ADD COLUMN superseded_by_asset_version_id VARCHAR(200)"
                )
            else:
                connection.exec_driver_sql(
                    f"ALTER TABLE reuse_asset_versions "
                    f"ADD COLUMN {column} {definition}"
                )
            changed = True
        if _SUPERSEDED_BY_FK not in foreign_keys:
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                f'ADD CONSTRAINT "{_SUPERSEDED_BY_FK}" '
                "FOREIGN KEY (superseded_by_asset_version_id) "
                "REFERENCES reuse_asset_versions (id) ON DELETE RESTRICT"
            )
            changed = True
        _assert_single_current_slot(connection)
        if _PUBLISH_KEY not in indexes | unique_constraints:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_PUBLISH_KEY} ON reuse_asset_versions "
                "(publish_idempotency_key)"
            )
            changed = True
        if _ARCHIVE_KEY not in indexes | unique_constraints:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_ARCHIVE_KEY} ON reuse_asset_versions "
                "(archive_idempotency_key)"
            )
            changed = True
        if _CURRENT_PUBLISHED not in indexes:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{_CURRENT_PUBLISHED} ON reuse_asset_versions "
                "(project_id, asset_type) WHERE status = 'published'"
            )
            changed = True
        if _SUPERSEDED_BY_INDEX not in indexes:
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS "
                f"{_SUPERSEDED_BY_INDEX} ON reuse_asset_versions "
                "(superseded_by_asset_version_id)"
            )
            changed = True
        if _protected_rows(connection) != before:
            raise RuntimeError(
                "M6 compatibility changed existing governed asset versions."
            )
    return changed


def ensure_asset_publication_compatibility(engine: Engine) -> bool:
    """Add publication audit and current-slot constraints without data loss."""

    if not _table_exists(engine):
        return False
    if engine.dialect.name == "sqlite":
        return _sqlite_upgrade(engine)
    if engine.dialect.name == "postgresql":
        return _postgresql_upgrade(engine)
    raise RuntimeError("Unsupported database for P3 M6 compatibility.")


__all__ = ["ensure_asset_publication_compatibility"]
