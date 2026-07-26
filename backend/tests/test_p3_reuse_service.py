"""Focused P3-M2.3 tests for project/source Service orchestration."""

from __future__ import annotations

import inspect
import os
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from app import p3_reuse_repositories as repositories  # noqa: E402
from app import p3_reuse_service as service_module  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import P3RepositoryPage  # noqa: E402
from app.p3_reuse_schemas import P3SourceRevalidationStatus  # noqa: E402
from app.p3_reuse_service import (  # noqa: E402
    MAX_PROJECT_REVALIDATION_SOURCES,
    P3ProjectStateError,
    P3ReuseService,
    P3ServiceConflict,
    P3ServiceNotFound,
    P3ServiceValidationError,
    P3SourceIneligible,
    P3SourceStale,
)
from app.p3_source_eligibility_schemas import (  # noqa: E402
    P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
    P3SourceEligibilityDecision,
    P3SourceEligibilityReason,
    P3SourceType,
)
from scripts.test_environment import require_test_database_url  # noqa: E402


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
P3_TABLES = {
    "reuse_projects",
    "reuse_source_items",
    "reuse_asset_versions",
    "reuse_asset_version_sources",
}
FORBIDDEN_FUTURE_TABLES = {
    "reuse_reviews",
    "export_jobs",
    "export_artifacts",
}


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
    cleanup_models = (
        ReuseSourceItem,
        ReuseProject,
        models.P2KnowledgeIndexEntry,
        models.KnowledgeAsset,
        models.AssetReviewSnapshot,
        models.ExtractionReview,
        models.AssetExtraction,
        models.ExtractionJob,
        models.Asset,
        models.ReviewRecord,
        models.KnowledgeCandidate,
        models.BadCase,
    )
    with SessionLocal() as session:
        for model in cleanup_models:
            session.query(model).delete()
        session.commit()
        yield session
        session.rollback()
        for model in cleanup_models:
            session.query(model).delete()
        session.commit()


@pytest.fixture
def service(db: Session) -> P3ReuseService:
    return P3ReuseService(db)


def _create_project(
    service: P3ReuseService,
    *,
    name: str = "客服培训复用",
    description: str | None = "Service test",
    idempotency_key: str = "service-project-key-1",
    request_id: str = "service-project-request-1",
) -> ReuseProject:
    return service.create_project(
        name=name,
        description=description,
        idempotency_key=idempotency_key,
        actor_role="cleaner",
        request_id=request_id,
    )


def _add_p1(
    db: Session,
    *,
    candidate_id: str = "candidate_p1",
    status: str = "approved",
    source_type: str = "sanitized_batch",
    include_review: bool = True,
    include_snapshot: bool = True,
    trace_complete: bool = True,
) -> models.KnowledgeCandidate:
    metadata = {
        "source_batch_id": "batch_p1" if source_type != "bad_case" else None,
        "source_bad_case_id": "bad_case_p1" if source_type == "bad_case" else None,
        "knowledge_type": "faq",
    }
    candidate = models.KnowledgeCandidate(
        id=candidate_id,
        source_type=source_type,
        source_id=(
            "bad_case_p1" if source_type == "bad_case" else "batch_p1"
        ),
        question="How long does shipping take?",
        answer="Shipping takes five business days.",
        intent="shipping",
        tags=["shipping", "policy"],
        risk_level="low",
        quality_score=0.95,
        status=status,
        metadata_json=metadata,
    )
    db.add(candidate)
    if include_review:
        snapshot = None
        if include_snapshot:
            snapshot = {
                "candidate_id": candidate_id,
                "source_type": source_type,
                "source_batch_id": (
                    "batch_p1"
                    if trace_complete and source_type != "bad_case"
                    else None
                ),
                "source_bad_case_id": (
                    "bad_case_p1"
                    if trace_complete and source_type == "bad_case"
                    else None
                ),
                "question": "How long does shipping take?",
                "answer": "Shipping takes five business days.",
                "intent": "shipping",
                "tags": ["policy", "shipping"],
                "risk_level": "low",
                "knowledge_type": "faq",
            }
        db.add(
            models.ReviewRecord(
                id=f"review_{candidate_id}",
                candidate_id=candidate_id,
                reviewer="reviewer",
                action="approved",
                snapshot_json=snapshot,
            )
        )
    if source_type == "bad_case":
        db.add(
            models.BadCase(
                id="bad_case_p1",
                retrieval_id="retrieval_p1",
                user_question="Original question",
                bad_answer="Incorrect answer",
                expected_answer="Corrected answer",
                status="resolved",
                created_candidate_id=candidate_id,
                metadata_json={},
            )
        )
    db.commit()
    return candidate


