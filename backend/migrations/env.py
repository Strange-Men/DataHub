"""Alembic environment backed by the immutable baseline snapshot."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url

from migrations.baseline_schema import build_baseline_metadata


config = context.config
if config.config_file_name is not None:
    # Migration commands can also be invoked through the in-process safety API.
    # Keep unrelated application loggers alive instead of mutating global state.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=build_baseline_metadata(connection.dialect.name),
        compare_type=True,
        compare_server_default=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    dialect_name = make_url(url).get_backend_name()
    context.configure(
        url=url,
        target_metadata=build_baseline_metadata(dialect_name),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=dialect_name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        _configure(provided_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            _configure(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
