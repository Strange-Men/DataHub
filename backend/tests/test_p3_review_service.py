"""Focused P3-M5.3 manual-revision and human-review Service tests."""

from __future__ import annotations

import copy
import inspect
import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db_models as models  # noqa: E402
from app import p3_review_service as service_module  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_asset_service import P3AssetService  # noqa: E402
from app.p3_review_service import (  # noqa: E402
    P3ReviewService,
    P3ReviewServiceError,
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
from app.p3_reuse_service import P3ReuseService  # noqa: E402
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


def _add_p1(
    db: Session,
    *,
    candidate_id: str = "m53_candidate",
) -> models.KnowledgeCandidate:
    candidate = models.KnowledgeCandidate(
        id=candidate_id,
        source_type="sanitized_batch",
        source_id=f"batch_{candidate_id}",
        question=f"Question for {candidate_id}?",
        answer=f"Approved answer for {candidate_id}.",
        intent="customer_policy",
        tags=["governed", "policy"],
        risk_level="low",
        quality_score=0.95,
        status="approved",
        metadata_json={
            "knowledge_type": "faq",
            "source_batch_id": f"batch_{candidate_id}",
        },
    )
    db.add(candidate)
    db.add(
        models.ReviewRecord(
            id=f"review_{candidate_id}",
            candidate_id=candidate_id,
            reviewer="reviewer",
            action="approved",
            snapshot_json={
                "candidate_id": candidate_id,
                "source_type": "sanitized_batch",
                "question": candidate.question,
                "answer": candidate.answer,
                "intent": candidate.intent,
                "tags": ["governed", "policy"],
                "risk_level": candidate.risk_level,
                "knowledge_type": "faq",
                "source_batch_id": f"batch_{candidate_id}",
            },
        )
    )
    db.commit()
    return candidate


def _active_project(
    db: Session,
    *,
    suffix: str = "default",
) -> tuple[ReuseProject, ReuseSourceItem]:
    candidate = _add_p1(db, candidate_id=f"m53_candidate_{suffix}")
    service = P3ReuseService(db)
    project = service.create_project(
        name=f"M5.3 project {suffix}",
        description="Manual revision Service test",
        idempotency_key=f"m53_project_key_{suffix}",
        actor_role="cleaner",
        request_id=f"m53_project_request_{suffix}",
    )
    source = service.add_source_to_project(
        project_id=project.id,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=candidate.id,
        source_version=None,
        expected_fingerprint=None,
        actor_role="cleaner",
        request_id=f"m53_source_request_{suffix}",
    )
    project = service.activate_project(project.id)
    return project, source


def _generated(
    db: Session,
    *,
    suffix: str = "default",
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
) -> tuple[ReuseProject, ReuseSourceItem, ReuseAssetVersion]:
    project, source = _active_project(db, suffix=suffix)
    version = P3AssetService(db).generate_draft_asset(
        project_id=project.id,
        asset_type=asset_type,
        template_key=None,
        idempotency_key=f"m53_generation_key_{suffix}",
        actor_role="cleaner",
        request_id=f"m53_generation_request_{suffix}",
    )
    return project, source, version


def _revision_payload(
    parent: ReuseAssetVersion,
    *,
    title: str = "Human revised title",
) -> dict[str, object]:
    payload = copy.deepcopy(parent.content_payload)
    if parent.asset_type is ReuseAssetType.SFT_DATASET:
        records = payload["records"]
        assert isinstance(records, list)
        assert isinstance(records[0], dict)
        records[0]["output"] = title
    else:
        payload["title"] = title
    return payload


def _create_revision(
    service: P3ReviewService,
    project: ReuseProject,
    parent: ReuseAssetVersion,
    *,
    key: str = "m53_revision_key",
    title: str = "Human revised title",
) -> ReuseAssetVersion:
    return service.create_manual_revision(
        project_id=project.id,
        parent_asset_version_id=parent.id,
        content_payload=_revision_payload(parent, title=title),
        idempotency_key=key,
        actor_role="cleaner",
        request_id=f"request_{key}",
    )


def _checklist(all_true: bool = True) -> dict[str, object]:
    return {
        "structure_complete": all_true,
        "source_refs_valid": True,
        "no_unsupported_claims_confirmed": True,
        "safe_for_reuse": True,
    }


def _submit(
    service: P3ReviewService,
    project: ReuseProject,
    asset: ReuseAssetVersion,
) -> ReuseAssetVersion:
    return service.submit_for_review(
        project_id=project.id,
        asset_version_id=asset.id,
        idempotency_key=f"submit_{asset.id}",
    )


def _decide(
    service: P3ReviewService,
    project: ReuseProject,
    asset: ReuseAssetVersion,
    *,
    decision: ReuseReviewDecision = ReuseReviewDecision.APPROVED,
    key: str = "m53_review_key",
    comments: str | None = None,
) -> ReuseReview:
    if comments is None and decision is not ReuseReviewDecision.APPROVED:
        comments = "Human reviewer supplied required comments."
    return service.decide_review(
        project_id=project.id,
        asset_version_id=asset.id,
        decision=decision,
        comments=comments,
        checklist=_checklist(
            decision is ReuseReviewDecision.APPROVED
        ),
        idempotency_key=key,
        reviewer_role="reviewer",
        request_id=f"request_{key}",
    )


def test_generated_parent_creates_new_manual_revision_without_overwrite(
    db: Session,
) -> None:
    project, _source, parent = _generated(db)
    parent_payload = copy.deepcopy(parent.content_payload)
    parent_hash = parent.content_hash
    child = _create_revision(P3ReviewService(db), project, parent)
    db.refresh(parent)
    assert child.generation_mode is ReuseGenerationMode.MANUAL_REVISION
    assert child.status is ReuseAssetVersionStatus.GENERATED
    assert child.parent_asset_version_id == parent.id
    assert child.asset_type is parent.asset_type
    assert child.id != parent.id
    assert parent.content_payload == parent_payload
    assert parent.content_hash == parent_hash
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
    assert (
        child_sources[0].source_trace_snapshot
        == parent_sources[0].source_trace_snapshot
    )


def test_needs_revision_parent_can_create_new_revision(db: Session) -> None:
    project, _source, parent = _generated(db)
    service = P3ReviewService(db)
    _submit(service, project, parent)
    _decide(
        service,
        project,
        parent,
        decision=ReuseReviewDecision.NEEDS_REVISION,
        comments="Revise the wording.",
    )
    child = _create_revision(
        service,
        project,
        parent,
        key="needs_revision_child",
    )
    db.refresh(parent)
    assert parent.status is ReuseAssetVersionStatus.NEEDS_REVISION
    assert child.status is ReuseAssetVersionStatus.GENERATED
    assert child.parent_asset_version_id == parent.id
    assert db.query(ReuseReview).filter_by(asset_version_id=parent.id).count() == 1


@pytest.mark.parametrize(
    "status",
    (
        ReuseAssetVersionStatus.GENERATING,
        ReuseAssetVersionStatus.FAILED,
        ReuseAssetVersionStatus.PENDING_REVIEW,
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.REJECTED,
        ReuseAssetVersionStatus.PUBLISHED,
        ReuseAssetVersionStatus.SUPERSEDED,
        ReuseAssetVersionStatus.ARCHIVED,
    ),
)
def test_forbidden_parent_states_cannot_be_revised(
    db: Session,
    status: ReuseAssetVersionStatus,
) -> None:
    project, _source, parent = _generated(db, suffix=status.value)
    parent.status = status
    db.commit()
    with pytest.raises(P3ReviewServiceError) as captured:
        _create_revision(
            P3ReviewService(db),
            project,
            parent,
            key=f"revision_{status.value}",
        )
    assert captured.value.code == "P3_REVIEW_PARENT_STATE_INVALID"


@pytest.mark.parametrize(
    "project_status",
    (ReuseProjectStatus.DRAFT, ReuseProjectStatus.ARCHIVED),
)
def test_nonactive_project_rejects_revision(
    db: Session,
    project_status: ReuseProjectStatus,
) -> None:
    project, _source, parent = _generated(
        db,
        suffix=project_status.value,
    )
    project.status = project_status
    db.commit()
    with pytest.raises(P3ReviewServiceError) as captured:
        _create_revision(
            P3ReviewService(db),
            project,
            parent,
            key=f"project_{project_status.value}",
        )
    assert captured.value.code == "P3_REVIEW_PROJECT_NOT_ACTIVE"


def test_revision_rejects_stale_and_changed_source_evidence(
    db: Session,
) -> None:
    project, source, parent = _generated(db)
    service = P3ReviewService(db)
    source.source_stale = True
    db.commit()
    with pytest.raises(P3ReviewServiceError) as stale:
        _create_revision(service, project, parent, key="stale_revision")
    assert stale.value.code == "P3_REVIEW_SOURCE_STALE"

    source.source_stale = False
    snapshot = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == parent.id)
        .one()
    )
    snapshot.source_fingerprint = "f" * 64
    db.commit()
    with pytest.raises(P3ReviewServiceError) as changed:
        _create_revision(service, project, parent, key="changed_revision")
    assert changed.value.code == "P3_REVIEW_SOURCE_EVIDENCE_CHANGED"


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("unknown_ref", "P3_REVIEW_SOURCE_REF_INVALID"),
        ("missing_refs", "P3_REVIEW_GROUNDING_INCOMPLETE"),
        ("invalid_schema", "P3_REVIEW_CONTENT_INVALID"),
    ),
)
def test_revision_content_schema_and_grounding_gates(
    db: Session,
    mutation: str,
    code: str,
) -> None:
    project, _source, parent = _generated(db, suffix=mutation)
    payload = _revision_payload(parent)
    if mutation == "unknown_ref":
        sections = payload["sections"]
        assert isinstance(sections, list)
        assert isinstance(sections[0], dict)
        refs = sections[0]["source_refs"]
        assert isinstance(refs, list)
        assert isinstance(refs[0], dict)
        refs[0]["source_id"] = "forged"
    elif mutation == "missing_refs":
        sections = payload["sections"]
        assert isinstance(sections, list)
        assert isinstance(sections[0], dict)
        sections[0]["source_refs"] = []
    else:
        payload.pop("title")
    with pytest.raises(P3ReviewServiceError) as captured:
        P3ReviewService(db).create_manual_revision(
            project_id=project.id,
            parent_asset_version_id=parent.id,
            content_payload=payload,
            idempotency_key=f"invalid_{mutation}",
            actor_role="cleaner",
            request_id=f"request_{mutation}",
        )
    assert captured.value.code == code


