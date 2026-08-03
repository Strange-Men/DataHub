"""Focused SQLite gates for the immutable Alembic baseline."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

from alembic import command
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (ROOT, BACKEND):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from app import migration_status  # noqa: E402
from app.database import Base  # noqa: E402
import app.db_models  # noqa: F401,E402
import app.p3_export_models  # noqa: F401,E402
import app.p3_reuse_models  # noqa: F401,E402
from app.migration_adoption import (  # noqa: E402
    MigrationAdoptionError,
    adopt_or_upgrade,
    make_alembic_config,
    validate_baseline_schema,
)
from app.migration_status import check_migration_status  # noqa: E402
from app.migration_schema_validation import _check_signature  # noqa: E402
from migrations.baseline_schema import (  # noqa: E402
    BASELINE_REVISION,
    BASELINE_SCHEMA_SHA256,
    BASELINE_TABLE_NAMES,
    P3_TABLE_NAMES,
    build_baseline_metadata,
)
from scripts.manage_migrations import main as migration_cli_main  # noqa: E402


EXPECTED_P3_TABLES = {
    "export_artifacts",
    "export_jobs",
    "reuse_asset_version_sources",
    "reuse_asset_versions",
    "reuse_projects",
    "reuse_reviews",
    "reuse_source_items",
}


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_current_schema(url: str) -> None:
    assert set(Base.metadata.tables) == set(BASELINE_TABLE_NAMES)
    engine = sa.create_engine(url)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()


def _insert_sample_business_data(url: str) -> None:
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            table = sa.Table("raw_batches", sa.MetaData(), autoload_with=connection)
            connection.execute(
                table.insert().values(
                    id="migration-batch-1",
                    source_name="immutable sample",
                    source_type="chat_logs",
                    status="raw_imported",
                    message_count=1,
                    metadata_json={"purpose": "migration-safety"},
                    created_at=datetime(2026, 8, 3, 12, 0, 0),
                    updated_at=datetime(2026, 8, 3, 12, 0, 0),
                )
            )
    finally:
        engine.dispose()


def _create_schema_with_mutated_check(
    url: str,
    *,
    table_name: str,
    constraint_name: str,
    replacement_sql: str,
) -> None:
    metadata = build_baseline_metadata("sqlite")
    constraint = next(
        item
        for item in metadata.tables[table_name].constraints
        if isinstance(item, sa.CheckConstraint) and item.name == constraint_name
    )
    constraint.sqltext = sa.text(replacement_sql)
    engine = sa.create_engine(url)
    try:
        metadata.create_all(bind=engine)
    finally:
        engine.dispose()


def _business_data_fingerprint(url: str) -> tuple[dict[str, int], str]:
    """Hash every business row while deliberately excluding alembic_version."""

    engine = sa.create_engine(url)
    try:
        payload: dict[str, list[dict[str, object]]] = {}
        counts: dict[str, int] = {}
        with engine.connect() as connection:
            metadata = sa.MetaData()
            for table_name in sorted(BASELINE_TABLE_NAMES):
                table = sa.Table(table_name, metadata, autoload_with=connection)
                statement = sa.select(table)
                primary_key = list(table.primary_key.columns)
                if primary_key:
                    statement = statement.order_by(*primary_key)
                rows = [dict(row) for row in connection.execute(statement).mappings()]
                payload[table_name] = rows
                counts[table_name] = len(rows)
        serialized = json.dumps(
            payload,
            default=str,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return counts, hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    finally:
        engine.dispose()


def test_frozen_snapshot_is_static_and_has_exact_table_ownership() -> None:
    source_path = BACKEND / "migrations" / "baseline_schema.py"
    source = source_path.read_text(encoding="utf-8")
    hash_input = re.sub(r"^BASELINE_SCHEMA_SHA256.*\n", "", source, flags=re.MULTILINE)

    assert hashlib.sha256(hash_input.encode("utf-8")).hexdigest() == BASELINE_SCHEMA_SHA256
    assert "app.db_models" not in source
    assert "app.p3_" not in source
    assert BASELINE_REVISION == "20260803_0001"
    assert len(BASELINE_TABLE_NAMES) == 27
    assert set(P3_TABLE_NAMES) == EXPECTED_P3_TABLES
    assert set(build_baseline_metadata("sqlite").tables) == set(BASELINE_TABLE_NAMES)


@pytest.mark.parametrize(
    ("baseline_sql", "postgres_deparse"),
    (
        (
            "length(trim(review_policy_version)) > 0",
            "length(TRIM(BOTH FROM review_policy_version)) > (0)::bigint",
        ),
        (
            "parent_asset_version_id IS NULL OR parent_asset_version_id != id",
            "((parent_asset_version_id IS NULL) OR "
            "(parent_asset_version_id <> id))",
        ),
        (
            "status IN ('draft', 'active', 'archived')",
            "((status)::text = ANY ((ARRAY['draft'::character varying, "
            "'active'::character varying, 'archived'::character varying])::text[]))",
        ),
    ),
)
def test_check_canonicalization_accepts_known_postgres_deparse_equivalents(
    baseline_sql: str,
    postgres_deparse: str,
) -> None:
    assert _check_signature(
        baseline_sql,
        table_name="reuse_asset_versions",
    ) == _check_signature(
        postgres_deparse,
        table_name="reuse_asset_versions",
    )


@pytest.mark.parametrize(
    ("constraint_name", "replacement_sql"),
    (
        (
            "ck_reuse_reviews_comments_for_nonapproval",
            "decision = 'approved' AND length(trim(comments)) > 0",
        ),
        (
            "reuse_review_decision",
            "decision NOT IN ('approved', 'needs_revision', 'rejected')",
        ),
    ),
)
def test_check_logic_mutations_are_rejected_before_stamp(
    tmp_path: Path,
    constraint_name: str,
    replacement_sql: str,
) -> None:
    url = _sqlite_url(tmp_path / f"{constraint_name}-migration-test.db")
    _create_schema_with_mutated_check(
        url,
        table_name="reuse_reviews",
        constraint_name=constraint_name,
        replacement_sql=replacement_sql,
    )

    with pytest.raises(MigrationAdoptionError, match=r"CHECK:reuse_reviews"):
        adopt_or_upgrade(url)

    engine = sa.create_engine(url)
    try:
        assert "alembic_version" not in set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_empty_sqlite_upgrade_creates_exact_baseline(tmp_path: Path) -> None:
    database_path = tmp_path / "empty-migration-test.db"
    url = _sqlite_url(database_path)

    result = adopt_or_upgrade(url)

    engine = sa.create_engine(url)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert result.action == "upgraded"
    assert result.revision == BASELINE_REVISION
    assert tables == set(BASELINE_TABLE_NAMES) | {"alembic_version"}
    assert (tables & set(P3_TABLE_NAMES)) == EXPECTED_P3_TABLES
    assert len(tables - {"alembic_version"}) == 27
    assert check_migration_status(url).ready is True


def test_in_process_upgrade_does_not_disable_application_loggers(
    tmp_path: Path,
) -> None:
    logger = logging.getLogger("app.auth")
    logger.disabled = False

    adopt_or_upgrade(_sqlite_url(tmp_path / "logger-migration-test.db"))

    assert logger.disabled is False


def test_equivalent_existing_sqlite_is_safely_stamped_without_data_changes(
    tmp_path: Path,
) -> None:
    url = _sqlite_url(tmp_path / "existing-migration-test.db")
    _create_current_schema(url)
    _insert_sample_business_data(url)
    before_counts, before_hash = _business_data_fingerprint(url)

    with sa.create_engine(url).connect() as connection:
        validation = validate_baseline_schema(connection)
    assert validation.matches is True
    assert validation.business_table_count == 27
    assert check_migration_status(url, deep_validate=True).schema_matches_baseline is True
    assert check_migration_status(url).ready is False

    result = adopt_or_upgrade(url)
    after_counts, after_hash = _business_data_fingerprint(url)

    assert result.action == "adopted"
    assert before_counts == after_counts
    assert before_hash == after_hash
    assert after_counts["raw_batches"] == 1
    assert sum(after_counts[name] for name in EXPECTED_P3_TABLES) == 0
    assert check_migration_status(url).ready is True


def test_schema_mismatch_refuses_stamp_and_preserves_all_business_data(
    tmp_path: Path,
) -> None:
    url = _sqlite_url(tmp_path / "mismatch-migration-test.db")
    _create_current_schema(url)
    _insert_sample_business_data(url)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP INDEX ix_raw_messages_batch_id"))
    finally:
        engine.dispose()
    before_counts, before_hash = _business_data_fingerprint(url)

    with pytest.raises(MigrationAdoptionError, match=r"INDEX:raw_messages"):
        adopt_or_upgrade(url)

    after_counts, after_hash = _business_data_fingerprint(url)
    engine = sa.create_engine(url)
    try:
        assert "alembic_version" not in set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert before_counts == after_counts
    assert before_hash == after_hash
    assert check_migration_status(url, deep_validate=True).ready is False


def test_upgrade_is_idempotent_and_downgrade_is_non_destructive(tmp_path: Path) -> None:
    url = _sqlite_url(tmp_path / "idempotent-migration-test.db")
    first = adopt_or_upgrade(url)
    _insert_sample_business_data(url)
    before_counts, before_hash = _business_data_fingerprint(url)

    second = adopt_or_upgrade(url)
    after_counts, after_hash = _business_data_fingerprint(url)

    assert first.action == second.action == "upgraded"
    assert first.revision == second.revision == BASELINE_REVISION
    assert before_counts == after_counts
    assert before_hash == after_hash

    with pytest.raises(RuntimeError, match="intentionally disabled"):
        command.downgrade(make_alembic_config(url), "base")
    assert _business_data_fingerprint(url) == (after_counts, after_hash)
    assert check_migration_status(url).ready is True


def test_status_hot_path_skips_deep_schema_introspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _sqlite_url(tmp_path / "hot-path-migration-test.db")
    adopt_or_upgrade(url)

    def fail_if_called(_connection: sa.Connection) -> None:
        raise AssertionError("readiness hot path must not run full schema comparison")

    monkeypatch.setattr(migration_status, "validate_baseline_schema", fail_if_called)
    assert migration_status.check_migration_status(url).ready is True


def test_status_does_not_create_a_missing_sqlite_database(tmp_path: Path) -> None:
    database_path = tmp_path / "missing-migration-test.db"

    status = check_migration_status(_sqlite_url(database_path))

    assert status.ready is False
    assert status.reason_codes == ("MIGRATION_REQUIRED", "SCHEMA_MISMATCH")
    assert database_path.exists() is False


@pytest.mark.parametrize(
    ("command_name", "expected_exit"),
    (("status", 1), ("upgrade", 3)),
)
def test_cli_never_echoes_secret_database_urls(
    command_name: str,
    expected_exit: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "migration-password-must-not-leak"
    database_url = (
        "postgresql+missing_migration_driver://migration-user:"
        f"{secret}@database.invalid/datahub_test"
    )

    exit_code = migration_cli_main(
        [command_name, "--database-url", database_url]
    )
    captured = capsys.readouterr()
    combined = f"{captured.out}\n{captured.err}"

    assert exit_code == expected_exit
    assert secret not in combined
    assert database_url not in combined
    assert "database.invalid" not in combined
    assert str(ROOT) not in combined
    assert "Traceback" not in combined
