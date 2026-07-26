"""Focused P3-M3.2 tests for deterministic draft-asset repositories."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
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

from app import p3_asset_repositories as repositories  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_asset_repositories import (  # noqa: E402
    P3AssetVersionSourceSnapshotInput,
    add_asset_version_source_snapshot,
    create_asset_version_with_source_snapshots,
    create_generating_asset_version,
    get_asset_version_by_id,
    get_asset_version_by_idempotency_key,
    list_asset_version_sources,
    list_project_asset_versions,
    mark_asset_failed,
    mark_asset_generated,
)
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
from app.p3_reuse_repositories import (  # noqa: E402
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryValidationError,
)
from app.p3_source_eligibility_schemas import P3SourceType  # noqa: E402
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
        _clear_p3_rows(session)
        yield session
        session.rollback()
        _clear_p3_rows(session)


def _clear_p3_rows(db: Session, prefix: str | None = None) -> None:
    filters = []
    if prefix is not None:
        filters = [ReuseProject.id.like(f"{prefix}%")]
        version_ids = db.query(ReuseAssetVersion.id).filter(
            ReuseAssetVersion.project_id.like(f"{prefix}%")
        )
        db.query(ReuseAssetVersionSource).filter(
            ReuseAssetVersionSource.asset_version_id.in_(version_ids)
        ).delete(synchronize_session=False)
        db.query(ReuseAssetVersion).filter(
            ReuseAssetVersion.project_id.like(f"{prefix}%")
        ).delete(synchronize_session=False)
        db.query(ReuseSourceItem).filter(
            ReuseSourceItem.project_id.like(f"{prefix}%")
        ).delete(synchronize_session=False)
    else:
        db.query(ReuseAssetVersionSource).delete(synchronize_session=False)
        db.query(ReuseAssetVersion).delete(synchronize_session=False)
        db.query(ReuseSourceItem).delete(synchronize_session=False)
    if prefix is None:
        db.query(ReuseProject).delete(synchronize_session=False)
    else:
        db.query(ReuseProject).filter(*filters).delete(synchronize_session=False)
    db.commit()


def _seed_project(
    db: Session,
    *,
    project_id: str = "m32_project",
    status: ReuseProjectStatus = ReuseProjectStatus.ACTIVE,
) -> ReuseProject:
    project = ReuseProject(
        id=project_id,
        name="M3.2 repository project",
        status=status,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=f"key_{project_id}",
    )
    db.add(project)
    db.commit()
    return project


def _seed_source(
    db: Session,
    *,
    source_item_id: str = "m32_source",
    project_id: str = "m32_project",
    source_type: P3SourceType = P3SourceType.P2_KNOWLEDGE_ASSET,
    source_version: int | None = 3,
) -> ReuseSourceItem:
    source = ReuseSourceItem(
        id=source_item_id,
        project_id=project_id,
        source_type=source_type,
        source_id=f"governed_{source_item_id}",
        source_version=source_version,
        source_fingerprint="a" * 64,
        eligibility_policy_version="p3-source-eligibility-v1",
        approved_review_id=f"review_{source_item_id}",
        snapshot_id=f"snapshot_{source_item_id}",
        knowledge_asset_id=(
            f"asset_{source_item_id}"
            if source_type is P3SourceType.P2_KNOWLEDGE_ASSET
            else None
        ),
        lineage_manifest_hash="b" * 64,
        source_trace={"source_item_id": source_item_id, "version": source_version},
        selected_by_role="cleaner",
        request_id=f"request_{source_item_id}",
    )
    db.add(source)
    db.commit()
    return source


def _snapshot(
    source: ReuseSourceItem,
    **overrides: object,
) -> P3AssetVersionSourceSnapshotInput:
    values: dict[str, object] = {
        "source_item_id": source.id,
        "source_type": source.source_type,
        "source_id": source.source_id,
        "source_version": source.source_version,
        "source_fingerprint": source.source_fingerprint,
        "approved_review_id": source.approved_review_id,
        "snapshot_id": source.snapshot_id,
        "knowledge_asset_id": source.knowledge_asset_id,
        "lineage_manifest_hash": source.lineage_manifest_hash,
        "source_trace_snapshot": dict(source.source_trace),
    }
    values.update(overrides)
    return P3AssetVersionSourceSnapshotInput(**values)


def _create_version(
    db: Session,
    *,
    project_id: str = "m32_project",
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    idempotency_key: str = "m32_asset_key",
    template_key: str = "training-material-v1",
    template_version: str = "1.0.0",
    source_manifest_hash: str = "c" * 64,
    snapshots: tuple[P3AssetVersionSourceSnapshotInput, ...] = (),
) -> ReuseAssetVersion:
    return create_asset_version_with_source_snapshots(
        db,
        project_id=project_id,
        asset_type=asset_type,
        generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        template_key=template_key,
        template_version=template_version,
        source_manifest_hash=source_manifest_hash,
        idempotency_key=idempotency_key,
        created_by_role="cleaner",
        request_id=f"request_{idempotency_key}",
        source_snapshots=snapshots,
    )


def test_version_number_starts_at_one_and_increments_per_project_asset_type(
    db: Session,
) -> None:
    _seed_project(db)
    first = _create_version(db, idempotency_key="m32_key_1")
    second = _create_version(db, idempotency_key="m32_key_2")
    other_type = _create_version(
        db,
        asset_type=ReuseAssetType.SOP,
        idempotency_key="m32_key_3",
    )
    assert (first.version_number, second.version_number) == (1, 2)
    assert other_type.version_number == 1
    assert all(
        row.status is ReuseAssetVersionStatus.GENERATING
        for row in (first, second, other_type)
    )


def test_create_generating_version_idempotency_and_lookup(db: Session) -> None:
    _seed_project(db)
    first = create_generating_asset_version(
        db,
        project_id="m32_project",
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        template_key="training-material-v1",
        template_version="1.0.0",
        source_manifest_hash="c" * 64,
        idempotency_key="m32_lookup_key",
        created_by_role="cleaner",
        request_id="request_1",
    )
    replay = create_generating_asset_version(
        db,
        project_id="m32_project",
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        template_key="training-material-v1",
        template_version="1.0.0",
        source_manifest_hash="c" * 64,
        idempotency_key="m32_lookup_key",
        created_by_role="cleaner",
        request_id="request_retry",
    )
    assert replay.id == first.id
    assert get_asset_version_by_id(db, first.id).id == first.id
    assert get_asset_version_by_idempotency_key(db, "m32_lookup_key").id == first.id
    assert db.query(ReuseAssetVersion).count() == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("template_key", "different-template"),
        ("template_version", "2.0.0"),
        ("source_manifest_hash", "d" * 64),
        ("asset_type", ReuseAssetType.SOP),
    ],
)
def test_idempotency_key_with_different_request_is_conflict(
    db: Session,
    field: str,
    value: object,
) -> None:
    _seed_project(db)
    _create_version(db, idempotency_key="m32_conflict")
    kwargs = {field: value}
    with pytest.raises(P3RepositoryConflict, match="different request"):
        _create_version(db, idempotency_key="m32_conflict", **kwargs)
    assert db.query(ReuseAssetVersion).count() == 1


def test_missing_version_returns_not_found(db: Session) -> None:
    with pytest.raises(P3RepositoryNotFound, match="not found"):
        get_asset_version_by_id(db, "missing")
    with pytest.raises(P3RepositoryNotFound, match="not found"):
        get_asset_version_by_idempotency_key(db, "missing")


def test_list_versions_is_paginated_filtered_and_stably_ordered(
    db: Session,
) -> None:
    _seed_project(db)
    first = _create_version(db, idempotency_key="m32_list_1")
    _create_version(db, idempotency_key="m32_list_2")
    _create_version(
        db,
        asset_type=ReuseAssetType.SOP,
        idempotency_key="m32_list_3",
    )
    mark_asset_generated(db, first.id, content_payload={"title": "First"})
    page = list_project_asset_versions(
        db,
        project_id="m32_project",
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        limit=1,
        offset=0,
    )
    assert page.total == 2
    assert page.limit == 1
    assert page.items[0].version_number == 2
    generated = list_project_asset_versions(
        db,
        project_id="m32_project",
        status=ReuseAssetVersionStatus.GENERATED,
    )
    assert [row.id for row in generated.items] == [first.id]


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (MAX_PAGE_LIMIT + 1, 0), (1, -1), (True, 0)],
)
def test_list_versions_rejects_invalid_pagination(
    db: Session,
    limit: int,
    offset: int,
) -> None:
    with pytest.raises(P3RepositoryValidationError):
        list_project_asset_versions(
            db,
            project_id="m32_project",
            limit=limit,
            offset=offset,
        )


def test_mark_generated_uses_canonical_hash_and_is_immutable(db: Session) -> None:
    _seed_project(db)
    row = _create_version(db)
    payload = {"sections": [{"body": "内容", "order": 1}], "title": "培训"}
    generated = mark_asset_generated(db, row.id, content_payload=payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    assert generated.content_hash == hashlib.sha256(encoded.encode()).hexdigest()
    replay = mark_asset_generated(
        db,
        row.id,
        content_payload={"title": "培训", "sections": payload["sections"]},
    )
    assert replay.id == generated.id
    with pytest.raises(P3RepositoryConflict, match="immutable"):
        mark_asset_generated(db, row.id, content_payload={"title": "Changed"})


def test_mark_failed_is_safe_idempotent_and_terminal(db: Session) -> None:
    _seed_project(db)
    row = _create_version(db)
    failed = mark_asset_failed(
        db,
        row.id,
        failure_code="TEMPLATE_RENDER_FAILED",
        failure_message=(
            "postgresql://user:password@internal/datahub token=secret\n"
            "Traceback details"
        ),
    )
    assert failed.status is ReuseAssetVersionStatus.FAILED
    assert "postgresql://" not in failed.failure_message.lower()
    assert "password" not in failed.failure_message.lower()
    replay = mark_asset_failed(
        db,
        row.id,
        failure_code="TEMPLATE_RENDER_FAILED",
        failure_message=(
            "postgresql://user:password@internal/datahub token=secret\n"
            "different hidden detail"
        ),
    )
    assert replay.id == failed.id
    with pytest.raises(P3RepositoryConflict, match="generating"):
        mark_asset_generated(db, row.id, content_payload={"title": "late"})


def test_atomic_version_and_source_snapshot_creation_is_idempotent(
    db: Session,
) -> None:
    _seed_project(db)
    source = _seed_source(db)
    snapshot = _snapshot(source)
    first = _create_version(db, snapshots=(snapshot,))
    replay = _create_version(db, snapshots=(snapshot,))
    bindings = list_asset_version_sources(db, asset_version_id=first.id)
    assert replay.id == first.id
    assert bindings.total == 1
    assert bindings.items[0].source_trace_snapshot == source.source_trace
    assert db.query(ReuseAssetVersionSource).count() == 1


def test_idempotent_asset_request_rejects_different_source_evidence(
    db: Session,
) -> None:
    _seed_project(db)
    source = _seed_source(db)
    _create_version(db, snapshots=(_snapshot(source),))
    changed = _snapshot(source, source_fingerprint="f" * 64)
    with pytest.raises(P3RepositoryConflict, match="source evidence"):
        _create_version(db, snapshots=(changed,))


def test_add_source_snapshot_exact_replay_and_conflict(db: Session) -> None:
    _seed_project(db)
    source = _seed_source(db)
    version = _create_version(db)
    snapshot = _snapshot(source)
    first = add_asset_version_source_snapshot(
        db,
        asset_version_id=version.id,
        snapshot=snapshot,
    )
    replay = add_asset_version_source_snapshot(
        db,
        asset_version_id=version.id,
        snapshot=snapshot,
    )
    assert replay.id == first.id
    with pytest.raises(P3RepositoryConflict, match="conflicts"):
        add_asset_version_source_snapshot(
            db,
            asset_version_id=version.id,
            snapshot=_snapshot(source, lineage_manifest_hash="d" * 64),
        )


def test_source_snapshots_cannot_be_added_after_generation(db: Session) -> None:
    _seed_project(db)
    source = _seed_source(db)
    version = _create_version(db)
    mark_asset_generated(db, version.id, content_payload={"title": "done"})
    with pytest.raises(P3RepositoryConflict, match="immutable"):
        add_asset_version_source_snapshot(
            db,
            asset_version_id=version.id,
            snapshot=_snapshot(source),
        )


def test_snapshot_survives_source_stale_and_logical_removal_unchanged(
    db: Session,
) -> None:
    _seed_project(db)
    source = _seed_source(db)
    version = _create_version(db, snapshots=(_snapshot(source),))
    original = list_asset_version_sources(
        db,
        asset_version_id=version.id,
    ).items[0]
    expected = (
        original.source_fingerprint,
        original.lineage_manifest_hash,
        dict(original.source_trace_snapshot),
    )
    source.source_stale = True
    source.removed_at = datetime.now(UTC)
    db.commit()
    db.expire_all()
    persisted = list_asset_version_sources(
        db,
        asset_version_id=version.id,
    ).items[0]
    assert (
        persisted.source_fingerprint,
        persisted.lineage_manifest_hash,
        persisted.source_trace_snapshot,
    ) == expected


def test_source_snapshot_must_belong_to_same_project(db: Session) -> None:
    _seed_project(db)
    _seed_project(db, project_id="m32_other_project")
    source = _seed_source(db, project_id="m32_other_project")
    with pytest.raises(P3RepositoryValidationError, match="does not belong"):
        _create_version(db, snapshots=(_snapshot(source),))
    assert db.query(ReuseAssetVersion).count() == 0


def test_list_source_snapshots_is_bounded_and_has_fixed_query_count(
    db: Session,
    sqlite_engine,
) -> None:
    _seed_project(db)
    sources = [
        _seed_source(db, source_item_id=f"m32_source_{index}")
        for index in range(4)
    ]
    version = _create_version(
        db,
        snapshots=tuple(_snapshot(source) for source in sources),
    )
    asset_version_id = version.id
    db.expunge_all()
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", count_selects)
    try:
        page = list_asset_version_sources(
            db,
            asset_version_id=asset_version_id,
            limit=2,
            offset=1,
        )
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", count_selects)
    assert page.total == 4
    assert len(page.items) == 2
    assert len(statements) == 3
    with pytest.raises(P3RepositoryValidationError):
        list_asset_version_sources(
            db,
            asset_version_id=version.id,
            limit=101,
        )


def test_version_list_query_count_does_not_grow_with_rows(
    db: Session,
    sqlite_engine,
) -> None:
    _seed_project(db)
    for index in range(5):
        _create_version(db, idempotency_key=f"m32_query_{index}")
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", count_selects)
    try:
        page = list_project_asset_versions(db, project_id="m32_project")
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", count_selects)
    assert page.total == 5
    assert len(page.items) == 5
    assert len(statements) == 2


def test_commit_failure_rolls_back_then_finite_retry_succeeds(db: Session) -> None:
    _seed_project(db)
    real_commit = db.commit
    calls = 0

    def flaky_commit() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise IntegrityError("synthetic conflict", {}, RuntimeError("race"))
        real_commit()

    with patch.object(db, "commit", side_effect=flaky_commit):
        row = _create_version(db, idempotency_key="m32_retry")
    assert row.version_number == 1
    assert calls == 2
    assert db.query(ReuseAssetVersion).count() == 1


def test_repository_boundary_excludes_business_rules_and_physical_delete() -> None:
    module_source = inspect.getsource(repositories)
    assert "p3_source_eligibility import" not in module_source
    assert "db_models" not in module_source
    assert "provider" not in module_source.lower()
    assert ".delete(" not in module_source
    assert "DELETE FROM" not in module_source.upper()


def test_repository_errors_do_not_leak_database_details(db: Session) -> None:
    _seed_project(db)
    _create_version(db, idempotency_key="m32_safe")
    with pytest.raises(P3RepositoryConflict) as caught:
        _create_version(
            db,
            idempotency_key="m32_safe",
            source_manifest_hash="f" * 64,
        )
    serialized = str(caught.value).lower()
    for forbidden in ("postgresql://", "sqlite://", "password", "localhost"):
        assert forbidden not in serialized


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_concurrent_versioning_idempotency_and_atomic_snapshots() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    prefix = "p3m32_pg_"
    Base.metadata.create_all(
        bind=engine,
        tables=[
            ReuseProject.__table__,
            ReuseSourceItem.__table__,
            ReuseAssetVersion.__table__,
            ReuseAssetVersionSource.__table__,
        ],
    )
    try:
        with SessionLocal() as session:
            _clear_p3_rows(session, prefix)
            _seed_project(session, project_id=f"{prefix}project")
            source = _seed_source(
                session,
                source_item_id=f"{prefix}source",
                project_id=f"{prefix}project",
            )
            snapshot = _snapshot(source)

        barrier = Barrier(2)

        def create_concurrent(key: str) -> tuple[int, str]:
            with SessionLocal() as session:
                barrier.wait(timeout=10)
                row = _create_version(
                    session,
                    project_id=f"{prefix}project",
                    idempotency_key=key,
                    snapshots=(snapshot,),
                )
                return row.version_number, row.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    create_concurrent,
                    [f"{prefix}key_1", f"{prefix}key_2"],
                )
            )
        assert sorted(number for number, _row_id in results) == [1, 2]

        same_key_barrier = Barrier(2)

        def create_same_request(_index: int) -> str:
            with SessionLocal() as session:
                same_key_barrier.wait(timeout=10)
                return _create_version(
                    session,
                    project_id=f"{prefix}project",
                    asset_type=ReuseAssetType.SOP,
                    idempotency_key=f"{prefix}same_key",
                    snapshots=(snapshot,),
                ).id

        with ThreadPoolExecutor(max_workers=2) as executor:
            replay_ids = list(executor.map(create_same_request, range(2)))
        assert replay_ids[0] == replay_ids[1]

        with SessionLocal() as session:
            versions = session.query(ReuseAssetVersion).filter(
                ReuseAssetVersion.project_id == f"{prefix}project"
            )
            assert versions.count() == 3
            assert session.query(ReuseAssetVersionSource).join(
                ReuseAssetVersion,
                ReuseAssetVersion.id
                == ReuseAssetVersionSource.asset_version_id,
            ).filter(
                ReuseAssetVersion.project_id == f"{prefix}project"
            ).count() == 3

            before = versions.count()
            with pytest.raises(P3RepositoryValidationError):
                _create_version(
                    session,
                    project_id=f"{prefix}project",
                    idempotency_key=f"{prefix}invalid_source",
                    snapshots=(
                        P3AssetVersionSourceSnapshotInput(
                            source_item_id=f"{prefix}missing",
                            source_type=P3SourceType.P1_KNOWLEDGE,
                            source_id="missing",
                            source_version=None,
                            source_fingerprint="a" * 64,
                            approved_review_id="review",
                            snapshot_id=None,
                            knowledge_asset_id=None,
                            lineage_manifest_hash="b" * 64,
                            source_trace_snapshot={"source_id": "missing"},
                        ),
                    ),
                )
            assert versions.count() == before
    finally:
        with SessionLocal() as session:
            _clear_p3_rows(session, prefix)
        engine.dispose()
