"""Focused P3-M3.3 tests for provider-free deterministic generation."""

from __future__ import annotations

import inspect
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect as sa_inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db_models as models  # noqa: E402
from app import p3_asset_service as asset_service_module  # noqa: E402
from app import p3_deterministic_templates as templates  # noqa: E402
from app import p3_source_material_reader as reader  # noqa: E402
from app.database import Base  # noqa: E402
from app.p3_asset_repositories import (  # noqa: E402
    get_asset_version_by_idempotency_key,
)
from app.p3_asset_schemas import (  # noqa: E402
    ASSET_PAYLOAD_SCHEMAS,
    P3SopPayload,
)
from app.p3_asset_service import (  # noqa: E402
    MAX_GENERATION_SOURCES,
    P3AssetService,
    P3AssetServiceError,
    build_source_manifest,
)
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_reuse_service import P3ReuseService, P3SourceIneligible  # noqa: E402
from app.p3_source_eligibility_schemas import P3SourceType  # noqa: E402


FROZEN_EXPORT_TABLES = {"export_jobs", "export_artifacts"}


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
    cleanup_models = (
        ReuseAssetVersionSource,
        ReuseAssetVersion,
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
    SessionLocal = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with SessionLocal() as session:
        for model in cleanup_models:
            session.query(model).delete()
        session.commit()
        yield session
        session.rollback()
        for model in cleanup_models:
            session.query(model).delete()
        session.commit()


def _add_p1(
    db: Session,
    *,
    candidate_id: str = "m33_candidate",
    source_type: str = "sanitized_batch",
    status: str = "approved",
) -> models.KnowledgeCandidate:
    lineage_id = (
        f"bad_case_{candidate_id}"
        if source_type == "bad_case"
        else f"batch_{candidate_id}"
    )
    metadata = {
        "knowledge_type": "faq",
        (
            "source_bad_case_id"
            if source_type == "bad_case"
            else "source_batch_id"
        ): lineage_id,
    }
    candidate = models.KnowledgeCandidate(
        id=candidate_id,
        source_type=source_type,
        source_id=lineage_id,
        question=f"Question for {candidate_id}?",
        answer=f"Approved answer for {candidate_id}.",
        intent="customer_policy",
        tags=["governed", "policy"],
        risk_level="low",
        quality_score=0.95,
        status=status,
        metadata_json=metadata,
    )
    snapshot = {
        "candidate_id": candidate_id,
        "source_type": source_type,
        "question": candidate.question,
        "answer": candidate.answer,
        "intent": candidate.intent,
        "tags": ["governed", "policy"],
        "risk_level": candidate.risk_level,
        "knowledge_type": "faq",
        (
            "source_bad_case_id"
            if source_type == "bad_case"
            else "source_batch_id"
        ): lineage_id,
    }
    db.add(candidate)
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
                id=lineage_id,
                user_question="Raw bad-case question",
                bad_answer="Raw incorrect answer",
                expected_answer=candidate.answer,
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
    suffix: str = "m33",
    status: str = "active",
    index_status: str | None = "ready",
) -> models.KnowledgeAsset:
    asset_id = f"asset_{suffix}"
    extraction_id = f"extraction_{suffix}"
    review_id = f"review_{suffix}"
    snapshot_id = f"snapshot_{suffix}"
    knowledge_id = f"knowledge_{suffix}"
    approved_content = f"Approved governed P2 content for {suffix}."
    db.add(
        models.Asset(
            id=asset_id,
            asset_type="image",
            file_name=f"{suffix}.png",
            mime_type="image/png",
            size=8,
            storage_uri=f"test://{suffix}.png",
            hash=(f"{suffix}-hash-" + "a" * 64)[:64],
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
            version=1,
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
            revised_content=approved_content,
            version=1,
        )
    )
    db.add(
        models.AssetReviewSnapshot(
            id=snapshot_id,
            asset_id=asset_id,
            extraction_id=extraction_id,
            review_id=review_id,
            extract_type="ocr",
            original_content="Machine content.",
            approved_content=approved_content,
            metadata_json={"title": f"Governed topic {suffix}"},
            version=1,
        )
    )
    knowledge = models.KnowledgeAsset(
        id=knowledge_id,
        source_snapshot_id=snapshot_id,
        asset_id=asset_id,
        content=approved_content,
        content_type="ocr",
        status=status,
        version=1,
        metadata_json={},
    )
    db.add(knowledge)
    if index_status is not None:
        db.add(
            models.P2KnowledgeIndexEntry(
                id=f"index_{suffix}",
                knowledge_asset_id=knowledge_id,
                status=index_status,
                generation=1,
                fingerprint=(f"index-{suffix}-" + "0" * 64)[:64],
                sync_state=index_status,
            )
        )
    db.commit()
    return knowledge


