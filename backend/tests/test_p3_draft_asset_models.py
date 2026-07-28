"""Focused P3-M3.1 draft-asset schema and constraint tests."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_source_eligibility_schemas import P3SourceType  # noqa: E402
from scripts.test_environment import require_test_database_url  # noqa: E402


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
P3_TABLES = {
    "reuse_projects",
    "reuse_source_items",
    "reuse_asset_versions",
    "reuse_asset_version_sources",
    "reuse_reviews",
}
FORBIDDEN_TABLES = {"export_jobs", "export_artifacts"}


def _engine():
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
def db():
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as session:
        yield session
        session.rollback()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _project(
    *,
    project_id: str = "m31_project",
    idempotency_key: str = "m31_project_key",
) -> ReuseProject:
    return ReuseProject(
        id=project_id,
        name="M3.1 draft schema",
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=idempotency_key,
    )


def _source(
    *,
    source_item_id: str = "m31_source",
    project_id: str = "m31_project",
) -> ReuseSourceItem:
    return ReuseSourceItem(
        id=source_item_id,
        project_id=project_id,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id="knowledge_asset_m31",
        source_version=3,
        source_fingerprint="a" * 64,
        eligibility_policy_version="p3-source-eligibility-v1",
        approved_review_id="review_m31",
        snapshot_id="snapshot_m31",
        knowledge_asset_id="knowledge_asset_m31",
        lineage_manifest_hash="b" * 64,
        source_trace={"source_id": "knowledge_asset_m31", "version": 3},
        selected_by_role="cleaner",
        request_id=f"request_{source_item_id}",
    )


def _asset_version(
    *,
    asset_version_id: str = "m31_asset_version",
    project_id: str = "m31_project",
    asset_type: ReuseAssetType | str = ReuseAssetType.TRAINING_MATERIAL,
    version_number: int = 1,
    status: ReuseAssetVersionStatus | str = ReuseAssetVersionStatus.GENERATED,
    generation_mode: ReuseGenerationMode | str = (
        ReuseGenerationMode.DETERMINISTIC_TEMPLATE
    ),
    idempotency_key: str = "m31_asset_key",
    content_hash: str = "c" * 64,
    source_manifest_hash: str = "d" * 64,
) -> ReuseAssetVersion:
    return ReuseAssetVersion(
        id=asset_version_id,
        project_id=project_id,
        asset_type=asset_type,
        version_number=version_number,
        status=status,
        generation_mode=generation_mode,
        template_key="training-material-v1",
        template_version="1.0.0",
        content_payload={"title": "Training", "sections": []},
        content_hash=content_hash,
        source_manifest_hash=source_manifest_hash,
        idempotency_key=idempotency_key,
        created_by_role="cleaner",
        request_id=f"request_{asset_version_id}",
    )


def _binding(
    *,
    binding_id: str = "m31_binding",
    asset_version_id: str = "m31_asset_version",
    source_item_id: str = "m31_source",
) -> ReuseAssetVersionSource:
    return ReuseAssetVersionSource(
        id=binding_id,
        asset_version_id=asset_version_id,
        source_item_id=source_item_id,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id="knowledge_asset_m31",
        source_version=3,
        source_fingerprint="a" * 64,
        approved_review_id="review_m31",
        snapshot_id="snapshot_m31",
        knowledge_asset_id="knowledge_asset_m31",
        lineage_manifest_hash="b" * 64,
        source_trace_snapshot={
            "source_id": "knowledge_asset_m31",
            "source_version": 3,
            "approved_review_id": "review_m31",
        },
    )


def _seed_graph(db: Session) -> tuple[ReuseProject, ReuseSourceItem, ReuseAssetVersion]:
    project = _project()
    db.add(project)
    db.commit()
    source = _source()
    version = _asset_version()
    db.add_all([source, version])
    db.commit()
    return project, source, version


def _persist_project(db: Session) -> ReuseProject:
    project = _project()
    db.add(project)
    db.commit()
    return project


def test_create_all_adds_exactly_the_four_current_p3_tables() -> None:
    engine = _engine()
    try:
        Base.metadata.create_all(bind=engine)
        tables = {
            name
            for name in sa_inspect(engine).get_table_names()
            if name.startswith("reuse_") or name.startswith("export_")
        }
        assert tables == P3_TABLES
        assert FORBIDDEN_TABLES.isdisjoint(tables)
        Base.metadata.create_all(bind=engine)
        assert P3_TABLES <= set(sa_inspect(engine).get_table_names())
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_additive_create_all_preserves_existing_m2_project_and_source() -> None:
    engine = _engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        Base.metadata.create_all(
            bind=engine,
            tables=[ReuseProject.__table__, ReuseSourceItem.__table__],
        )
        with SessionLocal() as session:
            session.add(_project())
            session.commit()
            session.add(_source())
            session.commit()

        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as session:
            project = session.get(ReuseProject, "m31_project")
            source = session.get(ReuseSourceItem, "m31_source")
            assert project is not None
            assert project.name == "M3.1 draft schema"
            assert source is not None
            assert source.source_fingerprint == "a" * 64
        assert P3_TABLES <= set(sa_inspect(engine).get_table_names())
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.mark.parametrize("asset_type", list(ReuseAssetType))
def test_all_five_asset_types_are_persistable(
    db: Session,
    asset_type: ReuseAssetType,
) -> None:
    _persist_project(db)
    db.add(
        _asset_version(
            asset_version_id=f"version_{asset_type.value}",
            asset_type=asset_type,
            idempotency_key=f"key_{asset_type.value}",
        )
    )
    db.commit()
    assert db.get(
        ReuseAssetVersion,
        f"version_{asset_type.value}",
    ).asset_type is asset_type


@pytest.mark.parametrize("status", list(ReuseAssetVersionStatus))
def test_all_frozen_asset_version_states_are_persistable(
    db: Session,
    status: ReuseAssetVersionStatus,
) -> None:
    _persist_project(db)
    db.add(_asset_version(status=status))
    db.commit()
    assert db.get(ReuseAssetVersion, "m31_asset_version").status is status


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_type", "unsupported"),
        ("status", "draft"),
        ("generation_mode", "unsupported"),
    ],
)
def test_invalid_enums_are_rejected(
    db: Session,
    field: str,
    value: str,
) -> None:
    _persist_project(db)
    values = {field: value}
    db.add(_asset_version(**values))
    with pytest.raises(StatementError):
        db.commit()
    db.rollback()
    assert db.query(ReuseAssetVersion).count() == 0


def test_llm_draft_generation_mode_is_persistable(db: Session) -> None:
    _persist_project(db)
    db.add(_asset_version(generation_mode=ReuseGenerationMode.LLM_DRAFT))
    db.commit()
    loaded = db.get(ReuseAssetVersion, "m31_asset_version")
    assert loaded.generation_mode is ReuseGenerationMode.LLM_DRAFT


def test_project_foreign_key_is_enforced(db: Session) -> None:
    db.add(_asset_version(project_id="missing_project"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_project_type_version_unique_constraint(db: Session) -> None:
    _persist_project(db)
    db.add_all(
        [
            _asset_version(),
            _asset_version(
                asset_version_id="duplicate_version",
                idempotency_key="duplicate_version_key",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_idempotency_key_is_globally_unique(db: Session) -> None:
    _persist_project(db)
    db.add_all(
        [
            _asset_version(),
            _asset_version(
                asset_version_id="second_version",
                version_number=2,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version_number", 0),
        ("content_hash", " "),
        ("source_manifest_hash", ""),
    ],
)
def test_required_version_and_hash_constraints(
    db: Session,
    field: str,
    value: object,
) -> None:
    _persist_project(db)
    db.add(_asset_version(**{field: value}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_asset_version_payload_round_trip(db: Session) -> None:
    _persist_project(db)
    version = _asset_version()
    version.failure_code = "TEMPLATE_INPUT_INVALID"
    version.failure_message = "Safe failure detail."
    db.add(version)
    db.commit()
    loaded = db.get(ReuseAssetVersion, version.id)
    assert loaded.content_payload == {"title": "Training", "sections": []}
    assert loaded.generation_mode is ReuseGenerationMode.DETERMINISTIC_TEMPLATE
    assert loaded.failure_code == "TEMPLATE_INPUT_INVALID"


def test_version_source_snapshot_round_trip(db: Session) -> None:
    _seed_graph(db)
    binding = _binding()
    db.add(binding)
    db.commit()
    loaded = db.get(ReuseAssetVersionSource, binding.id)
    assert loaded.source_type is P3SourceType.P2_KNOWLEDGE_ASSET
    assert loaded.source_version == 3
    assert loaded.source_trace_snapshot["approved_review_id"] == "review_m31"


def test_same_source_cannot_bind_twice_to_one_asset_version(db: Session) -> None:
    _seed_graph(db)
    db.add_all([_binding(), _binding(binding_id="duplicate_binding")])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_different_asset_versions_can_bind_the_same_source_item(
    db: Session,
) -> None:
    _seed_graph(db)
    second_version = _asset_version(
        asset_version_id="m31_asset_version_2",
        version_number=2,
        idempotency_key="m31_asset_key_2",
    )
    db.add(second_version)
    db.commit()
    db.add_all(
        [
            _binding(),
            _binding(
                binding_id="m31_binding_2",
                asset_version_id=second_version.id,
            ),
        ]
    )
    db.commit()
    assert db.query(ReuseAssetVersionSource).count() == 2


@pytest.mark.parametrize(
    ("asset_version_id", "source_item_id"),
    [
        ("missing_version", "m31_source"),
        ("m31_asset_version", "missing_source"),
    ],
)
def test_binding_foreign_keys_are_enforced(
    db: Session,
    asset_version_id: str,
    source_item_id: str,
) -> None:
    _seed_graph(db)
    db.add(
        _binding(
            asset_version_id=asset_version_id,
            source_item_id=source_item_id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_bound_snapshot_survives_source_stale_and_logical_removal(
    db: Session,
) -> None:
    _project_row, source, _version = _seed_graph(db)
    binding = _binding()
    db.add(binding)
    db.commit()
    original_snapshot = dict(binding.source_trace_snapshot)
    original_fingerprint = binding.source_fingerprint

    source.source_stale = True
    source.removed_at = datetime.now(UTC)
    source.source_fingerprint = "e" * 64
    db.commit()
    db.refresh(binding)
    assert binding.source_trace_snapshot == original_snapshot
    assert binding.source_fingerprint == original_fingerprint


def test_restrict_foreign_keys_and_unique_constraints_are_declared() -> None:
    engine = _engine()
    try:
        Base.metadata.create_all(bind=engine)
        inspector = sa_inspect(engine)
        version_fks = inspector.get_foreign_keys("reuse_asset_versions")
        binding_fks = inspector.get_foreign_keys("reuse_asset_version_sources")
        assert {
            fk["referred_table"] for fk in version_fks
        } == {"reuse_projects", "reuse_asset_versions"}
        assert {
            fk["referred_table"] for fk in binding_fks
        } == {"reuse_asset_versions", "reuse_source_items"}
        assert all(
            fk["options"].get("ondelete") == "RESTRICT"
            for fk in version_fks + binding_fks
        )
        version_uniques = {
            item["name"]
            for item in inspector.get_unique_constraints("reuse_asset_versions")
        }
        binding_uniques = {
            item["name"]
            for item in inspector.get_unique_constraints(
                "reuse_asset_version_sources"
            )
        }
        assert "uq_reuse_asset_versions_project_type_version" in version_uniques
        assert "uq_reuse_asset_versions_idempotency_key" in version_uniques
        assert "uq_reuse_asset_version_sources_version_source" in binding_uniques
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_new_tables_have_no_secret_vector_or_p1_p2_foreign_keys() -> None:
    forbidden_fragments = {
        "token",
        "secret",
        "api_key",
        "embedding",
        "vector",
        "password",
    }
    for table in (
        ReuseAssetVersion.__table__,
        ReuseAssetVersionSource.__table__,
    ):
        column_names = {column.name.lower() for column in table.columns}
        assert not any(
            fragment in column_name
            for fragment in forbidden_fragments
            for column_name in column_names
        )
        referred = {
            foreign_key.column.table.name
            for foreign_key in table.foreign_keys
        }
        assert referred <= {
            "reuse_projects",
            "reuse_asset_versions",
            "reuse_source_items",
        }


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_asset_version_constraints_and_restrict_foreign_keys() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    prefix = "p3m31_pg_"
    tables = [
        ReuseProject.__table__,
        ReuseSourceItem.__table__,
        ReuseAssetVersion.__table__,
        ReuseAssetVersionSource.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    try:
        with SessionLocal() as session:
            session.query(ReuseAssetVersionSource).filter(
                ReuseAssetVersionSource.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseAssetVersion).filter(
                ReuseAssetVersion.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.commit()

            project = _project(
                project_id=f"{prefix}project",
                idempotency_key=f"{prefix}project_key",
            )
            source = _source(
                source_item_id=f"{prefix}source",
                project_id=project.id,
            )
            version = _asset_version(
                asset_version_id=f"{prefix}version",
                project_id=project.id,
                idempotency_key=f"{prefix}version_key",
            )
            binding = _binding(
                binding_id=f"{prefix}binding",
                asset_version_id=version.id,
                source_item_id=source.id,
            )
            session.add(project)
            session.commit()
            session.add_all([source, version])
            session.commit()
            session.add(binding)
            session.commit()

            second_version = _asset_version(
                asset_version_id=f"{prefix}version_2",
                project_id=project.id,
                version_number=2,
                idempotency_key=f"{prefix}version_key_2",
            )
            session.add(second_version)
            session.commit()
            session.add(
                _binding(
                    binding_id=f"{prefix}binding_2",
                    asset_version_id=second_version.id,
                    source_item_id=source.id,
                )
            )
            session.commit()

            session.add(
                _asset_version(
                    asset_version_id=f"{prefix}duplicate_version",
                    project_id=project.id,
                    idempotency_key=f"{prefix}duplicate_key",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(
                _binding(
                    binding_id=f"{prefix}duplicate_binding",
                    asset_version_id=version.id,
                    source_item_id=source.id,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.delete(version)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.get(ReuseAssetVersion, version.id) is not None

        inspector = sa_inspect(engine)
        assert all(
            fk["options"].get("ondelete") == "RESTRICT"
            for fk in inspector.get_foreign_keys(
                "reuse_asset_version_sources"
            )
        )
    finally:
        with SessionLocal() as session:
            session.query(ReuseAssetVersionSource).filter(
                ReuseAssetVersionSource.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseAssetVersion).filter(
                ReuseAssetVersion.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.commit()
        engine.dispose()