def test_revision_idempotency_and_conflict(db: Session) -> None:
    project, _source, parent = _generated(db)
    service = P3ReviewService(db)
    first = _create_revision(service, project, parent)
    replay = _create_revision(service, project, parent)
    assert replay.id == first.id
    with pytest.raises(P3ReviewServiceError) as captured:
        _create_revision(service, project, parent, title="Different")
    assert captured.value.code == "P3_REVIEW_IDEMPOTENCY_CONFLICT"


def test_submit_validates_content_hash_manifest_and_sources(
    db: Session,
) -> None:
    project, source, asset = _generated(db)
    service = P3ReviewService(db)
    original_hash = asset.content_hash
    submitted = _submit(service, project, asset)
    assert submitted.status is ReuseAssetVersionStatus.PENDING_REVIEW
    assert submitted.content_hash == original_hash
    assert _submit(service, project, asset).id == asset.id
    assert db.query(ReuseReview).count() == 0

    project2, _source2, hash_asset = _generated(db, suffix="hash")
    hash_asset.content_payload = {
        **hash_asset.content_payload,
        "title": "Tampered",
    }
    db.commit()
    with pytest.raises(P3ReviewServiceError) as hash_error:
        _submit(P3ReviewService(db), project2, hash_asset)
    assert hash_error.value.code == "P3_REVIEW_CONTENT_HASH_MISMATCH"
    db.refresh(hash_asset)
    assert hash_asset.status is ReuseAssetVersionStatus.GENERATED

    project3, _source3, manifest_asset = _generated(db, suffix="manifest")
    manifest_asset.source_manifest_hash = "0" * 64
    db.commit()
    with pytest.raises(P3ReviewServiceError) as manifest_error:
        _submit(P3ReviewService(db), project3, manifest_asset)
    assert manifest_error.value.code == "P3_REVIEW_SOURCE_EVIDENCE_CHANGED"
    db.refresh(manifest_asset)
    assert manifest_asset.status is ReuseAssetVersionStatus.GENERATED

    project4, stale_source, stale_asset = _generated(db, suffix="stale")
    stale_source.source_stale = True
    db.commit()
    with pytest.raises(P3ReviewServiceError) as stale_error:
        _submit(P3ReviewService(db), project4, stale_asset)
    assert stale_error.value.code == "P3_REVIEW_SOURCE_STALE"
    db.refresh(stale_asset)
    assert stale_asset.status is ReuseAssetVersionStatus.GENERATED