def _create_project(
    db: Session,
    *,
    key: str = "m33_project_key",
) -> tuple[P3ReuseService, ReuseProject]:
    service = P3ReuseService(db)
    project = service.create_project(
        name="M3.3 deterministic generation",
        description="Focused test",
        idempotency_key=key,
        actor_role="cleaner",
        request_id=f"request_{key}",
    )
    return service, project


def _add_project_source(
    service: P3ReuseService,
    project: ReuseProject,
    *,
    source_type: P3SourceType,
    source_id: str,
    source_version: int | None = None,
) -> ReuseSourceItem:
    return service.add_source_to_project(
        project_id=project.id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        expected_fingerprint=None,
        actor_role="cleaner",
        request_id=f"select_{source_id}",
    )


def _active_p1_project(
    db: Session,
    *,
    key: str = "m33_project_key",
    candidate_id: str = "m33_candidate",
    source_type: str = "sanitized_batch",
) -> tuple[P3AssetService, ReuseProject, ReuseSourceItem]:
    candidate = _add_p1(
        db,
        candidate_id=candidate_id,
        source_type=source_type,
    )
    reuse_service, project = _create_project(db, key=key)
    governed_type = (
        P3SourceType.APPROVED_BAD_CASE_CORRECTION
        if source_type == "bad_case"
        else P3SourceType.P1_KNOWLEDGE
    )
    source = _add_project_source(
        reuse_service,
        project,
        source_type=governed_type,
        source_id=candidate.id,
    )
    reuse_service.activate_project(project.id)
    return P3AssetService(db), project, source


def _generate(
    service: P3AssetService,
    project: ReuseProject,
    *,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    key: str = "m33_generation_key",
    template_key: str | None = None,
) -> ReuseAssetVersion:
    return service.generate_draft_asset(
        project_id=project.id,
        asset_type=asset_type,
        template_key=template_key,
        idempotency_key=key,
        actor_role="cleaner",
        request_id=f"request_{key}",
    )


@pytest.mark.parametrize("asset_type", list(ReuseAssetType))
def test_all_five_deterministic_asset_types_generate_valid_payloads(
    db: Session,
    asset_type: ReuseAssetType,
) -> None:
    service, project, _source = _active_p1_project(db)
    version = _generate(service, project, asset_type=asset_type)
    assert version.status is ReuseAssetVersionStatus.GENERATED
    assert version.version_number == 1
    assert version.generation_mode.value == "deterministic_template"
    ASSET_PAYLOAD_SCHEMAS[asset_type].model_validate(version.content_payload)
    assert version.content_hash


def test_draft_and_archived_projects_cannot_generate(db: Session) -> None:
    candidate = _add_p1(db)
    reuse_service, project = _create_project(db)
    _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=candidate.id,
    )
    service = P3AssetService(db)
    with pytest.raises(P3AssetServiceError) as draft:
        _generate(service, project)
    assert draft.value.code == "P3_ASSET_PROJECT_NOT_ACTIVE"

    reuse_service.activate_project(project.id)
    reuse_service.archive_project(project.id)
    with pytest.raises(P3AssetServiceError) as archived:
        _generate(service, project, key="archived_generation")
    assert archived.value.code == "P3_ASSET_PROJECT_NOT_ACTIVE"
    assert db.query(ReuseAssetVersion).count() == 0


