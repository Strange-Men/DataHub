"""Forward-only compatibility for the P3 draft generation-mode constraint."""

from __future__ import annotations

import re

from sqlalchemy import Engine, inspect, text


_TABLE = "reuse_asset_versions"
_CONSTRAINT = "reuse_generation_mode"
_OLD_CHECK = "generation_mode IN ('deterministic_template')"
_NEW_CHECK = (
    "generation_mode IN ('deterministic_template', 'llm_draft')"
)
_SQLITE_SHADOW = "reuse_asset_versions__p3_m4_new"


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


def _sqlite_snapshot(connection) -> list[tuple[object, ...]]:
    return list(
        connection.execute(
            text(
                "SELECT id, generation_mode, content_hash, "
                "source_manifest_hash FROM reuse_asset_versions ORDER BY id"
            )
        ).tuples()
    )


def _sqlite_upgrade(engine: Engine) -> bool:
    with engine.connect() as connection:
        table_sql = _sqlite_table_sql(connection, _TABLE)
        if table_sql is None or "llm_draft" in table_sql:
            return False
        if _OLD_CHECK not in table_sql:
            raise RuntimeError(
                "Unsupported reuse_asset_versions generation-mode constraint."
            )
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
        before = _sqlite_snapshot(connection)
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.commit()
        try:
            with connection.begin():
                connection.exec_driver_sql(
                    f"DROP TABLE IF EXISTS {_SQLITE_SHADOW}"
                )
                shadow_sql = re.sub(
                    rf"^CREATE TABLE\s+[\"`]?{_TABLE}[\"`]?",
                    f"CREATE TABLE {_SQLITE_SHADOW}",
                    table_sql,
                    count=1,
                    flags=re.IGNORECASE,
                ).replace(_OLD_CHECK, _NEW_CHECK, 1)
                if shadow_sql == table_sql:
                    raise RuntimeError(
                        "Could not build the generation-mode compatibility table."
                    )
                connection.exec_driver_sql(shadow_sql)
                connection.exec_driver_sql(
                    f"INSERT INTO {_SQLITE_SHADOW} "
                    f"SELECT * FROM {_TABLE}"
                )
                connection.exec_driver_sql(f"DROP TABLE {_TABLE}")
                connection.exec_driver_sql(
                    f"ALTER TABLE {_SQLITE_SHADOW} RENAME TO {_TABLE}"
                )
                for index_sql in indexes:
                    connection.exec_driver_sql(index_sql)
                after = _sqlite_snapshot(connection)
                if after != before:
                    raise RuntimeError(
                        "Generation-mode compatibility changed existing records."
                    )
                violations = list(
                    connection.exec_driver_sql("PRAGMA foreign_key_check")
                )
                if violations:
                    raise RuntimeError(
                        "Generation-mode compatibility broke foreign keys."
                    )
        finally:
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    return True


def _postgresql_upgrade(engine: Engine) -> bool:
    checks = {
        item["name"]: str(item["sqltext"])
        for item in inspect(engine).get_check_constraints(_TABLE)
    }
    current = checks.get(_CONSTRAINT, "")
    if "llm_draft" in current:
        return False
    if "deterministic_template" not in current:
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
        connection.exec_driver_sql(
            f'ALTER TABLE {_TABLE} DROP CONSTRAINT "{_CONSTRAINT}"'
        )
        connection.exec_driver_sql(
            f'ALTER TABLE {_TABLE} ADD CONSTRAINT "{_CONSTRAINT}" '
            f"CHECK ({_NEW_CHECK})"
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
                "Generation-mode compatibility changed existing records."
            )
    return True


def ensure_llm_draft_generation_mode_compatibility(engine: Engine) -> bool:
    """Allow ``llm_draft`` without deleting or rewriting governed data.

    Returns ``True`` only when an existing M3 constraint was upgraded.
    New databases already contain both values and are a no-op.
    """

    if not _table_exists(engine):
        return False
    if engine.dialect.name == "sqlite":
        return _sqlite_upgrade(engine)
    if engine.dialect.name == "postgresql":
        return _postgresql_upgrade(engine)
    raise RuntimeError("Unsupported database for P3 generation-mode compatibility.")


__all__ = ["ensure_llm_draft_generation_mode_compatibility"]
