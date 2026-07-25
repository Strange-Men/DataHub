"""Focused P3-M2.2 tests for project/source persistence repositories."""

from __future__ import annotations

import inspect
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db_models as p1_p2_models  # noqa: E402
from app import p3_reuse_repositories as repositories  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import (  # noqa: E402
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryValidationError,
    add_source_item,
    create_project,
    get_project_by_id,
    get_project_by_idempotency_key,
    get_source_item_by_id,
    get_source_item_by_identity,
    list_project_source_items,
    list_projects,
    logically_remove_source_item,
    mark_source_stale,
    set_project_status,
    update_project_metadata,
)
from app.p3_source_eligibility_schemas import (  # noqa: E402
    P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
    P3SourceType,
)
from scripts.test_environment import require_test_database_url  # noqa: E402


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()


@pytest.fixture(scope="module")
def sqlite_engine():
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

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db(sqlite_engine):
    SessionLocal = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with SessionLocal() as session:
        session.query(ReuseSourceItem).delete()
        session.query(ReuseProject).delete()
        session.query(p1_p2_models.KnowledgeCandidate).filter(
            p1_p2_models.KnowledgeCandidate.id.like("p3m22_%")
        ).delete(synchronize_session=False)
        session.query(p1_p2_models.Asset).filter(
            p1_p2_models.Asset.id.like("p3m22_%")
        ).delete(synchronize_session=False)
        session.commit()
        yield session
        session.rollback()
        session.query(ReuseSourceItem).delete()
        session.query(ReuseProject).delete()
        session.query(p1_p2_models.KnowledgeCandidate).filter(
            p1_p2_models.KnowledgeCandidate.id.like("p3m22_%")
        ).delete(synchronize_session=False)
        session.query(p1_p2_models.Asset).filter(
            p1_p2_models.Asset.id.like("p3m22_%")
        ).delete(synchronize_session=False)
        session.commit()


def _create_project(
    db: Session,
    *,
    project_id: str = "reuse_project_1",
    name: str = "客服培训复用",
    description: str | None = "Repository test",
    status: ReuseProjectStatus = ReuseProjectStatus.DRAFT,
    idempotency_key: str = "project-key-1",
    request_id: str = "request-project-1",
) -> ReuseProject:
    return create_project(
        db,
        project_id=project_id,
        name=name,
        description=description,
        status=status,
        created_by_role="cleaner",
        request_id=request_id,
        idempotency_key=idempotency_key,
    )


def _add_source(
    db: Session,
    *,
    source_item_id: str = "reuse_source_1",
    project_id: str = "reuse_project_1",
    source_type: P3SourceType = P3SourceType.P1_KNOWLEDGE,
    source_id: str = "candidate_1",
    source_version: int | None = None,
    source_fingerprint: str = "a" * 64,
    approved_review_id: str | None = "review_1",
    snapshot_id: str | None = None,
    knowledge_asset_id: str | None = None,
    lineage_manifest_hash: str | None = "b" * 64,
    source_trace: dict[str, object] | None = None,
    request_id: str = "request-source-1",
) -> ReuseSourceItem:
    trace = source_trace or {
        "source_id": source_id,
        "source_type": source_type.value,
        "content_hash": source_fingerprint,
    }
    return add_source_item(
        db,
        source_item_id=source_item_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        source_fingerprint=source_fingerprint,
        eligibility_policy_version=P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
        approved_review_id=approved_review_id,
        snapshot_id=snapshot_id,
        knowledge_asset_id=knowledge_asset_id,
        lineage_manifest_hash=lineage_manifest_hash,
        source_trace=trace,
        selected_by_role="cleaner",
        request_id=request_id,
    )


def test_create_draft_project(db: Session) -> None:
    project = _create_project(db)
    assert project.status is ReuseProjectStatus.DRAFT
    assert db.query(ReuseProject).count() == 1


def test_project_idempotency_same_payload_returns_same_row(db: Session) -> None:
    first = _create_project(db)
    replay = _create_project(db, request_id="request-project-retry")
    assert replay.id == first.id
    assert replay.request_id == "request-project-1"
    assert db.query(ReuseProject).count() == 1


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("name", "不同名称"),
        ("description", "Different description"),
        ("status", ReuseProjectStatus.ACTIVE),
        ("project_id", "reuse_project_other"),
    ],
)
def test_project_idempotency_different_payload_is_conflict(
    db: Session,
    field_name: str,
    field_value: object,
) -> None:
    _create_project(db)
    values = {field_name: field_value}
    with pytest.raises(P3RepositoryConflict, match="different payload"):
        _create_project(db, **values)
    assert db.query(ReuseProject).count() == 1