@pytest.mark.parametrize(
    "status",
    (
        ReuseAssetVersionStatus.FAILED,
        ReuseAssetVersionStatus.NEEDS_REVISION,
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.REJECTED,
    ),
)
def test_submit_rejects_invalid_asset_states(
    db: Session,
    status: ReuseAssetVersionStatus,
) -> None:
    project, _source, asset = _generated(db, suffix=f"submit_{status.value}")
    asset.status = status
    db.commit()
    with pytest.raises(P3ReviewServiceError) as captured:
        _submit(P3ReviewService(db), project, asset)
    assert captured.value.code == "P3_REVIEW_ASSET_STATE_INVALID"


@pytest.mark.parametrize("decision", list(ReuseReviewDecision))
def test_human_decisions_preserve_review_hash_and_never_publish(
    db: Session,
    decision: ReuseReviewDecision,
) -> None:
    project, _source, asset = _generated(db, suffix=decision.value)
    service = P3ReviewService(db)
    _submit(service, project, asset)
    review = _decide(
        service,
        project,
        asset,
        decision=decision,
        key=f"decision_{decision.value}",
    )
    db.refresh(asset)
    assert asset.status.value == decision.value
    assert asset.status is not ReuseAssetVersionStatus.PUBLISHED
    assert asset.published_at is None
    assert review.reviewed_content_hash == asset.content_hash
    assert review.reviewed_source_manifest_hash == asset.source_manifest_hash
    assert (asset.approved_at is not None) is (
        decision is ReuseReviewDecision.APPROVED
    )


