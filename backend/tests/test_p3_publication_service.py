"""Focused P3-M6.2 governed publication Service tests."""

from __future__ import annotations

import copy
import inspect
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db_models as models  # noqa: E402
from app import p3_publication_service as service_module  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_asset_repositories import canonicalize_asset_content  # noqa: E402
from app.p3_asset_service import P3AssetService  # noqa: E402
from app.p3_publication_service import (  # noqa: E402
    P3PublicationService,
    P3PublicationServiceError,
)
from app.p3_review_service import P3ReviewService  # noqa: E402
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
ALL_TRUE = {
    "structure_complete": True,
    "source_refs_valid": True,
    "no_unsupported_claims_confirmed": True,
    "safe_for_reuse": True,
}


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
    candidate_id: str,
) -> models.KnowledgeCandidate:
    candidate = models.KnowledgeCandidate(
        id=candidate_id,
        source_type="sanitized_batch",
        source_id=f"batch_{candidate_id}",
        question=f"Question for {candidate_id}?",
        answer=f"Approved answer for {candidate_id}.",
        intent="customer_policy",
        tags=["governed", "publication"],
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
                "tags": ["governed", "publication"],
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
    suffix: str,
) -> tuple[ReuseProject, ReuseSourceItem]:
    candidate = _add_p1(db, candidate_id=f"m62_candidate_{suffix}")
    service = P3ReuseService(db)
    project = service.create_project(
        name=f"M6.2 publication {suffix}",
        description="Publication Service test",
        idempotency_key=f"m62_project_key_{suffix}",
        actor_role="cleaner",
        request_id=f"m62_project_request_{suffix}",
    )
    source = service.add_source_to_project(
        project_id=project.id,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=candidate.id,
        source_version=None,
        expected_fingerprint=None,
        actor_role="cleaner",
        request_id=f"m62_source_request_{suffix}",
    )
    project = service.activate_project(project.id)
    return project, source


def _generate(
    db: Session,
    project: ReuseProject,
    *,
    suffix: str,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
) -> ReuseAssetVersion:
    return P3AssetService(db).generate_draft_asset(
        project_id=project.id,
        asset_type=asset_type,
        template_key=None,
        idempotency_key=f"m62_generation_key_{suffix}",
        actor_role="cleaner",
        request_id=f"m62_generation_request_{suffix}",
    )


def _approve(
    db: Session,
    project: ReuseProject,
    asset: ReuseAssetVersion,
    *,
    suffix: str,
) -> ReuseReview:
    service = P3ReviewService(db)
    service.submit_for_review(
        project_id=project.id,
        asset_version_id=asset.id,
        idempotency_key=f"submit_{suffix}",
    )
    return service.decide_review(
        project_id=project.id,
        asset_version_id=asset.id,
        decision=ReuseReviewDecision.APPROVED,
        comments=None,
        checklist=dict(ALL_TRUE),
        idempotency_key=f"review_{suffix}",
        reviewer_role="reviewer",
        request_id=f"review_request_{suffix}",
    )


def _approved_asset(
    db: Session,
    *,
    suffix: str,
    mode: ReuseGenerationMode = ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
) -> tuple[
    ReuseProject,
    ReuseSourceItem,
    ReuseAssetVersion,
    ReuseReview,
]:
    project, source = _active_project(db, suffix=suffix)
    generated = _generate(
        db,
        project,
        suffix=suffix,
        asset_type=asset_type,
    )
    asset = generated
    if mode is ReuseGenerationMode.MANUAL_REVISION:
        payload = copy.deepcopy(generated.content_payload)
        payload["title"] = f"Manual revision {suffix}"
        asset = P3ReviewService(db).create_manual_revision(
            project_id=project.id,
            parent_asset_version_id=generated.id,
            content_payload=payload,
            idempotency_key=f"manual_{suffix}",
            actor_role="cleaner",
            request_id=f"manual_request_{suffix}",
        )
    elif mode is ReuseGenerationMode.LLM_DRAFT:
        generated.generation_mode = ReuseGenerationMode.LLM_DRAFT
        generated.template_key = f"p3.llm.test.{asset_type.value}.v1"
        db.commit()
    review = _approve(db, project, asset, suffix=suffix)
    return project, source, asset, review