def test_get_project_by_id_and_idempotency_key(db: Session) -> None:
    project = _create_project(db)
    assert get_project_by_id(db, project.id).id == project.id
    assert get_project_by_idempotency_key(db, project.idempotency_key).id == project.id


@pytest.mark.parametrize(
    ("getter", "value"),
    [
        (get_project_by_id, "missing-project"),
        (get_project_by_idempotency_key, "missing-key"),
    ],
)
def test_missing_project_returns_repository_not_found(
    db: Session,
    getter,
    value: str,
) -> None:
    with pytest.raises(P3RepositoryNotFound, match="not found"):
        getter(db, value)


def test_update_project_name_and_description(db: Session) -> None:
    project = _create_project(db)
    updated = update_project_metadata(
        db,
        project.id,
        name="更新后的培训项目",
        description=None,
    )
    assert updated.name == "更新后的培训项目"
    assert updated.description is None
    assert updated.id == project.id
    assert updated.idempotency_key == project.idempotency_key


def test_update_metadata_cannot_accept_protected_fields(db: Session) -> None:
    project = _create_project(db)
    with pytest.raises(TypeError):
        update_project_metadata(
            db,
            project.id,
            status=ReuseProjectStatus.ARCHIVED,
        )
    db.expire_all()
    persisted = get_project_by_id(db, project.id)
    assert persisted.status is ReuseProjectStatus.DRAFT
    assert persisted.created_by_role == "cleaner"


def test_set_project_status_persists_only_enum_values(db: Session) -> None:
    project = _create_project(db)
    active = set_project_status(db, project.id, ReuseProjectStatus.ACTIVE)
    assert active.status is ReuseProjectStatus.ACTIVE
    archived = set_project_status(db, project.id, ReuseProjectStatus.ARCHIVED)
    assert archived.status is ReuseProjectStatus.ARCHIVED
    assert archived.archived_at is not None
    with pytest.raises(P3RepositoryValidationError, match="ReuseProjectStatus"):
        set_project_status(db, project.id, "draft")  # type: ignore[arg-type]


def test_project_pagination_and_stable_sorting(db: Session) -> None:
    projects = [
        _create_project(
            db,
            project_id=f"reuse_project_{suffix}",
            idempotency_key=f"project-key-{suffix}",
        )
        for suffix in ("a", "b", "c")
    ]
    fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
    for project in projects:
        project.created_at = fixed_time
    db.commit()
    page = list_projects(db, limit=1, offset=1)
    assert [item.id for item in page.items] == ["reuse_project_b"]
    assert (page.total, page.limit, page.offset) == (3, 1, 1)


def test_project_status_filter(db: Session) -> None:
    _create_project(db, project_id="draft", idempotency_key="key-draft")
    _create_project(
        db,
        project_id="active",
        idempotency_key="key-active",
        status=ReuseProjectStatus.ACTIVE,
    )
    page = list_projects(db, status=ReuseProjectStatus.ACTIVE)
    assert page.total == 1
    assert page.items[0].id == "active"


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (-1, 0), (MAX_PAGE_LIMIT + 1, 0), (True, 0), (10, -1), (10, True)],
)
def test_invalid_project_pagination_fails_safely(
    db: Session,
    limit: object,
    offset: object,
) -> None:
    with pytest.raises(P3RepositoryValidationError):
        list_projects(db, limit=limit, offset=offset)  # type: ignore[arg-type]


def test_add_p1_source_evidence(db: Session) -> None:
    _create_project(db)
    source = _add_source(db)
    assert source.source_type is P3SourceType.P1_KNOWLEDGE
    assert source.source_version_key == 0


def test_add_p2_complete_lineage(db: Session) -> None:
    _create_project(db)
    source = _add_source(
        db,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id="knowledge_asset_1",
        source_version=3,
        approved_review_id="review_p2",
        snapshot_id="snapshot_p2",
        knowledge_asset_id="knowledge_asset_1",
        lineage_manifest_hash="c" * 64,
        source_trace={
            "review_id": "review_p2",
            "snapshot_id": "snapshot_p2",
            "knowledge_asset_id": "knowledge_asset_1",
            "knowledge_asset_version": 3,
        },
    )
    assert source.snapshot_id == "snapshot_p2"
    assert source.knowledge_asset_id == "knowledge_asset_1"
    assert source.source_version_key == 3