def _add_p2(
    db: Session,
    *,
    suffix: str = "v1",
    status: str = "active",
    index_status: str | None = None,
    include_snapshot: bool = True,
    version: int = 1,
) -> models.KnowledgeAsset:
    asset_id = f"asset_{suffix}"
    extraction_id = f"extraction_{suffix}"
    review_id = f"review_{suffix}"
    snapshot_id = f"snapshot_{suffix}"
    knowledge_asset_id = f"knowledge_{suffix}"
    db.add(
        models.Asset(
            id=asset_id,
            asset_type="image",
            file_name=f"{suffix}.png",
            mime_type="image/png",
            size=8,
            storage_uri=f"test://{suffix}.png",
            hash=(suffix.encode("utf-8").hex() + "a" * 64)[:64],
            status="uploaded",
            metadata_json={},
        )
    )
    db.add(
        models.ExtractionJob(
            id=f"job_{suffix}",
            asset_id=asset_id,
            extract_type="ocr",
            provider="mock",
            status="success",
        )
    )
    db.add(
        models.AssetExtraction(
            id=extraction_id,
            asset_id=asset_id,
            job_id=f"job_{suffix}",
            extract_type="ocr",
            content="Machine content.",
            version=version,
        )
    )
    db.add(
        models.ExtractionReview(
            id=review_id,
            asset_id=asset_id,
            extraction_id=extraction_id,
            review_status="approved",
            reviewer="reviewer",
            original_content="Machine content.",
            revised_content="Approved governed content.",
            version=version,
        )
    )
    if include_snapshot:
        db.add(
            models.AssetReviewSnapshot(
                id=snapshot_id,
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_id=review_id,
                extract_type="ocr",
                original_content="Machine content.",
                approved_content="Approved governed content.",
                version=version,
            )
        )
    knowledge = models.KnowledgeAsset(
        id=knowledge_asset_id,
        source_snapshot_id=snapshot_id,
        asset_id=asset_id,
        content="Approved governed content.",
        content_type="ocr",
        status=status,
        version=version,
        metadata_json={},
    )
    db.add(knowledge)
    if index_status is not None:
        db.add(
            models.P2KnowledgeIndexEntry(
                id=f"index_{suffix}",
                knowledge_asset_id=knowledge_asset_id,
                status=index_status,
                generation=1,
                fingerprint=(f"index-{suffix}" + "0" * 64)[:64],
                sync_state=index_status,
            )
        )
    db.commit()
    return knowledge


def _add_source(
    service: P3ReuseService,
    project: ReuseProject,
    *,
    source_type: P3SourceType | str = P3SourceType.P1_KNOWLEDGE,
    source_id: str = "candidate_p1",
    source_version: int | None = None,
    expected_fingerprint: str | None = None,
    request_id: str = "service-source-request-1",
) -> ReuseSourceItem:
    return service.add_source_to_project(
        project_id=project.id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        expected_fingerprint=expected_fingerprint,
        actor_role="cleaner",
        request_id=request_id,
    )


def _decision_for_item(
    item: ReuseSourceItem,
    **updates: object,
) -> P3SourceEligibilityDecision:
    values: dict[str, object] = {
        "source_type": item.source_type.value,
        "source_id": item.source_id,
        "eligible": True,
        "reason_code": P3SourceEligibilityReason.ELIGIBLE,
        "source_status": "active",
        "source_version": item.source_version,
        "content_fingerprint": item.source_fingerprint,
        "approved_review_id": item.approved_review_id,
        "snapshot_id": item.snapshot_id,
        "knowledge_asset_id": item.knowledge_asset_id,
        "lineage_complete": True,
        "checked_conditions": ["SOURCE_TRACE_COMPLETE"],
        "policy_version": item.eligibility_policy_version,
    }
    values.update(updates)
    return P3SourceEligibilityDecision.model_validate(values)