def _publish(
    service: P3PublicationService,
    project: ReuseProject,
    asset: ReuseAssetVersion,
    *,
    key: str | None = None,
    actor_role: str = "admin",
):
    return service.publish_asset(
        project_id=project.id,
        asset_version_id=asset.id,
        idempotency_key=key or f"publish_{asset.id}",
        actor_role=actor_role,
        request_id=f"publish_request_{asset.id}",
    )


@pytest.mark.parametrize(
    "mode",
    [
        ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        ReuseGenerationMode.LLM_DRAFT,
        ReuseGenerationMode.MANUAL_REVISION,
    ],
)
def test_all_three_approved_generation_modes_publish(
    db: Session,
    mode: ReuseGenerationMode,
) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix=mode.value,
        mode=mode,
    )
    outcome = _publish(P3PublicationService(db), project, asset)
    assert outcome.asset.status is ReuseAssetVersionStatus.PUBLISHED
    assert outcome.asset.generation_mode is mode
    assert outcome.asset.published_by_role == "admin"
    assert outcome.asset.current_reuse_eligible is True


@pytest.mark.parametrize(
    "status",
    [
        ReuseAssetVersionStatus.GENERATED,
        ReuseAssetVersionStatus.PENDING_REVIEW,
        ReuseAssetVersionStatus.NEEDS_REVISION,
        ReuseAssetVersionStatus.REJECTED,
        ReuseAssetVersionStatus.FAILED,
    ],
)
def test_nonapproved_states_cannot_publish(
    db: Session,
    status: ReuseAssetVersionStatus,
) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix=f"state_{status.value}",
    )
    asset.status = status
    db.commit()
    with pytest.raises(P3PublicationServiceError) as caught:
        _publish(P3PublicationService(db), project, asset)
    assert caught.value.code == "P3_PUBLICATION_ASSET_STATE_INVALID"
    db.refresh(asset)
    assert asset.status is status


def test_review_missing_nonapproved_policy_and_checklist_are_rejected(
    db: Session,
) -> None:
    project, _source, asset, review = _approved_asset(
        db,
        suffix="review_gates",
    )
    db.delete(review)
    db.commit()
    with pytest.raises(P3PublicationServiceError) as missing:
        _publish(P3PublicationService(db), project, asset, key="missing")
    assert missing.value.code == "P3_PUBLICATION_REVIEW_MISSING"

    review = _approve_after_direct_reset(db, project, asset, "review_reseed")
    review.decision = ReuseReviewDecision.NEEDS_REVISION
    review.comments = "Not approved"
    db.commit()
    with pytest.raises(P3PublicationServiceError) as not_approved:
        _publish(P3PublicationService(db), project, asset, key="not_approved")
    assert not_approved.value.code == "P3_PUBLICATION_REVIEW_NOT_APPROVED"

    review.decision = ReuseReviewDecision.APPROVED
    review.comments = None
    review.review_policy_version = "p3-review-v0"
    db.commit()
    with pytest.raises(P3PublicationServiceError) as policy:
        _publish(P3PublicationService(db), project, asset, key="bad_policy")
    assert policy.value.code == "P3_PUBLICATION_REVIEW_NOT_APPROVED"

    review.review_policy_version = "p3-review-v1"
    review.checklist_payload = {
        **ALL_TRUE,
        "safe_for_reuse": False,
    }
    db.commit()
    with pytest.raises(P3PublicationServiceError) as checklist:
        _publish(P3PublicationService(db), project, asset, key="bad_checklist")
    assert checklist.value.code == "P3_PUBLICATION_REVIEW_NOT_APPROVED"


def _approve_after_direct_reset(
    db: Session,
    project: ReuseProject,
    asset: ReuseAssetVersion,
    suffix: str,
) -> ReuseReview:
    asset.status = ReuseAssetVersionStatus.GENERATED
    asset.approved_at = None
    db.commit()
    return _approve(db, project, asset, suffix=suffix)


def test_review_content_and_manifest_hash_drift_are_rejected(
    db: Session,
) -> None:
    project, _source, asset, review = _approved_asset(
        db,
        suffix="review_hash",
    )
    review.reviewed_content_hash = "0" * 64
    db.commit()
    with pytest.raises(P3PublicationServiceError) as content:
        _publish(P3PublicationService(db), project, asset, key="review_content")
    assert content.value.code == "P3_PUBLICATION_REVIEW_HASH_MISMATCH"
    review.reviewed_content_hash = asset.content_hash
    review.reviewed_source_manifest_hash = "1" * 64
    db.commit()
    with pytest.raises(P3PublicationServiceError) as manifest:
        _publish(P3PublicationService(db), project, asset, key="review_manifest")
    assert manifest.value.code == "P3_PUBLICATION_REVIEW_HASH_MISMATCH"


