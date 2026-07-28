"""Forward-only compatibility for P3 manual revisions and human review."""

from __future__ import annotations

import re

from sqlalchemy import Engine, inspect, text
from sqlalchemy.schema import CreateTable

from app.p3_reuse_models import ReuseAssetVersion


_TABLE = "reuse_asset_versions"
_OLD_CHECK = "generation_mode IN ('deterministic_template', 'llm_draft')"
_NEW_CHECK = (
    "generation_mode IN "
    "('deterministic_template', 'llm_draft', 'manual_revision')"
)
_SQLITE_SHADOW = "reuse_asset_versions__p3_m5_new"
_PARENT_FK = "fk_reuse_asset_versions_parent"
_MANUAL_PARENT_CHECK = "ck_reuse_asset_versions_manual_parent_required"
_NOT_SELF_CHECK = "ck_reuse_asset_versions_parent_not_self"


def _table_exists(engine: Engine) -> bool:
    return inspect(engine).has_table(_TABLE)


def _sqlite_table_sql(connection, table: str) -> str | None:
    return connection.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = :table"
        ),
        {"table": table},
    ).scalar_one_or_none()


def _sqlite_columns(connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.exec_driver_sql(
            f'PRAGMA table_info("{table}")'
        )
    ]


def _quoted_columns(columns: list[str]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


def _sqlite_upgrade(engine: Engine) -> bool:
    with engine.connect() as connection:
        table_sql = _sqlite_table_sql(connection, _TABLE)
        if table_sql is None:
            return False
        has_parent = "parent_asset_version_id" in table_sql
        has_manual = "manual_revision" in table_sql
        if has_parent and has_manual:
            return False
        if _OLD_CHECK not in table_sql:
            raise RuntimeError(
                "Unsupported reuse_asset_versions generation-mode constraint."
            )
        existing_columns = _sqlite_columns(connection, _TABLE)
        indexes = list(
            connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' AND tbl_name = :table "
                    "AND sql IS NOT NULL ORDER BY name"
                ),
                {"table": _TABLE},
            ).scalars()
        )
        before = list(
            connection.execute(
                text(
                    "SELECT id, generation_mode, content_hash, "
                    "source_manifest_hash FROM reuse_asset_versions ORDER BY id"
                )
            ).tuples()
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.commit()
        try:
            with connection.begin():
                connection.exec_driver_sql(
                    f"DROP TABLE IF EXISTS {_SQLITE_SHADOW}"
                )
                shadow_sql = str(
                    CreateTable(ReuseAssetVersion.__table__).compile(
                        dialect=connection.dialect
                    )
                )
                shadow_sql = re.sub(
                    rf"^CREATE TABLE\s+[\"`]?{_TABLE}[\"`]?",
                    f"CREATE TABLE {_SQLITE_SHADOW}",
                    shadow_sql.lstrip(),
                    count=1,
                    flags=re.IGNORECASE,
                )
                connection.exec_driver_sql(shadow_sql)
                columns_sql = _quoted_columns(existing_columns)
                connection.exec_driver_sql(
                    f"INSERT INTO {_SQLITE_SHADOW} ({columns_sql}) "
                    f"SELECT {columns_sql} FROM {_TABLE}"
                )
                connection.exec_driver_sql(f"DROP TABLE {_TABLE}")
                connection.exec_driver_sql(
                    f"ALTER TABLE {_SQLITE_SHADOW} RENAME TO {_TABLE}"
                )
                for index_sql in indexes:
                    connection.exec_driver_sql(index_sql)
                after = list(
                    connection.execute(
                        text(
                            "SELECT id, generation_mode, content_hash, "
                            "source_manifest_hash "
                            "FROM reuse_asset_versions ORDER BY id"
                        )
                    ).tuples()
                )
                if after != before:
                    raise RuntimeError(
                        "M5 compatibility changed existing asset versions."
                    )
                if any(
                    row[0] is not None
                    for row in connection.execute(
                        text(
                            "SELECT parent_asset_version_id "
                            "FROM reuse_asset_versions"
                        )
                    )
                ):
                    raise RuntimeError(
                        "M5 compatibility assigned an unexpected parent."
                    )
                violations = list(
                    connection.exec_driver_sql("PRAGMA foreign_key_check")
                )
                if violations:
                    raise RuntimeError(
                        "M5 compatibility broke foreign-key integrity."
                    )
        finally:
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    return True


def _postgresql_upgrade(engine: Engine) -> bool:
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns(_TABLE)}
    checks = {
        item["name"]: str(item["sqltext"])
        for item in inspector.get_check_constraints(_TABLE)
    }
    foreign_keys = {
        item.get("name")
        for item in inspector.get_foreign_keys(_TABLE)
    }
    generation_check = checks.get("reuse_generation_mode", "")
    has_manual = "manual_revision" in generation_check
    has_parent = "parent_asset_version_id" in columns
    has_parent_fk = _PARENT_FK in foreign_keys
    has_manual_check = _MANUAL_PARENT_CHECK in checks
    has_self_check = _NOT_SELF_CHECK in checks
    if all(
        (
            has_manual,
            has_parent,
            has_parent_fk,
            has_manual_check,
            has_self_check,
        )
    ):
        return False
    if not has_manual and not all(
        value in generation_check
        for value in ("deterministic_template", "llm_draft")
    ):
        raise RuntimeError(
            "Unsupported reuse_asset_versions generation-mode constraint."
        )
    with engine.begin() as connection:
        before = list(
            connection.execute(
                text(
                    "SELECT id, generation_mode, content_hash, "
                    "source_manifest_hash FROM reuse_asset_versions ORDER BY id"
                )
            ).tuples()
        )
        if not has_parent:
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                "ADD COLUMN parent_asset_version_id VARCHAR(200)"
            )
        if not has_parent_fk:
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                f'ADD CONSTRAINT "{_PARENT_FK}" '
                "FOREIGN KEY (parent_asset_version_id) "
                "REFERENCES reuse_asset_versions (id) ON DELETE RESTRICT"
            )
        if not has_manual:
            connection.exec_driver_sql(
                'ALTER TABLE reuse_asset_versions '
                'DROP CONSTRAINT "reuse_generation_mode"'
            )
            connection.exec_driver_sql(
                'ALTER TABLE reuse_asset_versions '
                'ADD CONSTRAINT "reuse_generation_mode" '
                f"CHECK ({_NEW_CHECK})"
            )
        if not has_manual_check:
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                f'ADD CONSTRAINT "{_MANUAL_PARENT_CHECK}" '
                "CHECK (generation_mode != 'manual_revision' "
                "OR parent_asset_version_id IS NOT NULL)"
            )
        if not has_self_check:
            connection.exec_driver_sql(
                "ALTER TABLE reuse_asset_versions "
                f'ADD CONSTRAINT "{_NOT_SELF_CHECK}" '
                "CHECK (parent_asset_version_id IS NULL "
                "OR parent_asset_version_id != id)"
            )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS "
            "ix_reuse_asset_versions_parent_asset_version_id "
            "ON reuse_asset_versions (parent_asset_version_id)"
        )
        after = list(
            connection.execute(
                text(
                    "SELECT id, generation_mode, content_hash, "
                    "source_manifest_hash FROM reuse_asset_versions ORDER BY id"
                )
            ).tuples()
        )
        if after != before:
            raise RuntimeError(
                "M5 compatibility changed existing asset versions."
            )
    return True


def ensure_manual_revision_review_compatibility(engine: Engine) -> bool:
    """Add manual-revision compatibility without rewriting governed data."""

    if not _table_exists(engine):
        return False
    if engine.dialect.name == "sqlite":
        return _sqlite_upgrade(engine)
    if engine.dialect.name == "postgresql":
        return _postgresql_upgrade(engine)
    raise RuntimeError("Unsupported database for P3 M5 compatibility.")


__all__ = ["ensure_manual_revision_review_compatibility"]