def test_create_project_is_always_draft(service: P3ReuseService) -> None:
    project = _create_project(service)
    assert project.status is ReuseProjectStatus.DRAFT
    assert project.created_by_role == "cleaner"


def test_create_project_idempotency_and_conflict(service: P3ReuseService) -> None:
    first = _create_project(service)
    replay = _create_project(service, request_id="retry-request")
    assert replay.id == first.id
    with pytest.raises(P3ServiceConflict) as caught:
        _create_project(service, name="Different name")
    assert caught.value.code == "P3_CONFLICT"


def test_draft_project_can_update_metadata(service: P3ReuseService) -> None:
    project = _create_project(service)
    updated = service.update_project_metadata(
        project.id,
        name="更新后的项目",
        description=None,
    )
    assert updated.name == "更新后的项目"
    assert updated.description is None


def test_active_project_cannot_update_metadata(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    _add_source(service, project)
    service.activate_project(project.id)
    with pytest.raises(P3ProjectStateError):
        service.update_project_metadata(project.id, name="forbidden")


def test_archived_project_cannot_update_or_reactivate(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    _add_source(service, project)
    service.activate_project(project.id)
    archived = service.archive_project(project.id)
    assert archived.status is ReuseProjectStatus.ARCHIVED
    with pytest.raises(P3ProjectStateError):
        service.update_project_metadata(project.id, name="forbidden")
    with pytest.raises(P3ProjectStateError):
        service.activate_project(project.id)


def test_illegal_project_transitions_are_not_exposed(
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    with pytest.raises(P3ProjectStateError):
        service.archive_project(project.id)
    assert not hasattr(service, "set_project_status")
    assert service.get_project(project.id).status is ReuseProjectStatus.DRAFT


def test_project_without_sources_cannot_activate(service: P3ReuseService) -> None:
    project = _create_project(service)
    with pytest.raises(P3ProjectStateError, match="at least one"):
        service.activate_project(project.id)
    assert service.get_project(project.id).status is ReuseProjectStatus.DRAFT


def test_add_eligible_p1_uses_m1_evidence(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    assert source.source_type is P3SourceType.P1_KNOWLEDGE
    assert source.approved_review_id == "review_candidate_p1"
    assert len(source.source_fingerprint) == 64
    assert source.source_trace["source_id"] == "candidate_p1"
    assert source.source_trace["eligibility_policy_version"] == (
        P3_SOURCE_ELIGIBILITY_POLICY_VERSION
    )
    assert source.lineage_manifest_hash is not None


def test_add_eligible_p2_saves_complete_decision_evidence(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    knowledge = _add_p2(db)
    source = _add_source(
        service,
        project,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id=knowledge.id,
    )
    assert source.source_version == 1
    assert source.approved_review_id == "review_v1"
    assert source.snapshot_id == "snapshot_v1"
    assert source.knowledge_asset_id == knowledge.id
    assert source.source_trace["lineage_complete"] is True


def test_ready_not_serving_p2_can_be_added(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    knowledge = _add_p2(db, index_status="ready")
    source = _add_source(
        service,
        project,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id=knowledge.id,
    )
    assert "INDEX_STATUS_OBSERVED:ready" in source.source_trace["checked_conditions"]


def test_approved_bad_case_correction_can_be_added(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db, source_type="bad_case")
    source = _add_source(
        service,
        project,
        source_type=P3SourceType.APPROVED_BAD_CASE_CORRECTION,
    )
    assert source.source_type is P3SourceType.APPROVED_BAD_CASE_CORRECTION


@pytest.mark.parametrize(
    ("source_type", "source_factory", "reason_code"),
    [
        (
            "RAW_BAD_CASE",
            None,
            P3SourceEligibilityReason.RAW_BAD_CASE_NOT_ALLOWED,
        ),
        (
            P3SourceType.P1_KNOWLEDGE,
            lambda db: _add_p1(db, status="pending_review"),
            P3SourceEligibilityReason.SOURCE_NOT_APPROVED,
        ),
        (
            P3SourceType.P2_KNOWLEDGE_ASSET,
            lambda db: _add_p2(db, status="archived"),
            P3SourceEligibilityReason.SOURCE_ARCHIVED,
        ),
        (
            P3SourceType.P2_KNOWLEDGE_ASSET,
            lambda db: _add_p2(db, include_snapshot=False),
            P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
        ),
    ],
)
def test_ineligible_sources_are_rejected_with_stable_reason(
    db: Session,
    service: P3ReuseService,
    source_type,
    source_factory,
    reason_code: P3SourceEligibilityReason,
) -> None:
    project = _create_project(service)
    source = source_factory(db) if source_factory is not None else None
    source_id = source.id if source is not None else "bad_case_raw"
    with pytest.raises(P3SourceIneligible) as caught:
        _add_source(
            service,
            project,
            source_type=source_type,
            source_id=source_id,
        )
    assert caught.value.reason_code is reason_code
    assert db.query(ReuseSourceItem).count() == 0


def test_fingerprint_drift_is_rejected_before_persistence(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    candidate.answer = "Drifted answer"
    db.commit()
    with pytest.raises(P3SourceIneligible) as caught:
        _add_source(service, project)
    assert caught.value.reason_code is (
        P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH
    )


def test_add_request_cannot_supply_governance_evidence(
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    with pytest.raises(TypeError):
        service.add_source_to_project(
            project_id=project.id,
            source_type=P3SourceType.P1_KNOWLEDGE,
            source_id="candidate_p1",
            source_version=None,
            expected_fingerprint=None,
            actor_role="cleaner",
            request_id="request",
            approved=True,
        )


def test_same_evidence_is_idempotent_and_changed_review_conflicts(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    first = _add_source(service, project)
    replay = _add_source(
        service,
        project,
        request_id="service-source-request-retry",
    )
    assert replay.id == first.id
    old_review = db.get(models.ReviewRecord, "review_candidate_p1")
    db.add(
        models.ReviewRecord(
            id="review_candidate_p1_new",
            candidate_id=candidate.id,
            reviewer="reviewer",
            action="approved",
            snapshot_json=dict(old_review.snapshot_json),
            created_at=old_review.created_at + timedelta(seconds=1),
        )
    )
    db.commit()
    with pytest.raises(P3ServiceConflict):
        _add_source(service, project)
    assert db.query(ReuseSourceItem).count() == 1


@pytest.mark.parametrize("target_status", [ReuseProjectStatus.ACTIVE, ReuseProjectStatus.ARCHIVED])
def test_active_and_archived_projects_reject_new_sources(
    db: Session,
    service: P3ReuseService,
    target_status: ReuseProjectStatus,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    _add_source(service, project)
    service.activate_project(project.id)
    if target_status is ReuseProjectStatus.ARCHIVED:
        service.archive_project(project.id)
    with pytest.raises(P3ProjectStateError):
        _add_source(service, project, source_id="candidate_other")


def test_draft_source_remove_is_logical_and_idempotent(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    first = service.remove_source_from_project(
        project_id=project.id,
        source_item_id=source.id,
    )
    second = service.remove_source_from_project(
        project_id=project.id,
        source_item_id=source.id,
    )
    assert first.removed_at is not None
    assert second.removed_at == first.removed_at
    assert db.get(ReuseSourceItem, source.id) is not None


@pytest.mark.parametrize("target_status", [ReuseProjectStatus.ACTIVE, ReuseProjectStatus.ARCHIVED])
def test_active_and_archived_projects_reject_source_removal(
    db: Session,
    service: P3ReuseService,
    target_status: ReuseProjectStatus,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    service.activate_project(project.id)
    if target_status is ReuseProjectStatus.ARCHIVED:
        service.archive_project(project.id)
    with pytest.raises(P3ProjectStateError):
        service.remove_source_from_project(
            project_id=project.id,
            source_item_id=source.id,
        )


def test_logically_removed_source_cannot_be_readded(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    service.remove_source_from_project(
        project_id=project.id,
        source_item_id=source.id,
    )
    candidate = db.get(models.KnowledgeCandidate, "candidate_p1")
    candidate.status = "archived"
    db.commit()
    with pytest.raises(P3ServiceConflict, match="cannot be restored"):
        _add_source(service, project)


def test_revalidate_valid_source_keeps_original_evidence(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    original_trace = dict(source.source_trace)
    result = service.revalidate_source_item(
        project_id=project.id,
        source_item_id=source.id,
    )
    assert result.status is P3SourceRevalidationStatus.VALID
    assert result.source_stale is False
    assert db.get(ReuseSourceItem, source.id).source_trace == original_trace


def test_revalidate_archived_source_marks_stale(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    source = _add_source(service, project)
    candidate.status = "archived"
    db.commit()
    result = service.revalidate_source_item(
        project_id=project.id,
        source_item_id=source.id,
    )
    assert result.status is P3SourceRevalidationStatus.STALE
    assert result.reason_code is P3SourceEligibilityReason.SOURCE_ARCHIVED
    assert db.get(ReuseSourceItem, source.id).source_stale is True


def test_revalidate_fingerprint_drift_marks_stale_without_overwrite(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    source = _add_source(service, project)
    original_fingerprint = source.source_fingerprint
    original_trace = dict(source.source_trace)
    candidate.answer = "Changed answer"
    db.commit()
    result = service.revalidate_source_item(
        project_id=project.id,
        source_item_id=source.id,
    )
    persisted = db.get(ReuseSourceItem, source.id)
    assert result.reason_code is (
        P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH
    )
    assert persisted.source_stale is True
    assert persisted.source_fingerprint == original_fingerprint
    assert persisted.source_trace == original_trace


@pytest.mark.parametrize(
    ("updates", "expected_reason"),
    [
        (
            {"source_version": 2},
            P3SourceEligibilityReason.SOURCE_NOT_CURRENT,
        ),
        (
            {"approved_review_id": "review_changed"},
            P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
        ),
        (
            {"snapshot_id": "snapshot_changed"},
            P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
        ),
    ],
)
def test_revalidate_changed_version_or_lineage_marks_stale(
    db: Session,
    service: P3ReuseService,
    updates: dict[str, object],
    expected_reason: P3SourceEligibilityReason,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    decision = _decision_for_item(source, **updates)
    with patch(
        "app.p3_reuse_service.p3_source_eligibility.check_source_eligibility",
        return_value=decision,
    ):
        result = service.revalidate_source_item(
            project_id=project.id,
            source_item_id=source.id,
        )
    assert result.status is P3SourceRevalidationStatus.STALE
    assert result.reason_code is expected_reason
    assert db.get(ReuseSourceItem, source.id).source_stale is True


def test_removed_source_revalidation_is_skipped_without_m1_call(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    service.remove_source_from_project(
        project_id=project.id,
        source_item_id=source.id,
    )
    with patch(
        "app.p3_reuse_service.p3_source_eligibility.check_source_eligibility",
        side_effect=AssertionError("removed source must be skipped"),
    ):
        result = service.revalidate_source_item(
            project_id=project.id,
            source_item_id=source.id,
        )
    assert result.status is P3SourceRevalidationStatus.SKIPPED_REMOVED


def test_all_valid_sources_activate_project(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    _add_source(service, project)
    active = service.activate_project(project.id)
    assert active.status is ReuseProjectStatus.ACTIVE


def test_existing_stale_source_blocks_activation(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    repositories.mark_source_stale(db, source.id)
    with pytest.raises(P3SourceStale):
        service.activate_project(project.id)
    assert service.get_project(project.id).status is ReuseProjectStatus.DRAFT


def test_ineligible_source_during_activation_keeps_project_draft(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    source = _add_source(service, project)
    candidate.status = "archived"
    db.commit()
    with pytest.raises(P3SourceIneligible) as caught:
        service.activate_project(project.id)
    assert caught.value.reason_code is P3SourceEligibilityReason.SOURCE_ARCHIVED
    assert service.get_project(project.id).status is ReuseProjectStatus.DRAFT
    assert db.get(ReuseSourceItem, source.id).source_stale is True


def test_activation_has_no_partial_active_state_with_mixed_sources(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    valid = _add_p1(db, candidate_id="candidate_valid")
    invalid = _add_p1(db, candidate_id="candidate_invalid")
    valid_source = _add_source(
        service,
        project,
        source_id=valid.id,
        request_id="request-valid",
    )
    invalid_source = _add_source(
        service,
        project,
        source_id=invalid.id,
        request_id="request-invalid",
    )
    invalid.status = "archived"
    db.commit()
    with pytest.raises(P3SourceIneligible):
        service.activate_project(project.id)
    assert service.get_project(project.id).status is ReuseProjectStatus.DRAFT
    assert db.get(ReuseSourceItem, valid_source.id).source_stale is False
    assert db.get(ReuseSourceItem, invalid_source.id).source_stale is True


def test_active_project_freezes_source_selection(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    source = _add_source(service, project)
    service.activate_project(project.id)
    with pytest.raises(P3ProjectStateError):
        _add_source(service, project, source_id="candidate_other")
    with pytest.raises(P3ProjectStateError):
        service.remove_source_from_project(
            project_id=project.id,
            source_item_id=source.id,
        )


def test_project_revalidation_is_bounded_and_queries_project_once(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    first = _add_p1(db, candidate_id="candidate_1")
    second = _add_p1(db, candidate_id="candidate_2")
    _add_source(service, project, source_id=first.id, request_id="request-1")
    _add_source(service, project, source_id=second.id, request_id="request-2")
    with patch.object(
        repositories,
        "get_project_by_id",
        wraps=repositories.get_project_by_id,
    ) as project_get:
        with patch.object(
            repositories,
            "list_project_source_items",
            wraps=repositories.list_project_source_items,
        ) as source_list:
            result = service.revalidate_project_sources(project.id)
    assert result.total == 2
    assert all(item.status is P3SourceRevalidationStatus.VALID for item in result.results)
    assert project_get.call_count == 1
    assert source_list.call_count == 1
    with pytest.raises(P3ServiceValidationError):
        service.revalidate_project_sources(
            project.id,
            limit=MAX_PROJECT_REVALIDATION_SOURCES + 1,
        )


def test_repository_errors_are_converted_to_stable_service_errors(
    service: P3ReuseService,
) -> None:
    with patch.object(
        repositories,
        "get_project_by_id",
        side_effect=repositories.P3RepositoryNotFound("db details"),
    ):
        with pytest.raises(P3ServiceNotFound) as missing:
            service.get_project("missing")
    assert missing.value.code == "P3_NOT_FOUND"
    assert "db details" not in str(missing.value)

    with patch.object(
        repositories,
        "list_projects",
        side_effect=repositories.P3RepositoryValidationError("unsafe"),
    ):
        with pytest.raises(P3ServiceValidationError) as invalid:
            service.list_projects()
    assert invalid.value.code == "P3_VALIDATION_ERROR"


def test_service_does_not_write_sql_or_copy_m1_rules() -> None:
    source = inspect.getsource(service_module)
    for forbidden in (
        ".query(",
        ".execute(",
        "select(",
        "KnowledgeCandidate",
        "KnowledgeAsset",
        "ReviewRecord",
        "SOURCE_STATUS_APPROVED",
        "SOURCE_ACTIVE",
    ):
        assert forbidden not in source
    assert "check_source_eligibility" in source
    assert "repositories." in source


def test_service_does_not_call_provider_embedding_retrieval_or_network(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    _add_p1(db)
    with patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network must not run"),
    ):
        source = _add_source(service, project)
    assert source.id
    module_source = inspect.getsource(service_module).lower()
    for forbidden in (
        "openai",
        "embedding",
        "retrieval_service",
        "extraction_provider",
    ):
        assert forbidden not in module_source


def test_service_does_not_modify_p1_p2_records(
    db: Session,
    service: P3ReuseService,
) -> None:
    project = _create_project(service)
    candidate = _add_p1(db)
    knowledge = _add_p2(db)
    _add_source(service, project)
    _add_source(
        service,
        project,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id=knowledge.id,
        request_id="request-p2",
    )
    assert db.get(models.KnowledgeCandidate, candidate.id).status == "approved"
    assert db.get(models.KnowledgeAsset, knowledge.id).status == "active"


def test_no_unimplemented_p3_tables_or_physical_delete_flow() -> None:
    registered = {
        name
        for name in Base.metadata.tables
        if name.startswith("reuse_") or name.startswith("export_")
    }
    assert registered == P3_TABLES
    assert FORBIDDEN_FUTURE_TABLES.isdisjoint(registered)
    module_source = inspect.getsource(service_module)
    assert ".delete(" not in module_source
    assert "DELETE FROM" not in module_source.upper()


def test_service_errors_do_not_leak_secret_or_connection_details(
    service: P3ReuseService,
) -> None:
    with patch.object(
        repositories,
        "get_project_by_id",
        side_effect=repositories.P3RepositoryConflict(
            "postgresql://user:password@localhost/datahub"
        ),
    ):
        with pytest.raises(P3ServiceConflict) as caught:
            service.get_project("project")
    serialized = (
        f"{caught.value} {caught.value.code} {caught.value.context}".lower()
    )
    for forbidden in ("postgresql://", "password", "token", "secret"):
        assert forbidden not in serialized


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgresql_service_activation_and_failure_atomicity() -> None:
    url = require_test_database_url(
        TEST_DATABASE_URL,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[ReuseProject.__table__, ReuseSourceItem.__table__],
    )
    created_project_ids: list[str] = []
    try:
        with SessionLocal() as session:
            service = P3ReuseService(session)
            eligible = P3SourceEligibilityDecision(
                source_type=P3SourceType.P1_KNOWLEDGE.value,
                source_id="pg_candidate",
                eligible=True,
                reason_code=P3SourceEligibilityReason.ELIGIBLE,
                source_status="approved",
                content_fingerprint="a" * 64,
                approved_review_id="pg_review",
                lineage_complete=True,
                checked_conditions=["SOURCE_TRACE_COMPLETE"],
            )
            with patch(
                "app.p3_reuse_service.p3_source_eligibility.check_source_eligibility",
                return_value=eligible,
            ):
                project = service.create_project(
                    name="PostgreSQL valid",
                    description=None,
                    idempotency_key="p3m23-pg-valid",
                    actor_role="cleaner",
                    request_id="pg-request-valid",
                )
                created_project_ids.append(project.id)
                service.add_source_to_project(
                    project_id=project.id,
                    source_type=P3SourceType.P1_KNOWLEDGE,
                    source_id="pg_candidate",
                    source_version=None,
                    expected_fingerprint=None,
                    actor_role="cleaner",
                    request_id="pg-source-valid",
                )
                assert service.activate_project(project.id).status is (
                    ReuseProjectStatus.ACTIVE
                )

                failed = service.create_project(
                    name="PostgreSQL failed",
                    description=None,
                    idempotency_key="p3m23-pg-failed",
                    actor_role="cleaner",
                    request_id="pg-request-failed",
                )
                created_project_ids.append(failed.id)
                service.add_source_to_project(
                    project_id=failed.id,
                    source_type=P3SourceType.P1_KNOWLEDGE,
                    source_id="pg_candidate",
                    source_version=None,
                    expected_fingerprint=None,
                    actor_role="cleaner",
                    request_id="pg-source-failed",
                )

            ineligible = eligible.model_copy(
                update={
                    "eligible": False,
                    "reason_code": P3SourceEligibilityReason.SOURCE_ARCHIVED,
                    "source_status": "archived",
                }
            )
            with patch(
                "app.p3_reuse_service.p3_source_eligibility.check_source_eligibility",
                return_value=ineligible,
            ):
                with pytest.raises(P3SourceIneligible):
                    service.activate_project(failed.id)
            assert service.get_project(failed.id).status is ReuseProjectStatus.DRAFT
    finally:
        with SessionLocal() as session:
            session.query(ReuseSourceItem).filter(
                ReuseSourceItem.project_id.in_(created_project_ids)
            ).delete(synchronize_session=False)
            session.query(ReuseProject).filter(
                ReuseProject.id.in_(created_project_ids)
            ).delete(synchronize_session=False)
            session.commit()
        engine.dispose()
