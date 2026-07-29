"""Focused P3-M2.1 schema tests for reuse projects and governed sources."""

from __future__ import annotations

import inspect
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db_models as p1_p2_models  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_source_eligibility_schemas import (  # noqa: E402
    P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
    P3SourceType,
)
from scripts.test_environment import (  # noqa: E402
    build_offline_subprocess_environment,
    require_test_database_url,
)


P3_M21_TABLES = {"reuse_projects", "reuse_source_items"}
FORBIDDEN_UNIMPLEMENTED_P3_TABLES = {
    "export_jobs",
    "export_artifacts",
}
FROZEN_EXPORT_TABLES = {"export_jobs", "export_artifacts"}
TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()


def _sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def sqlite_session():
    engine = _sqlite_engine()
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _project(
    *,
    project_id: str = "reuse_project_1",
    status: ReuseProjectStatus | str = ReuseProjectStatus.DRAFT,
    idempotency_key: str = "reuse-project-key-1",
    name: str = "客服培训资料复用",
) -> ReuseProject:
    return ReuseProject(
        id=project_id,
        name=name,
        description="P3-M2.1 schema test",
        status=status,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=idempotency_key,
        archived_at=(
            datetime.now(UTC)
            if status in (ReuseProjectStatus.ARCHIVED, "archived")
            else None
        ),
    )


def _source(
    *,
    source_item_id: str = "reuse_source_1",
    project_id: str = "reuse_project_1",
    source_type: P3SourceType | str = P3SourceType.P1_KNOWLEDGE,
    source_id: str = "candidate_1",
    source_version: int | None = None,
    source_fingerprint: str = "a" * 64,
    policy_version: str = P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
) -> ReuseSourceItem:
    return ReuseSourceItem(
        id=source_item_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        source_fingerprint=source_fingerprint,
        eligibility_policy_version=policy_version,
        source_trace={
            "source_id": source_id,
            "content_hash": source_fingerprint,
        },
        selected_by_role="cleaner",
        request_id=f"request_{source_item_id}",
    )


def test_empty_database_creates_only_the_two_requested_p3_tables() -> None:
    engine = _sqlite_engine()
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[ReuseProject.__table__, ReuseSourceItem.__table__],
        )
        assert set(sa_inspect(engine).get_table_names()) == P3_M21_TABLES
        assert FORBIDDEN_UNIMPLEMENTED_P3_TABLES.isdisjoint(
            sa_inspect(engine).get_table_names()
        )
    finally:
        Base.metadata.drop_all(
            bind=engine,
            tables=[ReuseSourceItem.__table__, ReuseProject.__table__],
        )
        engine.dispose()