def test_active_project_without_sources_is_rejected(db: Session) -> None:
    project = ReuseProject(
        id="m33_empty_active",
        name="empty",
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id="empty_request",
        idempotency_key="empty_key",
    )
    db.add(project)
    db.commit()
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(P3AssetService(db), project)
    assert caught.value.code == "P3_ASSET_NO_SOURCES"


def test_stale_source_is_rejected_before_generation(db: Session) -> None:
    service, project, source = _active_p1_project(db)
    source.source_stale = True
    db.commit()
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(service, project)
    assert caught.value.code == "P3_ASSET_SOURCE_STALE"
    assert db.query(ReuseAssetVersion).count() == 0


def test_removed_source_does_not_participate_in_generation(db: Session) -> None:
    first = _add_p1(db, candidate_id="m33_removed")
    second = _add_p1(db, candidate_id="m33_current")
    reuse_service, project = _create_project(db)
    removed = _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=first.id,
    )
    current = _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=second.id,
    )
    reuse_service.remove_source_from_project(
        project_id=project.id,
        source_item_id=removed.id,
    )
    reuse_service.activate_project(project.id)
    version = _generate(P3AssetService(db), project)
    bindings = db.query(ReuseAssetVersionSource).filter(
        ReuseAssetVersionSource.asset_version_id == version.id
    )
    assert [row.source_item_id for row in bindings] == [current.id]


def test_more_than_one_hundred_sources_is_rejected_without_loading_all(
    db: Session,
) -> None:
    project = ReuseProject(
        id="m33_large_project",
        name="large",
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id="large_request",
        idempotency_key="large_key",
    )
    db.add(project)
    db.commit()
    for index in range(MAX_GENERATION_SOURCES + 1):
        db.add(
            ReuseSourceItem(
                id=f"m33_large_source_{index:03d}",
                project_id=project.id,
                source_type=P3SourceType.P1_KNOWLEDGE,
                source_id=f"m33_candidate_{index:03d}",
                source_version=None,
                source_fingerprint="a" * 64,
                eligibility_policy_version="p3-source-eligibility-v1",
                approved_review_id=f"review_{index}",
                lineage_manifest_hash="b" * 64,
                source_trace={"candidate_id": f"m33_candidate_{index:03d}"},
                selected_by_role="cleaner",
                request_id=f"request_{index}",
            )
        )
    db.commit()
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(P3AssetService(db), project)
    assert caught.value.code == "P3_ASSET_LIMIT_EXCEEDED"


def test_fingerprint_drift_and_lineage_change_are_rejected(db: Session) -> None:
    service, project, source = _active_p1_project(db)
    candidate = db.get(models.KnowledgeCandidate, source.source_id)
    candidate.answer = "Changed after approval."
    db.commit()
    with pytest.raises(P3AssetServiceError) as fingerprint:
        _generate(service, project)
    assert fingerprint.value.code == "P3_ASSET_SOURCE_INELIGIBLE"
    assert db.get(ReuseSourceItem, source.id).source_stale is True

    db.query(ReuseAssetVersionSource).delete()
    db.query(ReuseAssetVersion).delete()
    db.query(ReuseSourceItem).delete()
    db.query(ReuseProject).delete()
    db.query(models.ReviewRecord).delete()
    db.query(models.KnowledgeCandidate).delete()
    db.commit()
    service, project, source = _active_p1_project(
        db,
        key="m33_lineage_project",
        candidate_id="m33_lineage",
    )
    source.lineage_manifest_hash = "f" * 64
    db.commit()
    with pytest.raises(P3AssetServiceError) as lineage:
        _generate(service, project, key="m33_lineage_generation")
    assert lineage.value.code == "P3_ASSET_SOURCE_EVIDENCE_CHANGED"


def test_ready_but_not_serving_p2_generates_successfully(db: Session) -> None:
    knowledge = _add_p2(db, index_status="ready")
    reuse_service, project = _create_project(db)
    _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P2_KNOWLEDGE_ASSET,
        source_id=knowledge.id,
        source_version=knowledge.version,
    )
    reuse_service.activate_project(project.id)
    version = _generate(P3AssetService(db), project)
    assert version.status is ReuseAssetVersionStatus.GENERATED
    assert "Approved governed P2 content" in str(version.content_payload)