def test_add_approved_bad_case_correction(db: Session) -> None:
    _create_project(db)
    source = _add_source(
        db,
        source_type=P3SourceType.APPROVED_BAD_CASE_CORRECTION,
        source_id="candidate_correction_1",
    )
    assert source.source_type is P3SourceType.APPROVED_BAD_CASE_CORRECTION


@pytest.mark.parametrize("source_type", ["RAW_BAD_CASE", "P3_ASSET"])
def test_raw_bad_case_and_invalid_source_types_are_rejected(
    db: Session,
    source_type: str,
) -> None:
    _create_project(db)
    with pytest.raises(P3RepositoryValidationError, match="P3SourceType"):
        add_source_item(
            db,
            source_item_id="source-invalid",
            project_id="reuse_project_1",
            source_type=source_type,  # type: ignore[arg-type]
            source_id="invalid",
            source_version=None,
            source_fingerprint="a" * 64,
            eligibility_policy_version=P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
            approved_review_id=None,
            snapshot_id=None,
            knowledge_asset_id=None,
            lineage_manifest_hash=None,
            source_trace={},
            selected_by_role="cleaner",
            request_id="request-invalid",
        )
    assert db.query(ReuseSourceItem).count() == 0


def test_same_source_evidence_replay_is_idempotent(db: Session) -> None:
    _create_project(db)
    first = _add_source(db)
    replay = _add_source(
        db,
        source_item_id="reuse_source_replay",
        request_id="request-source-retry",
    )
    assert replay.id == first.id
    assert replay.request_id == "request-source-1"
    assert db.query(ReuseSourceItem).count() == 1


def test_same_source_identity_different_fingerprint_is_conflict(db: Session) -> None:
    _create_project(db)
    _add_source(db)
    with pytest.raises(P3RepositoryConflict, match="different eligibility evidence"):
        _add_source(
            db,
            source_item_id="reuse_source_other",
            source_fingerprint="f" * 64,
        )
    assert db.query(ReuseSourceItem).count() == 1


@pytest.mark.parametrize(
    ("lineage_manifest_hash", "source_trace"),
    [
        ("d" * 64, None),
        ("b" * 64, {"source_id": "candidate_1", "review_id": "changed"}),
    ],
)
def test_same_source_identity_different_lineage_is_conflict(
    db: Session,
    lineage_manifest_hash: str,
    source_trace: dict[str, object] | None,
) -> None:
    _create_project(db)
    _add_source(db)
    with pytest.raises(P3RepositoryConflict, match="different eligibility evidence"):
        _add_source(
            db,
            source_item_id="reuse_source_other",
            lineage_manifest_hash=lineage_manifest_hash,
            source_trace=source_trace,
        )


def test_different_projects_can_reference_same_source(db: Session) -> None:
    _create_project(db)
    _create_project(
        db,
        project_id="reuse_project_2",
        idempotency_key="project-key-2",
    )
    _add_source(db)
    _add_source(
        db,
        source_item_id="reuse_source_2",
        project_id="reuse_project_2",
    )
    assert db.query(ReuseSourceItem).count() == 2


def test_same_source_different_versions_can_be_added(db: Session) -> None:
    _create_project(db)
    _add_source(db, source_item_id="source-v1", source_version=1)
    _add_source(db, source_item_id="source-v2", source_version=2)
    assert {
        item.source_version
        for item in db.query(ReuseSourceItem).all()
    } == {1, 2}


def test_get_source_by_id_and_identity(db: Session) -> None:
    _create_project(db)
    source = _add_source(db, source_version=2)
    assert get_source_item_by_id(db, source.id).id == source.id
    found = get_source_item_by_identity(
        db,
        project_id=source.project_id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version_key=2,
    )
    assert found.id == source.id


def test_missing_source_returns_repository_not_found(db: Session) -> None:
    with pytest.raises(P3RepositoryNotFound, match="not found"):
        get_source_item_by_id(db, "missing-source")
    with pytest.raises(P3RepositoryNotFound, match="not found"):
        get_source_item_by_identity(
            db,
            project_id="missing-project",
            source_type=P3SourceType.P1_KNOWLEDGE,
            source_id="missing-source",
            source_version_key=0,
        )


