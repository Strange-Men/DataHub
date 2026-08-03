"""Focused P3-M5.2 manual-revision and Review repository tests."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import p3_review_repositories as repositories  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_asset_repositories import (  # noqa: E402
    P3AssetVersionSourceSnapshotInput,
    create_asset_version_with_source_snapshots,
    mark_asset_generated,
)
from app.p3_review_repositories import (  # noqa: E402
    create_manual_revision_with_snapshots,
    create_review_decision,
    get_child_revisions,
    get_parent_asset_version,
    get_review_by_asset_version,
    get_review_by_idempotency_key,
    list_project_reviews,
    submit_asset_for_review,
)
from app.p3_review_schemas import P3_REVIEW_POLICY_VERSION  # noqa: E402
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


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seed_project(
    db: Session,
    project_id: str = "m52_project",
) -> ReuseProject:
    project = ReuseProject(
        id=project_id,
        name="M5.2 review repository",
        status=ReuseProjectStatus.ACTIVE,
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
    project_id: str = "m52_project",
    source_id: str = "m52_source",
) -> ReuseSourceItem:
    source = ReuseSourceItem(
        id=source_id,
        project_id=project_id,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id=f"knowledge_asset_{source_id}",
        source_version=3,
        source_fingerprint="a" * 64,
        eligibility_policy_version="p3-source-eligibility-v1",
        approved_review_id="asset_review_1",
        snapshot_id="asset_snapshot_1",
        knowledge_asset_id=f"knowledge_asset_{source_id}",
        lineage_manifest_hash="b" * 64,
        source_trace={
            "governed": True,
            "source_id": f"knowledge_asset_{source_id}",
        },
        selected_by_role="cleaner",
        request_id=f"request_{source_id}",
    )
    db.add(source)
    db.commit()
    return source


def _snapshot(source: ReuseSourceItem) -> P3AssetVersionSourceSnapshotInput:
    return P3AssetVersionSourceSnapshotInput(
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=source.source_version,
        source_fingerprint=source.source_fingerprint,
        approved_review_id=source.approved_review_id,
        snapshot_id=source.snapshot_id,
        knowledge_asset_id=source.knowledge_asset_id,
        lineage_manifest_hash=source.lineage_manifest_hash or "",
        source_trace_snapshot=dict(source.source_trace),
    )


def _seed_parent(
    db: Session,
    *,
    project_id: str = "m52_project",
    source_id: str = "m52_source",
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    parent_key: str = "m52_parent_key",
) -> ReuseAssetVersion:
    if db.get(ReuseProject, project_id) is None:
        _seed_project(db, project_id)
    source = db.get(ReuseSourceItem, source_id)
    if source is None:
        source = _seed_source(db, project_id=project_id, source_id=source_id)
    version = create_asset_version_with_source_snapshots(
        db,
        project_id=project_id,
        asset_type=asset_type,
        generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        template_key="p3.deterministic.training_material.v1",
        template_version="v1",
        source_manifest_hash="c" * 64,
        idempotency_key=parent_key,
        created_by_role="cleaner",
        request_id=f"request_{parent_key}",
        source_snapshots=(_snapshot(source),),
    )
    return mark_asset_generated(
        db,
        version.id,
        content_payload={
            "title": "Parent",
            "sections": [],
            "source_refs": [],
        },
    )


def _manual_payload(title: str = "Human revision") -> dict[str, object]:
    return {
        "title": title,
        "sections": [
            {
                "heading": "Governed",
                "content": "Approved content only.",
                "source_refs": [{"source_item_id": "m52_source"}],
            }
        ],
        "source_refs": [{"source_item_id": "m52_source"}],
    }


def _create_revision(
    db: Session,
    parent: ReuseAssetVersion,
    *,
    key: str = "m52_revision_key",
    title: str = "Human revision",
) -> ReuseAssetVersion:
    return create_manual_revision_with_snapshots(
        db,
        project_id=parent.project_id,
        parent_asset_version_id=parent.id,
        content_payload=_manual_payload(title),
        idempotency_key=key,
        created_by_role="cleaner",
        request_id=f"request_{key}",
    )


def _checklist(all_true: bool = True) -> dict[str, object]:
    return {
        "structure_complete": all_true,
        "source_refs_valid": True,
        "no_unsupported_claims_confirmed": True,
        "safe_for_reuse": True,
    }


def _decide(
    db: Session,
    version: ReuseAssetVersion,
    *,
    decision: ReuseReviewDecision = ReuseReviewDecision.APPROVED,
    key: str = "m52_review_key",
    comments: str | None = None,
) -> ReuseReview:
    if comments is None and decision is not ReuseReviewDecision.APPROVED:
        comments = "Human reviewer requested this outcome."
    return create_review_decision(
        db,
        asset_version_id=version.id,
        decision=decision,
        comments=comments,
        checklist_payload=_checklist(
            decision is ReuseReviewDecision.APPROVED
        ),
        review_policy_version=P3_REVIEW_POLICY_VERSION,
        reviewer_role="reviewer",
        request_id=f"request_{key}",
        idempotency_key=key,
    )


def test_manual_revision_is_atomic_generated_child_with_copied_snapshots(
    db: Session,
) -> None:
    parent = _seed_parent(db)
    child = _create_revision(db, parent)
    assert child.version_number == parent.version_number + 1
    assert child.parent_asset_version_id == parent.id
    assert child.generation_mode is ReuseGenerationMode.MANUAL_REVISION
    assert child.status is ReuseAssetVersionStatus.GENERATED
    assert child.asset_type is parent.asset_type
    assert child.source_manifest_hash == parent.source_manifest_hash
    assert child.content_hash == _canonical_hash(_manual_payload())
    parent_sources = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == parent.id)
        .all()
    )
    child_sources = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == child.id)
        .all()
    )
    assert len(parent_sources) == len(child_sources) == 1
    assert child_sources[0].source_trace_snapshot == parent_sources[0].source_trace_snapshot
    assert child_sources[0].source_fingerprint == parent_sources[0].source_fingerprint


def test_parent_later_change_does_not_rewrite_child_snapshot(
    db: Session,
) -> None:
    parent = _seed_parent(db)
    child = _create_revision(db, parent)
    parent_source = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == parent.id)
        .one()
    )
    child_source = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == child.id)
        .one()
    )
    original = dict(child_source.source_trace_snapshot)
    parent_source.source_trace_snapshot = {"changed": True}
    parent_source.source_fingerprint = "f" * 64
    db.commit()
    db.refresh(child_source)
    assert child_source.source_trace_snapshot == original
    assert child_source.source_fingerprint == "a" * 64


def test_manual_revision_idempotency_and_conflict(
    db: Session,
) -> None:
    parent = _seed_parent(db)
    first = _create_revision(db, parent)
    replay = _create_revision(db, parent)
    assert replay.id == first.id
    assert (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.idempotency_key == "m52_revision_key")
        .count()
        == 1
    )
    with pytest.raises(P3RepositoryConflict):
        _create_revision(db, parent, title="Different content")


def test_manual_revision_validation_and_atomic_rollback(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _seed_parent(db)
    with pytest.raises(P3RepositoryNotFound):
        create_manual_revision_with_snapshots(
            db,
            project_id=parent.project_id,
            parent_asset_version_id="missing",
            content_payload=_manual_payload(),
            idempotency_key="missing_key",
            created_by_role="cleaner",
            request_id="missing_request",
        )
    real_commit = db.commit

    def fail_commit() -> None:
        raise IntegrityError("forced", {}, RuntimeError("forced"))

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(P3RepositoryConflict):
        _create_revision(db, parent, key="rollback_key")
    monkeypatch.setattr(db, "commit", real_commit)
    db.rollback()
    assert (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.idempotency_key == "rollback_key")
        .count()
        == 0
    )
    assert (
        db.query(ReuseAssetVersionSource)
        .filter(
            ReuseAssetVersionSource.asset_version_id.like(
                "reuse_asset_version_%"
            ),
            ReuseAssetVersionSource.asset_version_id != parent.id,
        )
        .count()
        == 0
    )


def test_parent_child_queries_are_bounded_and_stable(db: Session) -> None:
    parent = _seed_parent(db)
    first = _create_revision(db, parent, key="child_1", title="First")
    second = _create_revision(db, parent, key="child_2", title="Second")
    page = get_child_revisions(
        db,
        parent_asset_version_id=parent.id,
        limit=1,
        offset=0,
    )
    assert page.total == 2
    assert page.items[0].id == second.id
    assert get_parent_asset_version(db, first.id).id == parent.id
    with pytest.raises(P3RepositoryValidationError):
        get_child_revisions(
            db,
            parent_asset_version_id=parent.id,
            limit=101,
        )


@pytest.mark.parametrize(
    "status",
    (
        ReuseAssetVersionStatus.FAILED,
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.REJECTED,
        ReuseAssetVersionStatus.NEEDS_REVISION,
    ),
)
def test_submit_for_review_rejects_non_generated_states(
    db: Session,
    status: ReuseAssetVersionStatus,
) -> None:
    parent = _seed_parent(db)
    parent.status = status
    db.commit()
    with pytest.raises(P3RepositoryConflict):
        submit_asset_for_review(db, asset_version_id=parent.id)


def test_submit_for_review_is_idempotent_and_preserves_content(
    db: Session,
) -> None:
    parent = _seed_parent(db)
    payload = dict(parent.content_payload)
    content_hash = parent.content_hash
    first = submit_asset_for_review(
        db,
        asset_version_id=parent.id,
        idempotency_key="submit_key",
    )
    replay = submit_asset_for_review(
        db,
        asset_version_id=parent.id,
        idempotency_key="submit_key",
    )
    assert first.id == replay.id
    assert replay.status is ReuseAssetVersionStatus.PENDING_REVIEW
    assert replay.content_payload == payload
    assert replay.content_hash == content_hash
    assert (
        db.query(ReuseReview)
        .filter(ReuseReview.asset_version_id == parent.id)
        .count()
        == 0
    )


@pytest.mark.parametrize("decision", list(ReuseReviewDecision))
def test_review_decision_and_asset_state_commit_atomically(
    db: Session,
    decision: ReuseReviewDecision,
) -> None:
    project_id = f"project_{decision.value}"
    source_id = f"source_{decision.value}"
    parent = _seed_parent(
        db,
        project_id=project_id,
        source_id=source_id,
        parent_key=f"parent_{decision.value}",
    )
    submit_asset_for_review(db, asset_version_id=parent.id)
    review = _decide(
        db,
        parent,
        decision=decision,
        key=f"review_{decision.value}",
    )
    db.refresh(parent)
    assert parent.status.value == decision.value
    assert (parent.approved_at is not None) is (
        decision is ReuseReviewDecision.APPROVED
    )
    assert review.reviewed_content_hash == parent.content_hash
    assert (
        review.reviewed_source_manifest_hash
        == parent.source_manifest_hash
    )
    assert get_review_by_asset_version(db, parent.id).id == review.id
    assert get_review_by_idempotency_key(db, review.idempotency_key).id == review.id
    assert parent.status is not ReuseAssetVersionStatus.PUBLISHED


def test_review_idempotency_conflict_and_single_final_decision(
    db: Session,
) -> None:
    parent = _seed_parent(db)
    submit_asset_for_review(db, asset_version_id=parent.id)
    first = _decide(db, parent)
    replay = _decide(db, parent)
    assert replay.id == first.id
    with pytest.raises(P3RepositoryConflict):
        _decide(
            db,
            parent,
            decision=ReuseReviewDecision.REJECTED,
            comments="Different final decision.",
        )
    with pytest.raises(P3RepositoryConflict):
        _decide(db, parent, key="second_review_key")
    assert (
        db.query(ReuseReview)
        .filter(ReuseReview.asset_version_id == parent.id)
        .count()
        == 1
    )


def test_review_failure_rolls_back_asset_state(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _seed_parent(db)
    submit_asset_for_review(db, asset_version_id=parent.id)
    real_commit = db.commit

    def fail_commit() -> None:
        raise IntegrityError("forced", {}, RuntimeError("forced"))

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(P3RepositoryConflict):
        _decide(db, parent, key="decision_rollback")
    monkeypatch.setattr(db, "commit", real_commit)
    db.rollback()
    db.refresh(parent)
    assert parent.status is ReuseAssetVersionStatus.PENDING_REVIEW
    assert (
        db.query(ReuseReview)
        .filter(ReuseReview.asset_version_id == parent.id)
        .count()
        == 0
    )


def test_review_list_filters_paginates_and_uses_fixed_queries(
    db: Session,
) -> None:
    project = _seed_project(db)
    for index, decision in enumerate(
        (
            ReuseReviewDecision.APPROVED,
            ReuseReviewDecision.REJECTED,
        ),
        start=1,
    ):
        parent = _seed_parent(
            db,
            project_id=project.id,
            source_id=f"list_source_{index}",
            parent_key=f"list_parent_{index}",
            asset_type=(
                ReuseAssetType.TRAINING_MATERIAL
                if index == 1
                else ReuseAssetType.SOP
            ),
        )
        submit_asset_for_review(db, asset_version_id=parent.id)
        _decide(
            db,
            parent,
            decision=decision,
            comments=(None if decision is ReuseReviewDecision.APPROVED else "No."),
            key=f"list_review_{index}",
        )
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", count_selects)
    try:
        page = list_project_reviews(
            db,
            project_id=project.id,
            limit=1,
            offset=0,
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", count_selects)
    assert page.total == 2
    assert len(page.items) == 1
    assert len(statements) == 2
    approved = list_project_reviews(
        db,
        project_id=project.id,
        decision=ReuseReviewDecision.APPROVED,
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
    )
    assert approved.total == 1
    with pytest.raises(P3RepositoryValidationError):
        list_project_reviews(db, project_id=project.id, offset=-1)


def test_repository_has_no_delete_provider_or_p1_p2_dependency() -> None:
    source = Path(repositories.__file__).read_text(encoding="utf-8")
    assert "delete_review" not in source
    assert "Provider" not in source
    assert "p3_source_eligibility" not in source
    assert "db_models" not in source
    assert "delete(" not in source


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_concurrent_revisions_and_decisions_are_atomic() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    admin_engine = create_engine(url, pool_pre_ping=True)
    schema = f"p3m52_{uuid.uuid4().hex[:12]}"
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        # ``public`` exposes the installed vector type; disabling checkfirst
        # prevents same-named public test tables from defeating schema isolation.
        Base.metadata.create_all(bind=engine, checkfirst=False)
        with SessionLocal() as seed:
            parent = _seed_parent(seed)
            parent_id = parent.id
            project_id = parent.project_id

        def create_child(index: int) -> tuple[str, int]:
            with SessionLocal() as session:
                row = create_manual_revision_with_snapshots(
                    session,
                    project_id=project_id,
                    parent_asset_version_id=parent_id,
                    content_payload=_manual_payload(f"Concurrent {index}"),
                    idempotency_key=f"pg_child_{index}",
                    created_by_role="cleaner",
                    request_id=f"pg_child_request_{index}",
                )
                return row.id, row.version_number

        with ThreadPoolExecutor(max_workers=2) as pool:
            children = list(pool.map(create_child, (1, 2)))
        assert {number for _row_id, number in children} == {2, 3}

        target_id = children[0][0]
        with SessionLocal() as session:
            submit_asset_for_review(session, asset_version_id=target_id)

        def decide(index: int) -> str:
            try:
                with SessionLocal() as session:
                    create_review_decision(
                        session,
                        asset_version_id=target_id,
                        decision=(
                            ReuseReviewDecision.APPROVED
                            if index == 1
                            else ReuseReviewDecision.REJECTED
                        ),
                        comments=(None if index == 1 else "Rejected."),
                        checklist_payload=_checklist(index == 1),
                        review_policy_version=P3_REVIEW_POLICY_VERSION,
                        reviewer_role="reviewer",
                        request_id=f"pg_decision_request_{index}",
                        idempotency_key=f"pg_decision_{index}",
                    )
                return "success"
            except P3RepositoryConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(decide, (1, 2)))
        assert sorted(outcomes) == ["conflict", "success"]
        with SessionLocal() as session:
            assert (
                session.query(func.count(ReuseReview.id))
                .filter(ReuseReview.asset_version_id == target_id)
                .scalar()
                == 1
            )
            assert session.get(ReuseAssetVersion, target_id).status in (
                ReuseAssetVersionStatus.APPROVED,
                ReuseAssetVersionStatus.REJECTED,
            )
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()