def test_payload_hash_and_snapshot_evidence_drift_are_rejected(
    db: Session,
) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix="payload_drift",
    )
    asset.content_payload = {
        **asset.content_payload,
        "title": "Tampered after approval",
    }
    db.commit()
    with pytest.raises(P3PublicationServiceError) as payload:
        _publish(P3PublicationService(db), project, asset, key="payload_drift")
    assert payload.value.code == "P3_PUBLICATION_CONTENT_HASH_MISMATCH"

    project2, _source2, asset2, _review2 = _approved_asset(
        db,
        suffix="snapshot_drift",
    )
    snapshot = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == asset2.id)
        .one()
    )
    snapshot.source_fingerprint = "f" * 64
    db.commit()
    with pytest.raises(P3PublicationServiceError) as snapshot_error:
        _publish(
            P3PublicationService(db),
            project2,
            asset2,
            key="snapshot_drift",
        )
    assert snapshot_error.value.code == (
        "P3_PUBLICATION_SOURCE_EVIDENCE_CHANGED"
    )


def test_grounding_and_stale_source_gates(db: Session) -> None:
    project, source, asset, review = _approved_asset(
        db,
        suffix="grounding",
    )
    payload = copy.deepcopy(asset.content_payload)
    sections = payload["sections"]
    assert isinstance(sections, list)
    assert isinstance(sections[0], dict)
    refs = sections[0]["source_refs"]
    assert isinstance(refs, list)
    assert isinstance(refs[0], dict)
    refs[0]["source_id"] = "forged"
    normalized, new_hash = canonicalize_asset_content(payload)
    asset.content_payload = normalized
    asset.content_hash = new_hash
    review.reviewed_content_hash = new_hash
    db.commit()
    with pytest.raises(P3PublicationServiceError) as grounding:
        _publish(P3PublicationService(db), project, asset, key="grounding")
    assert grounding.value.code == "P3_PUBLICATION_GROUNDING_INVALID"

    project2, source2, asset2, _review2 = _approved_asset(
        db,
        suffix="stale",
    )
    source2.source_stale = True
    db.commit()
    with pytest.raises(P3PublicationServiceError) as stale:
        _publish(P3PublicationService(db), project2, asset2, key="stale")
    assert stale.value.code == "P3_PUBLICATION_SOURCE_STALE"


def test_archived_project_and_nonadmin_roles_are_rejected(db: Session) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix="project_role",
    )
    project.status = ReuseProjectStatus.ARCHIVED
    project.archived_at = asset.created_at
    db.commit()
    with pytest.raises(P3PublicationServiceError) as archived:
        _publish(P3PublicationService(db), project, asset, key="archived_project")
    assert archived.value.code == "P3_PUBLICATION_PROJECT_NOT_ACTIVE"
    project.status = ReuseProjectStatus.ACTIVE
    project.archived_at = None
    db.commit()
    for role in ("cleaner", "reviewer", "viewer", "service"):
        with pytest.raises(P3PublicationServiceError) as forbidden:
            _publish(
                P3PublicationService(db),
                project,
                asset,
                key=f"forbidden_{role}",
                actor_role=role,
            )
        assert forbidden.value.code == "P3_PUBLICATION_ROLE_FORBIDDEN"


def test_second_version_supersedes_old_and_different_types_coexist(
    db: Session,
) -> None:
    project, _source, first, _review = _approved_asset(
        db,
        suffix="supersede",
    )
    service = P3PublicationService(db)
    _publish(service, project, first)
    second = _generate(db, project, suffix="supersede_v2")
    _approve(db, project, second, suffix="supersede_v2")
    outcome = _publish(service, project, second)
    db.refresh(first)
    assert first.status is ReuseAssetVersionStatus.SUPERSEDED
    assert first.superseded_by_asset_version_id == second.id
    assert outcome.superseded_asset_version_id == first.id
    assert service.list_current_published_assets(
        project_id=project.id
    ).total == 1

    sop = _generate(
        db,
        project,
        suffix="supersede_sop",
        asset_type=ReuseAssetType.SOP,
    )
    _approve(db, project, sop, suffix="supersede_sop")
    _publish(service, project, sop)
    page = service.list_current_published_assets(project_id=project.id)
    assert page.total == 2
    assert {item.asset_type for item in page.items} == {
        ReuseAssetType.TRAINING_MATERIAL,
        ReuseAssetType.SOP,
    }