def test_additive_upgrade_and_repeated_create_all_preserve_p1_p2_data() -> None:
    engine = _sqlite_engine()
    legacy_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in P3_M21_TABLES
    ]
    try:
        Base.metadata.create_all(bind=engine, tables=legacy_tables)
        with Session(engine) as session:
            session.add(
                p1_p2_models.KnowledgeCandidate(
                    id="p3m21_existing_candidate",
                    source_type="sanitized_batch",
                    source_id="p3m21_existing_batch",
                    question="Existing P1 question",
                    answer="Existing P1 answer",
                    status="approved",
                )
            )
            session.add(
                p1_p2_models.Asset(
                    id="p3m21_existing_asset",
                    asset_type="image",
                    file_name="existing.png",
                    mime_type="image/png",
                    size=1,
                    storage_uri="test://existing.png",
                    hash="b" * 64,
                    status="uploaded",
                )
            )
            session.commit()

        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        tables = set(sa_inspect(engine).get_table_names())
        assert P3_M21_TABLES <= tables
        registered_export_tables = FROZEN_EXPORT_TABLES & tables
        assert {"knowledge_candidates", "assets"} <= tables
        with Session(engine) as session:
            for table_name in registered_export_tables:
                assert session.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar_one() == 0
            assert session.get(
                p1_p2_models.KnowledgeCandidate,
                "p3m21_existing_candidate",
            ).answer == "Existing P1 answer"
            assert session.get(
                p1_p2_models.Asset,
                "p3m21_existing_asset",
            ).hash == "b" * 64
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_application_init_registers_current_p3_tables_idempotently(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "p3-m21-init-test.db"
    environment = build_offline_subprocess_environment(ROOT_DIR, database_path)
    code = (
        "from sqlalchemy import inspect; "
        "from app.database import engine, init_database_tables; "
        "init_database_tables(); init_database_tables(); "
        "tables=inspect(engine).get_table_names(); "
        "print(','.join(sorted(name for name in tables "
        "if name.startswith('reuse_') or name.startswith('export_'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "export_artifacts,export_jobs,"
        "reuse_asset_version_sources,reuse_asset_versions,"
        "reuse_projects,reuse_reviews,reuse_source_items"
    )


@pytest.mark.parametrize(
    "status",
    [
        ReuseProjectStatus.DRAFT,
        ReuseProjectStatus.ACTIVE,
        ReuseProjectStatus.ARCHIVED,
    ],
)
def test_valid_project_states_are_persisted(
    sqlite_session: Session,
    status: ReuseProjectStatus,
) -> None:
    project = _project(status=status)
    sqlite_session.add(project)
    sqlite_session.commit()
    persisted = sqlite_session.get(ReuseProject, project.id)
    assert persisted is not None
    assert persisted.status == status
    if status is ReuseProjectStatus.ARCHIVED:
        assert persisted.archived_at is not None


def test_invalid_project_state_fails_safely(sqlite_session: Session) -> None:
    sqlite_session.add(_project(status="deleted"))
    with pytest.raises((StatementError, IntegrityError)):
        sqlite_session.commit()


def test_blank_project_name_fails_safely(sqlite_session: Session) -> None:
    sqlite_session.add(_project(name="   "))
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


def test_duplicate_project_idempotency_key_fails_safely(
    sqlite_session: Session,
) -> None:
    sqlite_session.add_all(
        [
            _project(project_id="reuse_project_1"),
            _project(
                project_id="reuse_project_2",
                idempotency_key="reuse-project-key-1",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


def test_archived_project_is_retained(sqlite_session: Session) -> None:
    project = _project(status=ReuseProjectStatus.ARCHIVED)
    sqlite_session.add(project)
    sqlite_session.commit()
    assert sqlite_session.get(ReuseProject, project.id) is not None


def test_p1_source_can_be_saved(sqlite_session: Session) -> None:
    sqlite_session.add(_project())
    sqlite_session.add(_source())
    sqlite_session.commit()
    saved = sqlite_session.get(ReuseSourceItem, "reuse_source_1")
    assert saved is not None
    assert saved.source_type is P3SourceType.P1_KNOWLEDGE
    assert saved.source_version is None
    assert saved.source_version_key == 0


def test_p2_source_can_store_complete_review_snapshot_lineage(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    source = _source(
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id="knowledge_asset_1",
        source_version=3,
    )
    source.approved_review_id = "review_1"
    source.snapshot_id = "snapshot_1"
    source.knowledge_asset_id = "knowledge_asset_1"
    source.lineage_manifest_hash = "c" * 64
    source.source_trace = {
        "review_id": "review_1",
        "snapshot_id": "snapshot_1",
        "knowledge_asset_id": "knowledge_asset_1",
        "knowledge_asset_version": 3,
    }
    sqlite_session.add(source)
    sqlite_session.commit()
    saved = sqlite_session.get(ReuseSourceItem, source.id)
    assert saved.approved_review_id == "review_1"
    assert saved.snapshot_id == "snapshot_1"
    assert saved.knowledge_asset_id == "knowledge_asset_1"
    assert saved.lineage_manifest_hash == "c" * 64


def test_approved_bad_case_correction_source_can_be_saved(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.add(
        _source(
            source_type=P3SourceType.APPROVED_BAD_CASE_CORRECTION,
            source_id="candidate_bad_case_correction_1",
        )
    )
    sqlite_session.commit()
    saved = sqlite_session.get(ReuseSourceItem, "reuse_source_1")
    assert saved.source_type is P3SourceType.APPROVED_BAD_CASE_CORRECTION


@pytest.mark.parametrize("source_type", ["RAW_BAD_CASE", "P3_ASSET"])
def test_raw_bad_case_and_invalid_source_types_fail_safely(
    sqlite_session: Session,
    source_type: str,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.add(_source(source_type=source_type))
    with pytest.raises((StatementError, IntegrityError)):
        sqlite_session.commit()


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("source_fingerprint", " "),
        ("eligibility_policy_version", " "),
    ],
)
def test_required_source_evidence_cannot_be_blank(
    sqlite_session: Session,
    field_name: str,
    field_value: str,
) -> None:
    sqlite_session.add(_project())
    source = _source()
    setattr(source, field_name, field_value)
    sqlite_session.add(source)
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


def test_missing_project_foreign_key_fails_safely(sqlite_session: Session) -> None:
    sqlite_session.add(_source(project_id="missing_project"))
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


def test_project_delete_is_restricted_and_does_not_delete_source(
    sqlite_session: Session,
) -> None:
    project = _project()
    source = _source()
    sqlite_session.add_all([project, source])
    sqlite_session.commit()
    sqlite_session.delete(project)
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()
    assert sqlite_session.get(ReuseProject, project.id) is not None
    assert sqlite_session.get(ReuseSourceItem, source.id) is not None


def test_same_project_and_unversioned_source_cannot_be_bound_twice(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.add_all(
        [
            _source(source_item_id="reuse_source_1"),
            _source(source_item_id="reuse_source_2"),
        ]
    )
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


def test_different_projects_can_reference_the_same_source(
    sqlite_session: Session,
) -> None:
    sqlite_session.add_all(
        [
            _project(project_id="reuse_project_1"),
            _project(
                project_id="reuse_project_2",
                idempotency_key="reuse-project-key-2",
            ),
        ]
    )
    sqlite_session.add_all(
        [
            _source(source_item_id="reuse_source_1", project_id="reuse_project_1"),
            _source(source_item_id="reuse_source_2", project_id="reuse_project_2"),
        ]
    )
    sqlite_session.commit()
    assert sqlite_session.query(ReuseSourceItem).count() == 2


def test_same_source_different_versions_can_be_bound(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    sqlite_session.add_all(
        [
            _source(source_item_id="reuse_source_v1", source_version=1),
            _source(source_item_id="reuse_source_v2", source_version=2),
        ]
    )
    sqlite_session.commit()
    versions = {
        item.source_version
        for item in sqlite_session.query(ReuseSourceItem).all()
    }
    assert versions == {1, 2}


def test_removed_at_is_logical_and_source_stale_defaults_false(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(_project())
    source = _source()
    sqlite_session.add(source)
    sqlite_session.commit()
    assert source.source_stale is False
    source.removed_at = datetime.now(UTC)
    sqlite_session.commit()
    assert sqlite_session.get(ReuseSourceItem, source.id) is not None
    assert source.removed_at is not None


def test_source_trace_json_round_trips(sqlite_session: Session) -> None:
    sqlite_session.add(_project())
    source = _source()
    source.source_trace = {
        "candidate_id": "candidate_1",
        "review": {"id": "review_1", "action": "approved"},
        "source_refs": ["chunk_1", "chunk_2"],
    }
    sqlite_session.add(source)
    sqlite_session.commit()
    sqlite_session.expire_all()
    assert sqlite_session.get(ReuseSourceItem, source.id).source_trace == {
        "candidate_id": "candidate_1",
        "review": {"id": "review_1", "action": "approved"},
        "source_refs": ["chunk_1", "chunk_2"],
    }


def test_source_type_is_the_m1_enum_without_drift() -> None:
    assert {member.value for member in P3SourceType} == {
        "P1_KNOWLEDGE",
        "P2_KNOWLEDGE_ASSET",
        "APPROVED_BAD_CASE_CORRECTION",
    }
    assert set(ReuseSourceItem.__table__.c.source_type.type.enums) == {
        member.value for member in P3SourceType
    }


def test_models_have_no_sensitive_content_or_vector_columns() -> None:
    columns = {
        column.name.lower()
        for table in (ReuseProject.__table__, ReuseSourceItem.__table__)
        for column in table.columns
    }
    assert columns.isdisjoint(
        {
            "token",
            "token_hash",
            "api_key",
            "secret",
            "password",
            "embedding",
            "vector",
            "raw_content",
        }
    )


def test_models_do_not_call_provider_embedding_or_network(
    sqlite_session: Session,
) -> None:
    import app.p3_reuse_models as model_module

    source_code = inspect.getsource(model_module).lower()
    for forbidden_import in (
        "openai",
        "requests",
        "httpx",
        "app.embedding",
        "app.extraction_providers",
    ):
        assert forbidden_import not in source_code
    with patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network call is forbidden"),
    ):
        sqlite_session.add(_project())
        sqlite_session.add(_source())
        sqlite_session.commit()


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_foreign_key_and_normalized_unique_constraint() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    project_prefix = "p3m21_pg_"
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[ReuseProject.__table__, ReuseSourceItem.__table__],
        )
        with SessionLocal() as session:
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{project_prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{project_prefix}%")
            ).delete(synchronize_session=False)
            session.commit()

            project = _project(
                project_id=f"{project_prefix}project",
                idempotency_key=f"{project_prefix}key",
            )
            session.add(project)
            session.commit()

            session.add(
                _source(
                    source_item_id=f"{project_prefix}source_1",
                    project_id=project.id,
                )
            )
            session.commit()

            session.add(
                _source(
                    source_item_id=f"{project_prefix}source_2",
                    project_id=project.id,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(
                _source(
                    source_item_id=f"{project_prefix}orphan",
                    project_id=f"{project_prefix}missing",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        foreign_keys = sa_inspect(engine).get_foreign_keys("reuse_source_items")
        assert foreign_keys[0]["referred_table"] == "reuse_projects"
        assert foreign_keys[0]["options"].get("ondelete") == "RESTRICT"
    finally:
        with SessionLocal() as session:
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{project_prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{project_prefix}%")
            ).delete(synchronize_session=False)
            session.commit()
        engine.dispose()