def test_project_source_pagination_and_stable_order(db: Session) -> None:
    _create_project(db)
    sources = [
        _add_source(
            db,
            source_item_id=f"reuse_source_{suffix}",
            source_id=f"candidate_{suffix}",
        )
        for suffix in ("a", "b", "c")
    ]
    fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
    for source in sources:
        source.created_at = fixed_time
    db.commit()
    page = list_project_source_items(
        db,
        project_id="reuse_project_1",
        limit=1,
        offset=1,
    )
    assert [item.id for item in page.items] == ["reuse_source_b"]
    assert (page.total, page.limit, page.offset) == (3, 1, 1)


def test_source_type_filter(db: Session) -> None:
    _create_project(db)
    _add_source(db)
    _add_source(
        db,
        source_item_id="source-p2",
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id="knowledge_asset_1",
        source_version=1,
    )
    page = list_project_source_items(
        db,
        project_id="reuse_project_1",
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
    )
    assert page.total == 1
    assert page.items[0].id == "source-p2"


def test_source_stale_filter_and_mark_are_idempotent(db: Session) -> None:
    _create_project(db)
    source = _add_source(db)
    original_trace = dict(source.source_trace)
    first = mark_source_stale(db, source.id)
    second = mark_source_stale(db, source.id)
    assert first.source_stale is True
    assert second.id == first.id
    assert second.source_trace == original_trace
    stale = list_project_source_items(
        db,
        project_id=source.project_id,
        source_stale=True,
    )
    current = list_project_source_items(
        db,
        project_id=source.project_id,
        source_stale=False,
    )
    assert stale.total == 1
    assert current.total == 0


def test_logical_remove_is_idempotent_and_list_visibility_is_explicit(
    db: Session,
) -> None:
    _create_project(db)
    source = _add_source(db)
    first = logically_remove_source_item(db, source.id)
    removed_at = first.removed_at
    second = logically_remove_source_item(db, source.id)
    assert second.removed_at == removed_at
    assert get_source_item_by_id(db, source.id).id == source.id
    assert list_project_source_items(db, project_id=source.project_id).total == 0
    included = list_project_source_items(
        db,
        project_id=source.project_id,
        include_removed=True,
    )
    assert included.total == 1
    assert included.items[0].id == source.id


def test_source_trace_round_trips_without_mutation(db: Session) -> None:
    _create_project(db)
    trace = {
        "candidate_id": "candidate_1",
        "review": {"id": "review_1", "action": "approved"},
        "source_refs": ["chunk_1", "chunk_2"],
    }
    source = _add_source(db, source_trace=trace)
    trace["candidate_id"] = "caller-mutated"
    db.expire_all()
    persisted = get_source_item_by_id(db, source.id)
    assert persisted.source_trace["candidate_id"] == "candidate_1"
    assert persisted.source_trace["review"]["action"] == "approved"


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (MAX_PAGE_LIMIT + 1, 0), (10, -1)],
)
def test_invalid_source_pagination_fails_safely(
    db: Session,
    limit: int,
    offset: int,
) -> None:
    with pytest.raises(P3RepositoryValidationError):
        list_project_source_items(
            db,
            project_id="reuse_project_1",
            limit=limit,
            offset=offset,
        )