def test_publish_idempotency_and_conflict(db: Session) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix="idempotency",
    )
    service = P3PublicationService(db)
    first = _publish(service, project, asset, key="publish_idempotent")
    replay = _publish(service, project, asset, key="publish_idempotent")
    assert replay.replayed is True
    assert replay.asset.published_at == first.asset.published_at

    project2, _source2, asset2, _review2 = _approved_asset(
        db,
        suffix="idempotency_other",
    )
    with pytest.raises(P3PublicationServiceError) as conflict:
        _publish(
            service,
            project2,
            asset2,
            key="publish_idempotent",
        )
    assert conflict.value.code == "P3_PUBLICATION_IDEMPOTENCY_CONFLICT"


def test_repository_failure_does_not_supersede_current(db: Session) -> None:
    project, _source, old, _review = _approved_asset(
        db,
        suffix="atomic",
    )
    service = P3PublicationService(db)
    _publish(service, project, old)
    new = _generate(db, project, suffix="atomic_new")
    _approve(db, project, new, suffix="atomic_new")
    with patch.object(
        service_module.publication_repositories,
        "publish_approved_asset",
        side_effect=P3RepositoryConflictForTest(),
    ):
        with pytest.raises(P3PublicationServiceError):
            _publish(service, project, new)
    db.refresh(old)
    db.refresh(new)
    assert old.status is ReuseAssetVersionStatus.PUBLISHED
    assert new.status is ReuseAssetVersionStatus.APPROVED


class P3RepositoryConflictForTest(
    service_module.P3RepositoryConflict
):
    pass


@pytest.mark.parametrize(
    "initial_state",
    [
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.PUBLISHED,
        ReuseAssetVersionStatus.SUPERSEDED,
    ],
)
def test_admin_archives_allowed_states_without_physical_delete(
    db: Session,
    initial_state: ReuseAssetVersionStatus,
) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix=f"archive_{initial_state.value}",
    )
    if initial_state is ReuseAssetVersionStatus.PUBLISHED:
        _publish(P3PublicationService(db), project, asset)
    elif initial_state is ReuseAssetVersionStatus.SUPERSEDED:
        asset.status = ReuseAssetVersionStatus.SUPERSEDED
        db.commit()
    outcome = P3PublicationService(db).archive_asset(
        project_id=project.id,
        asset_version_id=asset.id,
        idempotency_key=f"archive_{asset.id}",
        actor_role="admin",
        request_id=f"archive_request_{asset.id}",
    )
    assert outcome.asset.status is ReuseAssetVersionStatus.ARCHIVED
    assert db.get(ReuseAssetVersion, asset.id) is not None
    assert db.query(ReuseReview).filter_by(asset_version_id=asset.id).count() == 1


def test_archive_current_does_not_restore_and_is_idempotent(db: Session) -> None:
    project, _source, old, _review = _approved_asset(
        db,
        suffix="archive_current",
    )
    service = P3PublicationService(db)
    _publish(service, project, old)
    new = _generate(db, project, suffix="archive_current_new")
    _approve(db, project, new, suffix="archive_current_new")
    _publish(service, project, new)
    first = service.archive_asset(
        project_id=project.id,
        asset_version_id=new.id,
        idempotency_key="archive_current_key",
        actor_role="admin",
        request_id="archive_current_request",
    )
    replay = service.archive_asset(
        project_id=project.id,
        asset_version_id=new.id,
        idempotency_key="archive_current_key",
        actor_role="admin",
        request_id="archive_current_request",
    )
    assert replay.replayed is True
    assert replay.asset.archived_at == first.asset.archived_at
    db.refresh(old)
    assert old.status is ReuseAssetVersionStatus.SUPERSEDED
    with pytest.raises(P3PublicationServiceError):
        service.get_current_published_asset(
            project_id=project.id,
            asset_type=ReuseAssetType.TRAINING_MATERIAL,
        )
    with pytest.raises(P3PublicationServiceError) as republish:
        _publish(service, project, new, key="republish_archived")
    assert republish.value.code == "P3_PUBLICATION_ASSET_ARCHIVED"