def test_review_policy_comments_and_checklist_are_enforced(
    db: Session,
) -> None:
    project, _source, asset = _generated(db)
    service = P3ReviewService(db)
    _submit(service, project, asset)
    with pytest.raises(P3ReviewServiceError) as checklist:
        service.decide_review(
            project_id=project.id,
            asset_version_id=asset.id,
            decision=ReuseReviewDecision.APPROVED,
            comments=None,
            checklist=_checklist(False),
            idempotency_key="bad_checklist",
            reviewer_role="reviewer",
            request_id="bad_checklist_request",
        )
    assert checklist.value.code == "P3_REVIEW_CHECKLIST_INVALID"
    with pytest.raises(P3ReviewServiceError) as comments:
        service.decide_review(
            project_id=project.id,
            asset_version_id=asset.id,
            decision=ReuseReviewDecision.REJECTED,
            comments=None,
            checklist=_checklist(False),
            idempotency_key="missing_comments",
            reviewer_role="reviewer",
            request_id="missing_comments_request",
        )
    assert comments.value.code == "P3_REVIEW_COMMENTS_REQUIRED"
    db.refresh(asset)
    assert asset.status is ReuseAssetVersionStatus.PENDING_REVIEW
    assert db.query(ReuseReview).count() == 0


def test_decision_revalidates_source_and_evidence(db: Session) -> None:
    project, source, asset = _generated(db)
    service = P3ReviewService(db)
    _submit(service, project, asset)
    source.source_stale = True
    db.commit()
    with pytest.raises(P3ReviewServiceError) as stale:
        _decide(service, project, asset, key="stale_decision")
    assert stale.value.code == "P3_REVIEW_SOURCE_STALE"
    db.refresh(asset)
    assert asset.status is ReuseAssetVersionStatus.PENDING_REVIEW

    source.source_stale = False
    snapshot = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == asset.id)
        .one()
    )
    snapshot.lineage_manifest_hash = "f" * 64
    db.commit()
    with pytest.raises(P3ReviewServiceError) as changed:
        _decide(service, project, asset, key="changed_decision")
    assert changed.value.code == "P3_REVIEW_SOURCE_EVIDENCE_CHANGED"
    db.refresh(asset)
    assert asset.status is ReuseAssetVersionStatus.PENDING_REVIEW


