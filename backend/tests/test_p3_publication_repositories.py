"""Focused P3-M6.1 publication persistence and repository tests."""

from __future__ import annotations

import inspect as pyinspect
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import p3_publication_repositories as repositories  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_publication_repositories import (  # noqa: E402
    archive_asset,
    get_asset_publication_state,
    get_current_published_asset,
    list_current_published_assets,
    publish_approved_asset,
)
from app.p3_publication_schema_compatibility import (  # noqa: E402
    ensure_asset_publication_compatibility,
)
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
    ReuseReview,
    ReuseReviewDecision,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import (  # noqa: E402
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryValidationError,
)
from app.p3_source_eligibility_schemas import P3SourceType  # noqa: E402
from scripts.test_environment import require_test_database_url  # noqa: E402


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
PUBLICATION_COLUMNS = {
    "published_by_role",
    "publish_request_id",
    "publish_idempotency_key",
    "superseded_by_asset_version_id",
    "archived_by_role",
    "archive_request_id",
    "archive_idempotency_key",
}
FROZEN_EXPORT_TABLES = {"export_jobs", "export_artifacts"}


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
def db():
    engine = _sqlite_engine()
    Base.metadata.create_all(bind=engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _project(
    db: Session,
    project_id: str = "m61_project",
) -> ReuseProject:
    row = ReuseProject(
        id=project_id,
        name="M6.1 publication repository",
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=f"key_{project_id}",
    )
    db.add(row)
    db.commit()
    return row


def _version(
    db: Session,
    *,
    version_id: str,
    project_id: str = "m61_project",
    version_number: int = 1,
    status: ReuseAssetVersionStatus = ReuseAssetVersionStatus.APPROVED,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    mode: ReuseGenerationMode = ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
    parent_id: str | None = None,
) -> ReuseAssetVersion:
    row = ReuseAssetVersion(
        id=version_id,
        project_id=project_id,
        asset_type=asset_type,
        version_number=version_number,
        status=status,
        generation_mode=mode,
        template_key=f"p3.m61.{asset_type.value}.v1",
        template_version="v1",
        content_payload={
            "title": version_id,
            "sections": [{"heading": "Evidence", "body": "Governed"}],
        },
        content_hash=(f"{version_number:x}"[-1] or "a") * 64,
        source_manifest_hash="b" * 64,
        idempotency_key=f"generation_{version_id}",
        created_by_role="cleaner",
        request_id=f"request_{version_id}",
        approved_at=(
            datetime.now(UTC)
            if status is ReuseAssetVersionStatus.APPROVED
            else None
        ),
        parent_asset_version_id=parent_id,
    )
    db.add(row)
    db.commit()
    return row


def _review(db: Session, version: ReuseAssetVersion) -> ReuseReview:
    row = ReuseReview(
        id=f"review_{version.id}",
        asset_version_id=version.id,
        decision=ReuseReviewDecision.APPROVED,
        comments=None,
        checklist_payload={
            "structure_complete": True,
            "source_refs_valid": True,
            "no_unsupported_claims_confirmed": True,
            "safe_for_reuse": True,
        },
        review_policy_version="p3-review-v1",
        reviewed_content_hash=version.content_hash,
        reviewed_source_manifest_hash=version.source_manifest_hash,
        reviewer_role="reviewer",
        request_id=f"review_request_{version.id}",
        idempotency_key=f"review_key_{version.id}",
    )
    db.add(row)
    db.commit()
    return row


def _source_snapshot(
    db: Session,
    version: ReuseAssetVersion,
) -> ReuseAssetVersionSource:
    source = ReuseSourceItem(
        id=f"source_{version.id}",
        project_id=version.project_id,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=f"candidate_{version.id}",
        source_fingerprint="c" * 64,
        eligibility_policy_version="p3-source-eligibility-v1",
        approved_review_id=f"approved_{version.id}",
        lineage_manifest_hash="d" * 64,
        source_trace={"source_id": f"candidate_{version.id}"},
        selected_by_role="cleaner",
        request_id=f"source_request_{version.id}",
    )
    snapshot = ReuseAssetVersionSource(
        id=f"snapshot_{version.id}",
        asset_version_id=version.id,
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=None,
        source_fingerprint=source.source_fingerprint,
        approved_review_id=source.approved_review_id,
        snapshot_id=None,
        knowledge_asset_id=None,
        lineage_manifest_hash=source.lineage_manifest_hash,
        source_trace_snapshot=dict(source.source_trace),
    )
    db.add(source)
    db.flush()
    db.add(snapshot)
    db.commit()
    return snapshot


def _publish(
    db: Session,
    version: ReuseAssetVersion,
    key: str | None = None,
):
    return publish_approved_asset(
        db,
        asset_version_id=version.id,
        published_by_role="admin",
        request_id=f"publish_request_{version.id}",
        idempotency_key=key or f"publish_key_{version.id}",
    )


def test_fresh_schema_has_publication_fields_and_empty_export_tables() -> None:
    engine = _sqlite_engine()
    try:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        columns = {
            item["name"]
            for item in inspector.get_columns("reuse_asset_versions")
        }
        indexes = {
            item["name"]: item
            for item in inspector.get_indexes("reuse_asset_versions")
        }
        foreign_keys = {
            item.get("name")
            for item in inspector.get_foreign_keys("reuse_asset_versions")
        }
        assert PUBLICATION_COLUMNS <= columns
        assert indexes[
            "uq_reuse_asset_versions_current_published"
        ]["unique"]
        assert (
            "fk_reuse_asset_versions_superseded_by" in foreign_keys
        )
        registered_export_tables = FROZEN_EXPORT_TABLES & set(
            inspector.get_table_names()
        )
        with engine.connect() as connection:
            for table_name in registered_export_tables:
                assert connection.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar_one() == 0
    finally:
        engine.dispose()


def test_sqlite_legacy_upgrade_is_forward_idempotent_and_preserves_modes() -> None:
    engine = _sqlite_engine()
    try:
        ReuseProject.__table__.create(bind=engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE reuse_asset_versions (
                    id VARCHAR(200) PRIMARY KEY,
                    project_id VARCHAR(200) NOT NULL
                        REFERENCES reuse_projects(id) ON DELETE RESTRICT,
                    asset_type VARCHAR(50) NOT NULL,
                    version_number INTEGER NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    generation_mode VARCHAR(50) NOT NULL,
                    template_key VARCHAR(200) NOT NULL,
                    template_version VARCHAR(100) NOT NULL,
                    content_payload JSON NOT NULL,
                    content_hash VARCHAR(128) NOT NULL,
                    source_manifest_hash VARCHAR(128) NOT NULL,
                    idempotency_key VARCHAR(200) NOT NULL,
                    created_by_role VARCHAR(50) NOT NULL,
                    request_id VARCHAR(200) NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    approved_at DATETIME,
                    published_at DATETIME,
                    superseded_at DATETIME,
                    archived_at DATETIME,
                    failure_code VARCHAR(100),
                    failure_message TEXT,
                    parent_asset_version_id VARCHAR(200)
                        REFERENCES reuse_asset_versions(id) ON DELETE RESTRICT
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO reuse_projects "
                    "(id,name,status,created_by_role,request_id,"
                    "idempotency_key,created_at,updated_at) "
                    "VALUES ('legacy_project','Legacy','active','cleaner',"
                    "'legacy_request','legacy_key',CURRENT_TIMESTAMP,"
                    "CURRENT_TIMESTAMP)"
                )
            )
            for number, mode, parent in (
                (1, "deterministic_template", None),
                (2, "llm_draft", None),
                (3, "manual_revision", "legacy_1"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO reuse_asset_versions "
                        "(id,project_id,asset_type,version_number,status,"
                        "generation_mode,template_key,template_version,"
                        "content_payload,content_hash,source_manifest_hash,"
                        "idempotency_key,created_by_role,request_id,"
                        "created_at,updated_at,parent_asset_version_id) "
                        "VALUES (:id,'legacy_project','training_material',"
                        ":number,'approved',:mode,'legacy','v1','{}',"
                        ":content_hash,:manifest_hash,:key,'cleaner',"
                        ":request,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,:parent)"
                    ),
                    {
                        "id": f"legacy_{number}",
                        "number": number,
                        "mode": mode,
                        "content_hash": str(number) * 64,
                        "manifest_hash": "f" * 64,
                        "key": f"legacy_generation_{number}",
                        "request": f"legacy_request_{number}",
                        "parent": parent,
                    },
                )
        assert ensure_asset_publication_compatibility(engine) is True
        assert ensure_asset_publication_compatibility(engine) is False
        with engine.connect() as connection:
            rows = list(
                connection.execute(
                    text(
                        "SELECT generation_mode, content_hash, "
                        "source_manifest_hash, publish_idempotency_key, "
                        "archive_idempotency_key "
                        "FROM reuse_asset_versions ORDER BY version_number"
                    )
                ).tuples()
            )
        assert [row[0] for row in rows] == [
            "deterministic_template",
            "llm_draft",
            "manual_revision",
        ]
        assert [row[1] for row in rows] == [
            "1" * 64,
            "2" * 64,
            "3" * 64,
        ]
        assert all(row[2] == "f" * 64 for row in rows)
        assert all(row[3] is None and row[4] is None for row in rows)
    finally:
        engine.dispose()


def test_database_current_published_unique_constraint_is_enforced(
    db: Session,
) -> None:
    _project(db)
    first = _version(db, version_id="m61_unique_1")
    second = _version(db, version_id="m61_unique_2", version_number=2)
    first.status = ReuseAssetVersionStatus.PUBLISHED
    first.published_at = datetime.now(UTC)
    db.commit()
    second.status = ReuseAssetVersionStatus.PUBLISHED
    second.published_at = datetime.now(UTC)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert second.status is ReuseAssetVersionStatus.APPROVED


def test_approved_publish_sets_audit_and_current_query(db: Session) -> None:
    _project(db)
    version = _version(db, version_id="m61_publish")
    result = _publish(db, version)
    assert result.published.status is ReuseAssetVersionStatus.PUBLISHED
    assert result.published.published_at is not None
    assert result.published.published_by_role == "admin"
    assert result.published.publish_request_id == "publish_request_m61_publish"
    assert result.published.publish_idempotency_key == "publish_key_m61_publish"
    assert result.superseded is None
    assert get_current_published_asset(
        db,
        project_id="m61_project",
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
    ).id == version.id
    assert get_asset_publication_state(db, version.id).id == version.id


def test_new_publish_supersedes_old_in_one_result(db: Session) -> None:
    _project(db)
    old = _version(db, version_id="m61_old")
    _publish(db, old)
    new = _version(db, version_id="m61_new", version_number=2)
    result = _publish(db, new)
    assert result.published.id == new.id
    assert result.superseded is not None
    assert result.superseded.id == old.id
    assert old.status is ReuseAssetVersionStatus.SUPERSEDED
    assert old.superseded_at is not None
    assert old.superseded_by_asset_version_id == new.id
    assert new.status is ReuseAssetVersionStatus.PUBLISHED
    page = list_current_published_assets(db, project_id="m61_project")
    assert page.total == 1
    assert [item.id for item in page.items] == [new.id]


def test_publish_replay_is_idempotent_without_timestamp_change(
    db: Session,
) -> None:
    _project(db)
    version = _version(db, version_id="m61_replay")
    first = _publish(db, version, "m61_publish_replay")
    published_at = first.published.published_at
    replay = _publish(db, version, "m61_publish_replay")
    assert replay.replayed is True
    assert replay.published.id == version.id
    assert replay.published.published_at == published_at


def test_already_current_publish_is_noop_with_another_key(db: Session) -> None:
    _project(db)
    version = _version(db, version_id="m61_current_replay")
    first = _publish(db, version, "m61_first_publish")
    published_at = first.published.published_at
    replay = _publish(db, version, "m61_second_publish")
    assert replay.replayed is True
    assert replay.published.published_at == published_at
    assert replay.published.publish_idempotency_key == "m61_first_publish"


def test_publish_key_bound_to_another_target_conflicts(db: Session) -> None:
    _project(db)
    first = _version(db, version_id="m61_key_1")
    second = _version(db, version_id="m61_key_2", version_number=2)
    _publish(db, first, "m61_shared_publish")
    with pytest.raises(P3RepositoryConflict):
        _publish(db, second, "m61_shared_publish")


@pytest.mark.parametrize(
    "state",
    [
        ReuseAssetVersionStatus.GENERATED,
        ReuseAssetVersionStatus.PENDING_REVIEW,
        ReuseAssetVersionStatus.NEEDS_REVISION,
        ReuseAssetVersionStatus.REJECTED,
        ReuseAssetVersionStatus.FAILED,
    ],
)
def test_nonapproved_state_cannot_publish(
    db: Session,
    state: ReuseAssetVersionStatus,
) -> None:
    _project(db)
    version = _version(db, version_id=f"m61_publish_{state.value}", status=state)
    with pytest.raises(P3RepositoryConflict):
        _publish(db, version)
    assert version.status is state


@pytest.mark.parametrize(
    "state",
    [
        ReuseAssetVersionStatus.SUPERSEDED,
        ReuseAssetVersionStatus.ARCHIVED,
    ],
)
def test_superseded_and_archived_cannot_republish(
    db: Session,
    state: ReuseAssetVersionStatus,
) -> None:
    _project(db)
    version = _version(db, version_id=f"m61_republish_{state.value}", status=state)
    with pytest.raises(P3RepositoryConflict):
        _publish(db, version)


def test_publish_rollback_keeps_old_current_and_new_approved(
    db: Session,
) -> None:
    _project(db)
    old = _version(db, version_id="m61_rollback_old")
    _publish(db, old)
    new = _version(db, version_id="m61_rollback_new", version_number=2)
    error = IntegrityError("statement", {}, RuntimeError("forced"))
    with patch.object(db, "commit", side_effect=error):
        with pytest.raises(P3RepositoryConflict):
            _publish(db, new)
    db.expire_all()
    assert db.get(ReuseAssetVersion, old.id).status is (
        ReuseAssetVersionStatus.PUBLISHED
    )
    assert db.get(ReuseAssetVersion, new.id).status is (
        ReuseAssetVersionStatus.APPROVED
    )


@pytest.mark.parametrize(
    "state",
    [
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.PUBLISHED,
        ReuseAssetVersionStatus.SUPERSEDED,
    ],
)
def test_allowed_states_archive_logically(
    db: Session,
    state: ReuseAssetVersionStatus,
) -> None:
    _project(db)
    version = _version(db, version_id=f"m61_archive_{state.value}", status=state)
    archived = archive_asset(
        db,
        asset_version_id=version.id,
        archived_by_role="admin",
        request_id=f"archive_request_{state.value}",
        idempotency_key=f"archive_key_{state.value}",
    )
    assert archived.status is ReuseAssetVersionStatus.ARCHIVED
    assert archived.archived_at is not None
    assert archived.archived_by_role == "admin"
    assert db.get(ReuseAssetVersion, version.id) is not None


@pytest.mark.parametrize(
    "state",
    [
        ReuseAssetVersionStatus.GENERATED,
        ReuseAssetVersionStatus.PENDING_REVIEW,
        ReuseAssetVersionStatus.NEEDS_REVISION,
        ReuseAssetVersionStatus.REJECTED,
        ReuseAssetVersionStatus.FAILED,
    ],
)
def test_invalid_states_cannot_archive(
    db: Session,
    state: ReuseAssetVersionStatus,
) -> None:
    _project(db)
    version = _version(db, version_id=f"m61_no_archive_{state.value}", status=state)
    with pytest.raises(P3RepositoryConflict):
        archive_asset(
            db,
            asset_version_id=version.id,
            archived_by_role="admin",
            request_id="archive_invalid",
            idempotency_key=f"archive_invalid_{state.value}",
        )


def test_archive_current_does_not_restore_superseded(db: Session) -> None:
    _project(db)
    old = _version(db, version_id="m61_restore_old")
    _publish(db, old)
    current = _version(db, version_id="m61_restore_new", version_number=2)
    _publish(db, current)
    archive_asset(
        db,
        asset_version_id=current.id,
        archived_by_role="admin",
        request_id="archive_current",
        idempotency_key="archive_current_key",
    )
    with pytest.raises(P3RepositoryNotFound):
        get_current_published_asset(
            db,
            project_id="m61_project",
            asset_type=ReuseAssetType.TRAINING_MATERIAL,
        )
    assert old.status is ReuseAssetVersionStatus.SUPERSEDED


def test_archive_idempotency_and_key_conflict(db: Session) -> None:
    _project(db)
    first = _version(db, version_id="m61_archive_idem_1")
    second = _version(db, version_id="m61_archive_idem_2", version_number=2)
    initial = archive_asset(
        db,
        asset_version_id=first.id,
        archived_by_role="admin",
        request_id="archive_idem",
        idempotency_key="archive_shared",
    )
    archived_at = initial.archived_at
    replay = archive_asset(
        db,
        asset_version_id=first.id,
        archived_by_role="admin",
        request_id="archive_idem",
        idempotency_key="archive_shared",
    )
    assert replay.id == first.id
    assert replay.archived_at == archived_at
    with pytest.raises(P3RepositoryConflict):
        archive_asset(
            db,
            asset_version_id=second.id,
            archived_by_role="admin",
            request_id="archive_conflict",
            idempotency_key="archive_shared",
        )


def test_review_and_source_snapshot_are_immutable_across_publication(
    db: Session,
) -> None:
    _project(db)
    version = _version(db, version_id="m61_history")
    review = _review(db, version)
    snapshot = _source_snapshot(db, version)
    review_before = (
        review.decision,
        dict(review.checklist_payload),
        review.reviewed_content_hash,
        review.reviewed_source_manifest_hash,
    )
    snapshot_before = (
        snapshot.source_fingerprint,
        snapshot.lineage_manifest_hash,
        dict(snapshot.source_trace_snapshot),
    )
    _publish(db, version)
    archive_asset(
        db,
        asset_version_id=version.id,
        archived_by_role="admin",
        request_id="archive_history",
        idempotency_key="archive_history_key",
    )
    db.expire_all()
    persisted_review = db.get(ReuseReview, review.id)
    persisted_snapshot = db.get(ReuseAssetVersionSource, snapshot.id)
    assert (
        persisted_review.decision,
        persisted_review.checklist_payload,
        persisted_review.reviewed_content_hash,
        persisted_review.reviewed_source_manifest_hash,
    ) == review_before
    assert (
        persisted_snapshot.source_fingerprint,
        persisted_snapshot.lineage_manifest_hash,
        persisted_snapshot.source_trace_snapshot,
    ) == snapshot_before


def test_current_list_is_bounded_filtered_and_stably_sorted(db: Session) -> None:
    _project(db)
    training = _version(db, version_id="m61_list_training")
    _publish(db, training)
    sop = _version(
        db,
        version_id="m61_list_sop",
        version_number=1,
        asset_type=ReuseAssetType.SOP,
    )
    _publish(db, sop)
    page = list_current_published_assets(
        db,
        project_id="m61_project",
        limit=1,
        offset=0,
    )
    assert page.total == 2
    assert len(page.items) == 1
    filtered = list_current_published_assets(
        db,
        project_id="m61_project",
        asset_type=ReuseAssetType.SOP,
    )
    assert [item.id for item in filtered.items] == [sop.id]
    with pytest.raises(P3RepositoryValidationError):
        list_current_published_assets(
            db,
            project_id="m61_project",
            limit=101,
        )


def test_repository_boundary_has_no_delete_provider_or_p1_p2_access() -> None:
    source = pyinspect.getsource(repositories)
    assert ".delete(" not in source
    assert "DELETE FROM" not in source.upper()
    assert "provider" not in source.lower()
    assert "db_models" not in source
    assert "p3_source_eligibility" not in source


def test_repository_errors_are_safe(db: Session) -> None:
    with pytest.raises(P3RepositoryNotFound) as caught:
        get_asset_publication_state(db, "missing")
    serialized = str(caught.value).lower()
    for forbidden in ("postgresql://", "sqlite://", "password", "token"):
        assert forbidden not in serialized


def _drop_publication_shape(connection) -> None:
    connection.exec_driver_sql(
        "DROP INDEX IF EXISTS uq_reuse_asset_versions_current_published"
    )
    connection.exec_driver_sql(
        "DROP INDEX IF EXISTS "
        "ix_reuse_asset_versions_superseded_by_asset_version_id"
    )
    connection.exec_driver_sql(
        "ALTER TABLE reuse_asset_versions DROP CONSTRAINT IF EXISTS "
        "fk_reuse_asset_versions_superseded_by"
    )
    connection.exec_driver_sql(
        "ALTER TABLE reuse_asset_versions DROP CONSTRAINT IF EXISTS "
        "uq_reuse_asset_versions_publish_idempotency_key"
    )
    connection.exec_driver_sql(
        "ALTER TABLE reuse_asset_versions DROP CONSTRAINT IF EXISTS "
        "uq_reuse_asset_versions_archive_idempotency_key"
    )
    for column in (
        "published_by_role",
        "publish_request_id",
        "publish_idempotency_key",
        "superseded_by_asset_version_id",
        "archived_by_role",
        "archive_request_id",
        "archive_idempotency_key",
    ):
        connection.exec_driver_sql(
            f"ALTER TABLE reuse_asset_versions "
            f"DROP COLUMN IF EXISTS {column}"
        )


def _clear_pg_rows(session: Session, prefix: str) -> None:
    session.query(ReuseAssetVersion).filter(
        ReuseAssetVersion.project_id.like(f"{prefix}%")
    ).update(
        {ReuseAssetVersion.superseded_by_asset_version_id: None},
        synchronize_session=False,
    )
    session.query(ReuseAssetVersion).filter(
        ReuseAssetVersion.project_id.like(f"{prefix}%")
    ).delete(synchronize_session=False)
    session.query(ReuseProject).filter(
        ReuseProject.id.like(f"{prefix}%")
    ).delete(synchronize_session=False)
    session.commit()


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_compatibility_unique_slot_and_concurrent_publish() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    prefix = "p3m61_pg_"
    Base.metadata.create_all(
        bind=engine,
        tables=[ReuseProject.__table__, ReuseAssetVersion.__table__],
    )
    try:
        with SessionLocal() as session:
            _clear_pg_rows(session, prefix)
        with engine.begin() as connection:
            if connection.execute(
                text("SELECT count(*) FROM reuse_asset_versions")
            ).scalar_one() != 0:
                pytest.skip(
                    "PostgreSQL compatibility downgrade simulation requires "
                    "an otherwise empty disposable test database."
                )
            _drop_publication_shape(connection)
        assert ensure_asset_publication_compatibility(engine) is True
        assert ensure_asset_publication_compatibility(engine) is False
        inspector = inspect(engine)
        assert PUBLICATION_COLUMNS <= {
            item["name"]
            for item in inspector.get_columns("reuse_asset_versions")
        }
        assert "uq_reuse_asset_versions_current_published" in {
            item["name"]
            for item in inspector.get_indexes("reuse_asset_versions")
        }

        with SessionLocal() as session:
            _project(session, project_id=f"{prefix}project")
            first = _version(
                session,
                version_id=f"{prefix}first",
                project_id=f"{prefix}project",
            )
            second = _version(
                session,
                version_id=f"{prefix}second",
                project_id=f"{prefix}project",
                version_number=2,
            )
            first_id, second_id = first.id, second.id

        barrier = Barrier(2)

        def publish(version_id: str) -> str:
            with SessionLocal() as session:
                barrier.wait(timeout=10)
                return publish_approved_asset(
                    session,
                    asset_version_id=version_id,
                    published_by_role="admin",
                    request_id=f"request_{version_id}",
                    idempotency_key=f"publish_{version_id}",
                ).published.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert set(executor.map(publish, (first_id, second_id))) == {
                first_id,
                second_id,
            }
        with SessionLocal() as session:
            rows = (
                session.query(ReuseAssetVersion)
                .filter(
                    ReuseAssetVersion.project_id == f"{prefix}project"
                )
                .all()
            )
            current = [
                row
                for row in rows
                if row.status is ReuseAssetVersionStatus.PUBLISHED
            ]
            superseded = [
                row
                for row in rows
                if row.status is ReuseAssetVersionStatus.SUPERSEDED
            ]
            assert len(current) == 1
            assert len(superseded) == 1
            assert superseded[0].superseded_by_asset_version_id == current[0].id
            replay = publish_approved_asset(
                session,
                asset_version_id=current[0].id,
                published_by_role="admin",
                request_id=f"request_{current[0].id}",
                idempotency_key=f"publish_{current[0].id}",
            )
            assert replay.replayed is True
            archived = archive_asset(
                session,
                asset_version_id=current[0].id,
                archived_by_role="admin",
                request_id="archive_current",
                idempotency_key=f"{prefix}archive",
            )
            assert archived.status is ReuseAssetVersionStatus.ARCHIVED
            assert (
                session.query(ReuseAssetVersion)
                .filter(
                    ReuseAssetVersion.project_id == f"{prefix}project",
                    ReuseAssetVersion.status
                    == ReuseAssetVersionStatus.PUBLISHED,
                )
                .count()
                == 0
            )
    finally:
        with SessionLocal() as session:
            _clear_pg_rows(session, prefix)
        engine.dispose()