def test_archive_role_state_and_idempotency_conflict(db: Session) -> None:
    project, _source, asset, _review = _approved_asset(
        db,
        suffix="archive_conflict",
    )
    service = P3PublicationService(db)
    with pytest.raises(P3PublicationServiceError) as role:
        service.archive_asset(
            project_id=project.id,
            asset_version_id=asset.id,
            idempotency_key="archive_role",
            actor_role="reviewer",
            request_id="archive_role_request",
        )
    assert role.value.code == "P3_PUBLICATION_ROLE_FORBIDDEN"
    asset.status = ReuseAssetVersionStatus.GENERATED
    db.commit()
    with pytest.raises(P3PublicationServiceError) as state:
        service.archive_asset(
            project_id=project.id,
            asset_version_id=asset.id,
            idempotency_key="archive_state",
            actor_role="admin",
            request_id="archive_state_request",
        )
    assert state.value.code == "P3_PUBLICATION_ASSET_STATE_INVALID"


def test_source_stale_after_publish_preserves_history(db: Session) -> None:
    project, source, asset, review = _approved_asset(
        db,
        suffix="history_stale",
    )
    service = P3PublicationService(db)
    published = _publish(service, project, asset)
    content_hash = published.asset.content_hash
    manifest_hash = published.asset.source_manifest_hash
    review_hash = review.reviewed_content_hash
    source.source_stale = True
    db.commit()
    current = service.get_current_published_asset(
        project_id=project.id,
        asset_type=asset.asset_type,
    )
    assert current.source_stale is True
    assert current.current_reuse_eligible is False
    db.refresh(asset)
    db.refresh(review)
    assert asset.status is ReuseAssetVersionStatus.PUBLISHED
    assert asset.content_hash == content_hash
    assert asset.source_manifest_hash == manifest_hash
    assert review.reviewed_content_hash == review_hash


def test_current_query_pagination_filter_and_no_per_asset_validation(
    db: Session,
) -> None:
    project, _source, training, _review = _approved_asset(
        db,
        suffix="query",
    )
    service = P3PublicationService(db)
    _publish(service, project, training)
    sop = _generate(
        db,
        project,
        suffix="query_sop",
        asset_type=ReuseAssetType.SOP,
    )
    _approve(db, project, sop, suffix="query_sop")
    _publish(service, project, sop)
    with patch.object(
        service,
        "_project_reuse_eligibility",
        wraps=service._project_reuse_eligibility,
    ) as eligibility:
        page = service.list_current_published_assets(
            project_id=project.id,
            limit=1,
            offset=0,
        )
        assert page.total == 2
        assert len(page.items) == 1
        assert eligibility.call_count == 1
    filtered = service.list_current_published_assets(
        project_id=project.id,
        asset_type=ReuseAssetType.SOP,
    )
    assert [item.asset_version_id for item in filtered.items] == [sop.id]


def test_service_boundary_excludes_provider_retrieval_export_and_sql() -> None:
    source = inspect.getsource(service_module)
    assert "provider" not in source.lower()
    assert "retrieval" not in source.lower()
    assert "export_jobs" not in source
    assert "export_artifacts" not in source
    assert "db_models" not in source
    assert "DELETE FROM" not in source.upper()
    assert "UPDATE reuse_" not in source


def test_errors_do_not_leak_secret_or_connection(db: Session) -> None:
    with pytest.raises(P3PublicationServiceError) as caught:
        P3PublicationService(db).publish_asset(
            project_id="missing",
            asset_version_id="missing",
            idempotency_key="safe",
            actor_role="admin",
            request_id="safe",
        )
    serialized = f"{caught.value} {caught.value.context}".lower()
    for forbidden in (
        "postgresql://",
        "sqlite://",
        "password",
        "bearer",
        "api_key",
        "traceback",
    ):
        assert forbidden not in serialized


