"""Isolated PostgreSQL/pgvector acceptance for the Alembic baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (ROOT, BACKEND):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from app.migration_adoption import adopt_or_upgrade  # noqa: E402
from app.migration_status import check_migration_status  # noqa: E402
from migrations.baseline_schema import (  # noqa: E402
    BASELINE_REVISION,
    BASELINE_TABLE_NAMES,
    P3_TABLE_NAMES,
)
from scripts.test_environment import require_test_database_url  # noqa: E402


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL migration tests",
    ),
]


@dataclass(frozen=True)
class IsolatedPostgresDatabase:
    name: str
    url: str = field(repr=False)


@pytest.fixture()
def isolated_postgres_database() -> IsolatedPostgresDatabase:
    base_url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    admin_engine = sa.create_engine(
        base_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    database_name = f"migration_test_{uuid4().hex[:20]}"
    assert database_name.startswith("migration_test_")
    quoted_database = admin_engine.dialect.identifier_preparer.quote(database_name)
    created = False
    try:
        with admin_engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT current_database() LIKE '%test%'")
            ).scalar_one()
            connection.execute(sa.text(f"CREATE DATABASE {quoted_database}"))
            created = True
        isolated = make_url(base_url).set(database=database_name)
        yield IsolatedPostgresDatabase(
            name=database_name,
            url=isolated.render_as_string(hide_password=False),
        )
    finally:
        try:
            if created:
                with admin_engine.connect() as connection:
                    connection.execute(
                        sa.text(
                            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                        ),
                        {"database_name": database_name},
                    )
                    connection.execute(sa.text(f"DROP DATABASE {quoted_database}"))
        finally:
            admin_engine.dispose()


def test_empty_postgres_upgrade_pgvector_and_idempotency(
    isolated_postgres_database: IsolatedPostgresDatabase,
) -> None:
    isolated_postgres_url = isolated_postgres_database.url
    first = adopt_or_upgrade(isolated_postgres_url)
    second = adopt_or_upgrade(isolated_postgres_url)
    status = check_migration_status(isolated_postgres_url, deep_validate=True)

    engine = sa.create_engine(isolated_postgres_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT current_database()")
            ).scalar_one() == isolated_postgres_database.name
            assert (
                connection.execute(sa.text("SELECT current_schema()")).scalar_one()
                == "public"
            )
            tables = set(sa.inspect(connection).get_table_names())
            vector_installed = connection.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
            ).scalar_one()
            vector_types = connection.execute(
                sa.text(
                    "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() "
                    "AND (c.relname, a.attname) IN "
                    "(('rag_embeddings', 'embedding'), "
                    "('p2_knowledge_embeddings', 'embedding'))"
                )
            ).all()
    finally:
        engine.dispose()

    assert first.action == second.action == "upgraded"
    assert first.revision == second.revision == BASELINE_REVISION
    assert tables == set(BASELINE_TABLE_NAMES) | {"alembic_version"}
    assert len(tables - {"alembic_version"}) == 27
    assert tables & set(P3_TABLE_NAMES) == set(P3_TABLE_NAMES)
    assert len(P3_TABLE_NAMES) == 7
    assert vector_installed is True
    assert set(vector_types) == {
        ("p2_knowledge_embeddings", "embedding", "vector"),
        ("rag_embeddings", "embedding", "vector(1536)"),
    }
    assert status.ready is True
    assert status.schema_matches_baseline is True