def test_list_source_query_count_is_constant_without_n_plus_one(
    db: Session,
    sqlite_engine,
) -> None:
    _create_project(db)
    for index in range(8):
        _add_source(
            db,
            source_item_id=f"source-{index}",
            source_id=f"candidate-{index}",
        )

    select_statements: list[str] = []

    def capture_select(
        _conn,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", capture_select)
    try:
        page = list_project_source_items(
            db,
            project_id="reuse_project_1",
            limit=5,
        )
        assert len(page.items) == 5
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", capture_select)
    assert len(select_statements) == 2
    assert all("knowledge_candidates" not in sql for sql in select_statements)
    assert all("knowledge_assets" not in sql for sql in select_statements)


def test_constraint_conflict_rolls_back_and_session_remains_usable(
    db: Session,
) -> None:
    _create_project(db)
    with pytest.raises(P3RepositoryConflict, match="persistence conflict"):
        _create_project(
            db,
            idempotency_key="different-key",
        )
    recovered = _create_project(
        db,
        project_id="reuse_project_2",
        idempotency_key="project-key-2",
    )
    assert recovered.id == "reuse_project_2"
    assert db.query(ReuseProject).count() == 2


def test_source_write_failure_leaves_no_half_success_and_session_recovers(
    db: Session,
) -> None:
    _create_project(db)
    _add_source(db)
    with pytest.raises(P3RepositoryConflict, match="persistence conflict"):
        _add_source(
            db,
            source_item_id="reuse_source_1",
            source_id="candidate_other",
        )
    assert db.query(ReuseSourceItem).count() == 1
    recovered = _add_source(
        db,
        source_item_id="reuse_source_2",
        source_id="candidate_2",
    )
    assert recovered.id == "reuse_source_2"


def test_repository_does_not_modify_p1_or_p2_rows(db: Session) -> None:
    candidate = p1_p2_models.KnowledgeCandidate(
        id="p3m22_candidate",
        source_type="sanitized_batch",
        source_id="p3m22_batch",
        question="Original question",
        answer="Original answer",
        status="approved",
    )
    asset = p1_p2_models.Asset(
        id="p3m22_asset",
        asset_type="image",
        file_name="original.png",
        mime_type="image/png",
        size=1,
        storage_uri="test://original.png",
        hash="e" * 64,
        status="uploaded",
    )
    db.add_all([candidate, asset])
    db.commit()
    _create_project(db)
    _add_source(db)
    assert db.get(p1_p2_models.KnowledgeCandidate, candidate.id).answer == "Original answer"
    assert db.get(p1_p2_models.Asset, asset.id).status == "uploaded"


def test_repository_does_not_call_eligibility_provider_or_network(
    db: Session,
) -> None:
    _create_project(db)
    with patch(
        "app.p3_source_eligibility.check_source_eligibility",
        side_effect=AssertionError("eligibility core must not run"),
    ):
        with patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network must not run"),
        ):
            source = _add_source(db)
    assert source.id == "reuse_source_1"

    module_source = inspect.getsource(repositories).lower()
    for forbidden in (
        "check_source_eligibility",
        "require_permission",
        "fastapi",
        "openai",
        "embedding",
        "provider",
    ):
        assert forbidden not in module_source


def test_repository_has_no_physical_delete_flow() -> None:
    module_source = inspect.getsource(repositories)
    assert ".delete(" not in module_source
    assert "DELETE FROM" not in module_source.upper()


def test_repository_errors_do_not_leak_database_connection_details(
    db: Session,
) -> None:
    _create_project(db)
    _add_source(db)
    with pytest.raises(P3RepositoryConflict) as caught:
        _add_source(
            db,
            source_item_id="reuse_source_other",
            source_fingerprint="f" * 64,
        )
    message = str(caught.value).lower()
    for forbidden in ("sqlite://", "postgresql://", "password", "localhost"):
        assert forbidden not in message


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_constraints_idempotency_and_rollback() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    prefix = "p3m22_pg_"
    Base.metadata.create_all(
        bind=engine,
        tables=[ReuseProject.__table__, ReuseSourceItem.__table__],
    )
    try:
        with SessionLocal() as session:
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.commit()

            project = _create_project(
                session,
                project_id=f"{prefix}project",
                idempotency_key=f"{prefix}key",
            )
            replay = _create_project(
                session,
                project_id=project.id,
                idempotency_key=project.idempotency_key,
                request_id=f"{prefix}retry",
            )
            assert replay.id == project.id

            session.add(
                ReuseProject(
                    id=f"{prefix}duplicate_project",
                    name="duplicate",
                    status=ReuseProjectStatus.DRAFT,
                    created_by_role="cleaner",
                    request_id=f"{prefix}duplicate_request",
                    idempotency_key=project.idempotency_key,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            source = _add_source(
                session,
                source_item_id=f"{prefix}source_1",
                project_id=project.id,
                source_id=f"{prefix}candidate",
            )
            session.add(
                ReuseSourceItem(
                    id=f"{prefix}duplicate_source",
                    project_id=project.id,
                    source_type=P3SourceType.P1_KNOWLEDGE,
                    source_id=source.source_id,
                    source_version=None,
                    source_fingerprint=source.source_fingerprint,
                    eligibility_policy_version=source.eligibility_policy_version,
                    source_trace=dict(source.source_trace),
                    selected_by_role="cleaner",
                    request_id=f"{prefix}duplicate_source_request",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            recovered = _add_source(
                session,
                source_item_id=f"{prefix}source_2",
                project_id=project.id,
                source_id=source.source_id,
                source_version=2,
            )
            assert recovered.source_version_key == 2
            assert session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{prefix}%")
            ).count() == 2
    finally:
        with SessionLocal() as session:
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            session.commit()
        engine.dispose()