def test_review_idempotency_second_decision_and_rejected_terminal(
    db: Session,
) -> None:
    project, _source, asset = _generated(db)
    service = P3ReviewService(db)
    _submit(service, project, asset)
    first = _decide(
        service,
        project,
        asset,
        decision=ReuseReviewDecision.REJECTED,
        comments="Final rejection.",
    )
    replay = _decide(
        service,
        project,
        asset,
        decision=ReuseReviewDecision.REJECTED,
        comments="Final rejection.",
    )
    assert replay.id == first.id
    with pytest.raises(P3ReviewServiceError) as conflict:
        _decide(
            service,
            project,
            asset,
            decision=ReuseReviewDecision.APPROVED,
        )
    assert conflict.value.code == "P3_REVIEW_IDEMPOTENCY_CONFLICT"
    with pytest.raises(P3ReviewServiceError) as second:
        service.decide_review(
            project_id=project.id,
            asset_version_id=asset.id,
            decision=ReuseReviewDecision.REJECTED,
            comments="Another review.",
            checklist=_checklist(False),
            idempotency_key="second_decision",
            reviewer_role="reviewer",
            request_id="second_decision_request",
        )
    assert second.value.code == "P3_REVIEW_ALREADY_DECIDED"
    assert (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.parent_asset_version_id == asset.id)
        .count()
        == 0
    )


def test_review_error_is_safe_and_service_has_no_provider_or_sql() -> None:
    error = P3ReviewServiceError(
        "P3_REVIEW_STORAGE_UNAVAILABLE",
        "Safe failure.",
        {"asset_version_id": "asset_1"},
    )
    rendered = f"{error!r} {error}"
    assert "postgresql://" not in rendered
    assert "Bearer " not in rendered
    source = Path(service_module.__file__).read_text(encoding="utf-8")
    assert "OpenAICompatible" not in source
    assert "generate_structured_draft" not in source
    assert "db_models" not in source
    assert "text(" not in source
    assert ".execute(" not in source


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_service_decision_is_atomic() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    admin_engine = create_engine(url, pool_pre_ping=True)
    schema = f"p3m53_{uuid.uuid4().hex[:12]}"
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
        with SessionLocal() as session:
            project, _source, asset = _generated(session, suffix="pg")
            service = P3ReviewService(session)
            _submit(service, project, asset)
            review = _decide(service, project, asset)
            session.refresh(asset)
            assert review.reviewed_content_hash == asset.content_hash
            assert asset.status is ReuseAssetVersionStatus.APPROVED
            assert asset.approved_at is not None
            assert asset.published_at is None
            assert session.query(ReuseReview).count() == 1
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()