def test_approved_bad_case_correction_generates_but_raw_bad_case_cannot_enter(
    db: Session,
) -> None:
    service, project, _source = _active_p1_project(
        db,
        source_type="bad_case",
    )
    assert _generate(service, project).status is ReuseAssetVersionStatus.GENERATED

    _add_p1(db, candidate_id="m33_other_candidate")
    reuse_service, other = _create_project(db, key="m33_raw_project")
    with pytest.raises(P3SourceIneligible):
        reuse_service.add_source_to_project(
            project_id=other.id,
            source_type="RAW_BAD_CASE",
            source_id="bad_case_m33_candidate",
            source_version=None,
            expected_fingerprint=None,
            actor_role="cleaner",
            request_id="raw_request",
        )


def test_manifest_and_generated_content_are_order_independent(db: Session) -> None:
    first = _add_p1(db, candidate_id="m33_a")
    second = _add_p1(db, candidate_id="m33_b")
    reuse_service, project = _create_project(db)
    source_a = _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=first.id,
    )
    source_b = _add_project_source(
        reuse_service,
        project,
        source_type=P3SourceType.P1_KNOWLEDGE,
        source_id=second.id,
    )
    assert build_source_manifest([source_a, source_b]) == build_source_manifest(
        [source_b, source_a]
    )
    reuse_service.activate_project(project.id)
    service = P3AssetService(db)
    first_version = _generate(service, project, key="m33_order_1")
    second_version = _generate(service, project, key="m33_order_2")
    assert second_version.version_number == 2
    assert second_version.content_payload == first_version.content_payload
    assert second_version.content_hash == first_version.content_hash


def test_idempotent_replay_and_different_request_conflict(db: Session) -> None:
    service, project, _source = _active_p1_project(db)
    first = _generate(service, project)
    replay = _generate(service, project)
    assert replay.id == first.id
    assert db.query(ReuseAssetVersion).count() == 1
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(
            service,
            project,
            asset_type=ReuseAssetType.SOP,
        )
    assert caught.value.code == "P3_ASSET_IDEMPOTENCY_CONFLICT"