def _clear_pg(session: Session, suffix: str) -> None:
    project = (
        session.query(ReuseProject)
        .filter(
            ReuseProject.idempotency_key
            == f"m62_project_key_{suffix}"
        )
        .first()
    )
    if project is not None:
        version_ids = [
            row[0]
            for row in session.query(ReuseAssetVersion.id)
            .filter(ReuseAssetVersion.project_id == project.id)
            .all()
        ]
        if version_ids:
            session.query(ReuseReview).filter(
                ReuseReview.asset_version_id.in_(version_ids)
            ).delete(synchronize_session=False)
            session.query(ReuseAssetVersionSource).filter(
                ReuseAssetVersionSource.asset_version_id.in_(version_ids)
            ).delete(synchronize_session=False)
            session.query(ReuseAssetVersion).filter(
                ReuseAssetVersion.id.in_(version_ids)
            ).update(
                {ReuseAssetVersion.superseded_by_asset_version_id: None},
                synchronize_session=False,
            )
            session.query(ReuseAssetVersion).filter(
                ReuseAssetVersion.id.in_(version_ids)
            ).delete(synchronize_session=False)
        session.query(ReuseSourceItem).filter(
            ReuseSourceItem.project_id == project.id
        ).delete(synchronize_session=False)
        session.delete(project)
    candidate_id = f"m62_candidate_{suffix}"
    session.query(models.ReviewRecord).filter(
        models.ReviewRecord.candidate_id == candidate_id
    ).delete(synchronize_session=False)
    session.query(models.KnowledgeCandidate).filter(
        models.KnowledgeCandidate.id == candidate_id
    ).delete(synchronize_session=False)
    session.commit()


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_service_concurrent_publish_archive_and_history() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    suffix = "p3m62_pg_main"
    try:
        with SessionLocal() as session:
            _clear_pg(session, suffix)
            project, source = _active_project(session, suffix=suffix)
            first = _generate(
                session,
                project,
                suffix="p3m62_pg_first",
            )
            _approve(session, project, first, suffix="p3m62_pg_first")
            second = _generate(
                session,
                project,
                suffix="p3m62_pg_second",
            )
            _approve(session, project, second, suffix="p3m62_pg_second")
            project_id = project.id
            source_id = source.id
            version_ids = (first.id, second.id)
        barrier = Barrier(2)

        def publish(version_id: str) -> str:
            with SessionLocal() as session:
                barrier.wait(timeout=10)
                return P3PublicationService(session).publish_asset(
                    project_id=project_id,
                    asset_version_id=version_id,
                    idempotency_key=f"publish_{version_id}",
                    actor_role="admin",
                    request_id=f"request_{version_id}",
                ).asset.asset_version_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert set(executor.map(publish, version_ids)) == set(version_ids)
        with SessionLocal() as session:
            rows = (
                session.query(ReuseAssetVersion)
                .filter(ReuseAssetVersion.project_id == project_id)
                .all()
            )
            current = [
                row
                for row in rows
                if row.status is ReuseAssetVersionStatus.PUBLISHED
            ]
            old = [
                row
                for row in rows
                if row.status is ReuseAssetVersionStatus.SUPERSEDED
            ]
            assert len(current) == len(old) == 1
            assert old[0].superseded_by_asset_version_id == current[0].id
            current_hash = current[0].content_hash
            review = (
                session.query(ReuseReview)
                .filter(ReuseReview.asset_version_id == current[0].id)
                .one()
            )
            review_hash = review.reviewed_content_hash
            source = session.get(ReuseSourceItem, source_id)
            source.source_stale = True
            session.commit()
            session.refresh(current[0])
            session.refresh(review)
            assert current[0].status is ReuseAssetVersionStatus.PUBLISHED
            assert current[0].content_hash == current_hash
            assert review.reviewed_content_hash == review_hash
            outcome = P3PublicationService(session).archive_asset(
                project_id=project_id,
                asset_version_id=current[0].id,
                idempotency_key="p3m62_pg_archive",
                actor_role="admin",
                request_id="p3m62_pg_archive_request",
            )
            assert outcome.asset.status is ReuseAssetVersionStatus.ARCHIVED
            assert (
                session.query(ReuseAssetVersion)
                .filter(
                    ReuseAssetVersion.project_id == project_id,
                    ReuseAssetVersion.status
                    == ReuseAssetVersionStatus.PUBLISHED,
                )
                .count()
                == 0
            )
    finally:
        with SessionLocal() as session:
            _clear_pg(session, suffix)
        engine.dispose()