def test_template_version_is_part_of_generation_request_identity(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, project, _source = _active_p1_project(db)
    first = _generate(service, project)
    key = templates.DEFAULT_TEMPLATE_KEYS[ReuseAssetType.TRAINING_MATERIAL]
    v2_template = replace(
        templates.TEMPLATE_REGISTRY[key],
        template_version="v2",
    )
    monkeypatch.setitem(templates.TEMPLATE_REGISTRY, key, v2_template)
    with pytest.raises(P3AssetServiceError) as replay:
        _generate(service, project)
    assert replay.value.code == "P3_ASSET_IDEMPOTENCY_CONFLICT"
    second = _generate(service, project, key="m33_generation_v2")
    assert second.version_number == 2
    assert first.template_version == "v1"
    assert second.template_version == "v2"


def test_generation_failure_is_persisted_safely_without_duplicate_version(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, project, _source = _active_p1_project(db)
    key = templates.DEFAULT_TEMPLATE_KEYS[ReuseAssetType.TRAINING_MATERIAL]

    def fail(_materials):
        raise RuntimeError(
            "postgresql://user:password@internal/datahub token=private"
        )

    monkeypatch.setitem(
        templates.TEMPLATE_REGISTRY,
        key,
        replace(templates.TEMPLATE_REGISTRY[key], renderer=fail),
    )
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(service, project)
    assert caught.value.code == "P3_ASSET_GENERATION_FAILED"
    failed = get_asset_version_by_idempotency_key(db, "m33_generation_key")
    assert failed.status is ReuseAssetVersionStatus.FAILED
    assert failed.failure_code == "P3_ASSET_GENERATION_FAILED"
    assert "postgresql://" not in failed.failure_message.lower()
    with pytest.raises(P3AssetServiceError):
        _generate(service, project)
    assert db.query(ReuseAssetVersion).count() == 1


def test_invalid_template_output_is_failed_with_stable_code(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, project, _source = _active_p1_project(db)
    key = templates.DEFAULT_TEMPLATE_KEYS[ReuseAssetType.TRAINING_MATERIAL]

    def wrong_payload(_materials):
        return P3SopPayload(
            title="wrong",
            purpose="wrong",
            scope="wrong",
            prerequisites=[],
            steps=[],
            cautions=[],
            escalation_rules=[],
            source_refs=[],
        )

    monkeypatch.setitem(
        templates.TEMPLATE_REGISTRY,
        key,
        replace(templates.TEMPLATE_REGISTRY[key], renderer=wrong_payload),
    )
    with pytest.raises(P3AssetServiceError) as caught:
        _generate(service, project)
    assert caught.value.code == "P3_ASSET_TEMPLATE_INVALID"
    failed = get_asset_version_by_idempotency_key(db, "m33_generation_key")
    assert failed.status is ReuseAssetVersionStatus.FAILED
    assert failed.failure_code == "P3_ASSET_TEMPLATE_INVALID"


def test_source_snapshot_is_complete_and_historical_after_source_stale(
    db: Session,
) -> None:
    service, project, source = _active_p1_project(db)
    version = _generate(service, project)
    binding = db.query(ReuseAssetVersionSource).filter(
        ReuseAssetVersionSource.asset_version_id == version.id
    ).one()
    original = (
        binding.source_fingerprint,
        binding.approved_review_id,
        binding.lineage_manifest_hash,
        dict(binding.source_trace_snapshot),
    )
    source.source_stale = True
    source.removed_at = datetime.now(UTC)
    db.commit()
    db.expire_all()
    binding = db.get(ReuseAssetVersionSource, binding.id)
    assert (
        binding.source_fingerprint,
        binding.approved_review_id,
        binding.lineage_manifest_hash,
        binding.source_trace_snapshot,
    ) == original


def test_reader_uses_approved_p1_snapshot_and_never_raw_bad_case_content(
    db: Session,
) -> None:
    _service, _project, source = _active_p1_project(
        db,
        source_type="bad_case",
    )
    material = reader.read_generation_source_material(db, source)
    assert material.approved_content == "Approved answer for m33_candidate."
    assert "Raw incorrect answer" not in material.approved_content
    assert "Raw bad-case question" not in material.approved_content


def test_missing_approved_material_returns_stable_safe_error(db: Session) -> None:
    _service, _project, source = _active_p1_project(db)
    db.query(models.ReviewRecord).delete()
    db.commit()
    with pytest.raises(reader.P3SourceMaterialReadError) as caught:
        reader.read_generation_source_material(db, source)
    assert caught.value.code == "P3_ASSET_SOURCE_CONTENT_UNAVAILABLE"
    assert source.source_id not in caught.value.message


def test_generation_does_not_modify_p1_p2_or_write_export_tables(
    db: Session,
    sqlite_engine,
) -> None:
    service, project, source = _active_p1_project(db)
    candidate = db.get(models.KnowledgeCandidate, source.source_id)
    review = db.get(models.ReviewRecord, source.approved_review_id)
    before = (
        candidate.question,
        candidate.answer,
        candidate.status,
        dict(review.snapshot_json),
    )
    _generate(service, project)
    db.expire_all()
    candidate = db.get(models.KnowledgeCandidate, source.source_id)
    review = db.get(models.ReviewRecord, source.approved_review_id)
    assert (
        candidate.question,
        candidate.answer,
        candidate.status,
        review.snapshot_json,
    ) == before
    registered_export_tables = FROZEN_EXPORT_TABLES & set(
        sa_inspect(sqlite_engine).get_table_names()
    )
    for table_name in registered_export_tables:
        assert db.execute(
            text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one() == 0


def test_generation_boundary_has_no_provider_network_or_random_dependency() -> None:
    combined = "\n".join(
        inspect.getsource(module)
        for module in (
            asset_service_module,
            templates,
            reader,
        )
    ).lower()
    for forbidden in (
        "requests",
        "httpx",
        "urllib",
        "openai",
        "embedding",
        "retrieval",
        "random.",
    ):
        assert forbidden not in combined
    assert "datetime.now" not in combined
    assert "badcase" not in inspect.getsource(reader)
