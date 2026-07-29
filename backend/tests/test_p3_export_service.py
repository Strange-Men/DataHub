"""Focused P3-M7.2 deterministic export Service tests."""

from __future__ import annotations

import csv
import hashlib
import io
import json
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

from app.database import Base  # noqa: E402
from app.p3_export_models import (  # noqa: E402
    P3ExportArtifact,
    P3ExportFormat,
    P3ExportJob,
    P3ExportJobStatus,
)
from app.p3_export_repositories import (  # noqa: E402
    create_pending_export_job,
    get_export_artifact_by_job_id,
    get_export_job_by_id,
    list_export_jobs,
    mark_export_job_running,
)
from app.p3_export_schemas import (  # noqa: E402
    P3_EXPORT_POLICY_VERSION,
    P3ExportErrorCode,
)
from app.p3_export_service import (  # noqa: E402
    P3ExportService,
    P3ExportServiceError,
)
from app.p3_export_serializers import (  # noqa: E402
    P3ExportSerializationError,
    serialize_asset_payload,
)
from app.p3_export_storage import (  # noqa: E402
    LocalFilesystemP3ExportStorage,
    P3ExportStorageError,
)
from app.p3_publication_service import P3PublicationService  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseProjectStatus,
)
from app.p3_reuse_repositories import P3RepositoryConflict  # noqa: E402
from app.p3_asset_repositories import canonicalize_asset_content  # noqa: E402
from test_p3_publication_service import (  # noqa: E402
    _approve,
    _approved_asset,
    _generate,
    _publish,
)


TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
ASSET_TYPES = list(ReuseAssetType)
EXPECTED_ERROR_CODES = {
    "P3_EXPORT_PROJECT_NOT_ACTIVE",
    "P3_EXPORT_ASSET_NOT_FOUND",
    "P3_EXPORT_ASSET_NOT_PUBLISHED",
    "P3_EXPORT_ASSET_NOT_CURRENT",
    "P3_EXPORT_REVIEW_INVALID",
    "P3_EXPORT_CONTENT_HASH_MISMATCH",
    "P3_EXPORT_MANIFEST_MISMATCH",
    "P3_EXPORT_SOURCE_STALE",
    "P3_EXPORT_SOURCE_EVIDENCE_CHANGED",
    "P3_EXPORT_GROUNDING_INVALID",
    "P3_EXPORT_FORMAT_UNSUPPORTED",
    "P3_EXPORT_PAYLOAD_INVALID",
    "P3_EXPORT_SERIALIZATION_FAILED",
    "P3_EXPORT_STORAGE_FAILED",
    "P3_EXPORT_IDEMPOTENCY_CONFLICT",
    "P3_EXPORT_JOB_NOT_FOUND",
    "P3_EXPORT_JOB_STATE_INVALID",
    "P3_EXPORT_ARTIFACT_NOT_FOUND",
    "P3_EXPORT_ARTIFACT_REVOKED",
    "P3_EXPORT_ROLE_FORBIDDEN",
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


def test_export_error_codes_are_frozen():
    assert {code.value for code in P3ExportErrorCode} == EXPECTED_ERROR_CODES


@pytest.fixture
def db():
    engine = _sqlite_engine()
    Base.metadata.create_all(bind=engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def storage(tmp_path: Path):
    return LocalFilesystemP3ExportStorage(tmp_path / "exports")


def _published(
    db: Session,
    *,
    suffix: str,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
):
    project, source, asset, review = _approved_asset(
        db,
        suffix=suffix,
        asset_type=asset_type,
    )
    _publish(P3PublicationService(db), project, asset)
    db.refresh(asset)
    return project, source, asset, review


def _create(
    db: Session,
    storage: LocalFilesystemP3ExportStorage,
    *,
    suffix: str,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    export_format: P3ExportFormat = P3ExportFormat.JSONL,
):
    project, source, asset, review = _published(
        db,
        suffix=suffix,
        asset_type=asset_type,
    )
    outcome = P3ExportService(db, storage=storage).create_export(
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=export_format,
        idempotency_key=f"export_{suffix}",
        actor_role="admin",
        request_id=f"export_request_{suffix}",
    )
    return project, source, asset, review, outcome


@pytest.mark.parametrize("asset_type", ASSET_TYPES)
@pytest.mark.parametrize(
    "export_format",
    [P3ExportFormat.JSONL, P3ExportFormat.CSV],
)
def test_all_asset_types_export_in_both_formats(
    db,
    storage,
    asset_type,
    export_format,
):
    _project, _source, _asset, _review, outcome = _create(
        db,
        storage,
        suffix=f"{asset_type.value}_{export_format.value}",
        asset_type=asset_type,
        export_format=export_format,
    )
    assert outcome.job.status is P3ExportJobStatus.SUCCEEDED
    assert outcome.artifact is not None
    assert outcome.artifact.row_count >= 1
    assert outcome.artifact.export_format is export_format
    with storage.open_read(outcome.artifact.storage_key) as handle:
        content = handle.read()
    assert hashlib.sha256(content).hexdigest() == outcome.artifact.artifact_sha256
    assert len(content) == outcome.artifact.byte_size
    if export_format is P3ExportFormat.JSONL:
        assert not content.startswith(b"\xef\xbb\xbf")
        assert content.endswith(b"\n")
        assert b"\r\n" not in content
        rows = [
            json.loads(line)
            for line in content.decode("utf-8").splitlines()
        ]
    else:
        assert content.startswith(b"\xef\xbb\xbf")
        text = content.decode("utf-8-sig")
        assert "\r\n" in text
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
    assert len(rows) == outcome.artifact.row_count
    assert all("source_refs" in row for row in rows)


def test_sft_jsonl_has_required_fields(db, storage):
    *_unused, outcome = _create(
        db,
        storage,
        suffix="sft_fields",
        asset_type=ReuseAssetType.SFT_DATASET,
    )
    assert outcome.artifact is not None
    with storage.open_read(outcome.artifact.storage_key) as handle:
        record = json.loads(handle.readline())
    assert set(record) == {
        "instruction",
        "input",
        "output",
        "metadata",
        "source_refs",
    }


def test_sft_csv_preserves_metadata_and_rfc4180_escaping(db):
    project, _source, asset, _review = _published(
        db,
        suffix="sft_csv_metadata",
        asset_type=ReuseAssetType.SFT_DATASET,
    )
    del project
    payload = json.loads(json.dumps(asset.content_payload))
    payload["records"][0]["instruction"] = 'Use "quoted", value\nsafely'
    serialized = serialize_asset_payload(
        asset_type=ReuseAssetType.SFT_DATASET,
        content_payload=payload,
        export_format=P3ExportFormat.CSV,
    )
    text = serialized.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    assert list(rows[0]) == [
        "instruction",
        "input",
        "output",
        "metadata",
        "source_refs",
    ]
    assert rows[0]["instruction"] == 'Use "quoted", value\nsafely'
    assert json.loads(rows[0]["metadata"]) == payload["records"][0]["metadata"]
    assert json.loads(rows[0]["source_refs"]) == (
        payload["records"][0]["source_refs"]
    )


def test_different_keys_are_byte_reproducible(db, storage):
    project, _source, asset, _review = _published(db, suffix="reproducible")
    service = P3ExportService(db, storage=storage)
    outcomes = [
        service.create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key=f"reproducible_{index}",
            actor_role="admin",
            request_id=f"request_{index}",
        )
        for index in range(2)
    ]
    artifacts = [outcome.artifact for outcome in outcomes]
    assert all(artifact is not None for artifact in artifacts)
    assert artifacts[0].artifact_sha256 == artifacts[1].artifact_sha256
    assert artifacts[0].export_manifest_hash == artifacts[1].export_manifest_hash
    with storage.open_read(artifacts[0].storage_key) as first:
        first_bytes = first.read()
    with storage.open_read(artifacts[1].storage_key) as second:
        second_bytes = second.read()
    assert first_bytes == second_bytes


def test_manifest_excludes_runtime_and_secret_fields(db, storage):
    *_unused, outcome = _create(db, storage, suffix="manifest_safe")
    assert outcome.artifact is not None
    forbidden = {
        "created_at",
        "request_id",
        "idempotency_key",
        "actor_role",
        "token",
        "provider",
        "storage_key",
    }
    source = Path(
        ROOT_DIR / "backend" / "app" / "p3_export_service.py"
    ).read_text(encoding="utf-8")
    manifest_block = source[source.index("def _manifest("):source.index("def _replay(")]
    assert not any(f"{field}=" in manifest_block for field in forbidden)
    assert outcome.job.export_policy_version == P3_EXPORT_POLICY_VERSION


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("project_archived", "P3_EXPORT_PROJECT_NOT_ACTIVE"),
        ("asset_approved", "P3_EXPORT_ASSET_NOT_PUBLISHED"),
        ("source_stale", "P3_EXPORT_SOURCE_STALE"),
        ("content_drift", "P3_EXPORT_CONTENT_HASH_MISMATCH"),
        ("review_hash", "P3_EXPORT_REVIEW_INVALID"),
    ],
)
def test_governance_failure_creates_no_job_or_file(
    db,
    storage,
    mutation,
    expected,
):
    project, source, asset, review = _published(
        db,
        suffix=f"gate_{mutation}",
    )
    if mutation == "project_archived":
        project.status = ReuseProjectStatus.ARCHIVED
    elif mutation == "asset_approved":
        asset.status = ReuseAssetVersionStatus.APPROVED
    elif mutation == "source_stale":
        source.source_stale = True
    elif mutation == "content_drift":
        asset.content_payload = {**asset.content_payload, "title": "drift"}
    elif mutation == "review_hash":
        review.reviewed_content_hash = "0" * 64
    db.commit()
    with pytest.raises(P3ExportServiceError) as caught:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key=f"gate_key_{mutation}",
            actor_role="admin",
            request_id=f"gate_request_{mutation}",
        )
    assert caught.value.code == expected
    assert db.query(P3ExportJob).count() == 0
    assert not any(storage.root.rglob("*.jsonl"))


def test_superseded_version_is_not_exportable(db, storage):
    project, _source, first, _review = _published(db, suffix="superseded")
    second = _generate(
        db,
        project,
        suffix="superseding",
    )
    _approve(db, project, second, suffix="superseding")
    _publish(P3PublicationService(db), project, second)
    db.refresh(first)
    assert first.status is ReuseAssetVersionStatus.SUPERSEDED
    with pytest.raises(P3ExportServiceError) as caught:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=first.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="superseded_export",
            actor_role="admin",
            request_id="superseded_export_request",
        )
    assert caught.value.code == "P3_EXPORT_ASSET_NOT_PUBLISHED"
    assert db.query(P3ExportJob).count() == 0


def test_idempotency_replays_succeeded_job(db, storage):
    project, _source, asset, _review = _published(db, suffix="replay_success")
    service = P3ExportService(db, storage=storage)
    kwargs = dict(
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.JSONL,
        idempotency_key="same_success_key",
        actor_role="admin",
        request_id="same_success_request",
    )
    first = service.create_export(**kwargs)
    second = service.create_export(**kwargs)
    assert second.replayed is True
    assert first.job.id == second.job.id
    assert db.query(P3ExportJob).count() == 1
    assert db.query(P3ExportArtifact).count() == 1


def test_same_key_different_format_conflicts(db, storage):
    project, _source, asset, _review = _published(db, suffix="key_conflict")
    service = P3ExportService(db, storage=storage)
    service.create_export(
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.JSONL,
        idempotency_key="format_conflict",
        actor_role="admin",
        request_id="format_first",
    )
    with pytest.raises(P3ExportServiceError) as caught:
        service.create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.CSV,
            idempotency_key="format_conflict",
            actor_role="admin",
            request_id="format_second",
        )
    assert caught.value.code == "P3_EXPORT_IDEMPOTENCY_CONFLICT"


def test_running_and_failed_jobs_replay_without_retry(db, storage):
    project, _source, asset, review = _published(db, suffix="state_replay")
    service = P3ExportService(db, storage=storage)
    fingerprint = service._request_fingerprint(
        project=project,
        asset=asset,
        review=review,
        export_format=P3ExportFormat.JSONL,
    )
    created = create_pending_export_job(
        db,
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.JSONL,
        export_policy_version=P3_EXPORT_POLICY_VERSION,
        requested_by_role="admin",
        request_id="state_replay_request",
        idempotency_key="state_replay_key",
        request_fingerprint=fingerprint,
    )
    mark_export_job_running(db, created.job.id)
    replay = service.create_export(
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.JSONL,
        idempotency_key="state_replay_key",
        actor_role="admin",
        request_id="state_replay_again",
    )
    assert replay.replayed is True
    assert replay.job.status is P3ExportJobStatus.RUNNING
    assert replay.artifact is None


class _FailingStorage(LocalFilesystemP3ExportStorage):
    def write_atomic(self, storage_key: str, content: bytes):
        raise P3ExportStorageError("postgresql://secret token=bad")


def test_storage_failure_is_audited_and_safe(db, tmp_path):
    project, _source, asset, _review = _published(db, suffix="storage_failure")
    storage = _FailingStorage(tmp_path / "failure")
    with pytest.raises(P3ExportServiceError) as caught:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="storage_failure_key",
            actor_role="admin",
            request_id="storage_failure_request",
        )
    assert caught.value.code == "P3_EXPORT_STORAGE_FAILED"
    job = db.query(P3ExportJob).one()
    assert job.status is P3ExportJobStatus.FAILED
    assert job.failure_code == "P3_EXPORT_STORAGE_FAILED"
    assert "postgresql://" not in (job.failure_message or "")
    assert "token" not in (job.failure_message or "").lower()
    assert db.query(P3ExportArtifact).count() == 0
    assert not any(storage.root.rglob("*.*"))
    replay = P3ExportService(db, storage=storage).create_export(
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.JSONL,
        idempotency_key="storage_failure_key",
        actor_role="admin",
        request_id="storage_failure_retry",
    )
    assert replay.replayed is True
    assert replay.job.status is P3ExportJobStatus.FAILED
    assert db.query(P3ExportJob).count() == 1


def test_serialization_failure_is_audited_without_artifact(db, storage):
    project, _source, asset, _review = _published(
        db,
        suffix="serialization_failure",
    )
    with patch(
        "app.p3_export_service.serialize_asset_payload",
        side_effect=P3ExportSerializationError("invalid payload"),
    ):
        with pytest.raises(P3ExportServiceError) as caught:
            P3ExportService(db, storage=storage).create_export(
                project_id=project.id,
                asset_version_id=asset.id,
                export_format=P3ExportFormat.JSONL,
                idempotency_key="serialization_failure_key",
                actor_role="admin",
                request_id="serialization_failure_request",
            )
    assert caught.value.code == "P3_EXPORT_SERIALIZATION_FAILED"
    job = db.query(P3ExportJob).one()
    assert job.status is P3ExportJobStatus.FAILED
    assert db.query(P3ExportArtifact).count() == 0


def test_completion_failure_cleans_uncommitted_file(db, storage):
    project, _source, asset, _review = _published(
        db,
        suffix="completion_failure",
    )
    with patch(
        "app.p3_export_service.repositories.complete_export_job",
        side_effect=P3RepositoryConflict("injected completion conflict"),
    ):
        with pytest.raises(P3ExportServiceError) as caught:
            P3ExportService(db, storage=storage).create_export(
                project_id=project.id,
                asset_version_id=asset.id,
                export_format=P3ExportFormat.JSONL,
                idempotency_key="completion_failure_key",
                actor_role="admin",
                request_id="completion_failure_request",
            )
    assert caught.value.code == "P3_EXPORT_SERIALIZATION_FAILED"
    assert db.query(P3ExportJob).one().status is P3ExportJobStatus.FAILED
    assert db.query(P3ExportArtifact).count() == 0
    assert not any(storage.root.rglob("*.jsonl"))


def test_snapshot_evidence_and_grounding_drift_are_rejected(db, storage):
    project, _source, asset, _review = _published(
        db,
        suffix="snapshot_evidence_drift",
    )
    snapshot = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == asset.id)
        .one()
    )
    snapshot.source_fingerprint = "f" * 64
    db.commit()
    with pytest.raises(P3ExportServiceError) as evidence:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="snapshot_evidence_drift",
            actor_role="admin",
            request_id="snapshot_evidence_request",
        )
    assert evidence.value.code == "P3_EXPORT_SOURCE_EVIDENCE_CHANGED"
    assert db.query(P3ExportJob).count() == 0

    project2, _source2, asset2, review2 = _published(
        db,
        suffix="grounding_drift",
    )
    payload = json.loads(json.dumps(asset2.content_payload))
    payload["sections"][0]["source_refs"][0]["source_id"] = "forged"
    normalized, content_hash = canonicalize_asset_content(payload)
    asset2.content_payload = normalized
    asset2.content_hash = content_hash
    review2.reviewed_content_hash = content_hash
    db.commit()
    with pytest.raises(P3ExportServiceError) as grounding:
        P3ExportService(db, storage=storage).create_export(
            project_id=project2.id,
            asset_version_id=asset2.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="grounding_drift",
            actor_role="admin",
            request_id="grounding_drift_request",
        )
    assert grounding.value.code == "P3_EXPORT_GROUNDING_INVALID"
    assert db.query(P3ExportJob).count() == 0


def test_source_manifest_drift_is_rejected_before_job(db, storage):
    project, _source, asset, review = _published(
        db,
        suffix="manifest_drift",
    )
    asset.source_manifest_hash = "1" * 64
    review.reviewed_source_manifest_hash = asset.source_manifest_hash
    db.commit()
    with pytest.raises(P3ExportServiceError) as caught:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="manifest_drift_key",
            actor_role="admin",
            request_id="manifest_drift_request",
        )
    assert caught.value.code == "P3_EXPORT_SOURCE_EVIDENCE_CHANGED"
    assert db.query(P3ExportJob).count() == 0


def test_admin_only_and_unsupported_format_create_no_job(db, storage):
    project, _source, asset, _review = _published(db, suffix="role_format")
    service = P3ExportService(db, storage=storage)
    with pytest.raises(P3ExportServiceError) as role:
        service.create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="role_denied",
            actor_role="reviewer",
            request_id="role_denied_request",
        )
    assert role.value.code == "P3_EXPORT_ROLE_FORBIDDEN"
    with pytest.raises(P3ExportServiceError) as format_error:
        service.create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format="xml",
            idempotency_key="format_denied",
            actor_role="admin",
            request_id="format_denied_request",
        )
    assert format_error.value.code == "P3_EXPORT_FORMAT_UNSUPPORTED"
    assert db.query(P3ExportJob).count() == 0


def test_revoke_is_atomic_idempotent_and_retains_file(db, storage):
    *_unused, outcome = _create(db, storage, suffix="revoke")
    assert outcome.artifact is not None
    service = P3ExportService(db, storage=storage)
    kwargs = dict(
        job_id=outcome.job.id,
        idempotency_key="revoke_key",
        actor_role="admin",
        request_id="revoke_request",
    )
    first = service.revoke_export(**kwargs)
    first_time = first.job.revoked_at
    second = service.revoke_export(**kwargs)
    assert first.job.status is P3ExportJobStatus.REVOKED
    assert second.replayed is True
    assert second.job.id == first.job.id
    assert second.artifact.revoked_at is not None
    assert second.job.revoked_at == first_time
    assert storage.exists(outcome.artifact.storage_key)
    assert db.query(P3ExportArtifact).count() == 1
    create_replay = service.create_export(
        project_id=outcome.job.project_id,
        asset_version_id=outcome.job.asset_version_id,
        export_format=outcome.job.export_format,
        idempotency_key=outcome.job.idempotency_key,
        actor_role="admin",
        request_id="create_after_revoke",
    )
    assert create_replay.replayed is True
    assert create_replay.job.status is P3ExportJobStatus.REVOKED


def test_revoke_role_and_state_rules(db, storage):
    *_unused, outcome = _create(db, storage, suffix="revoke_rules")
    service = P3ExportService(db, storage=storage)
    with pytest.raises(P3ExportServiceError) as role:
        service.revoke_export(
            job_id=outcome.job.id,
            idempotency_key="revoke_role",
            actor_role="reviewer",
            request_id="revoke_role_request",
        )
    assert role.value.code == "P3_EXPORT_ROLE_FORBIDDEN"
    service.revoke_export(
        job_id=outcome.job.id,
        idempotency_key="revoke_once",
        actor_role="admin",
        request_id="revoke_once_request",
    )
    with pytest.raises(P3ExportServiceError) as state:
        service.revoke_export(
            job_id=outcome.job.id,
            idempotency_key="revoke_again_different_key",
            actor_role="admin",
            request_id="revoke_again_request",
        )
    assert state.value.code == "P3_EXPORT_JOB_STATE_INVALID"


def test_later_source_stale_does_not_rewrite_historical_artifact(db, storage):
    project, source, asset, _review, outcome = _create(
        db,
        storage,
        suffix="historical",
    )
    assert outcome.artifact is not None
    original_hash = outcome.artifact.artifact_sha256
    original_manifest = outcome.artifact.export_manifest_hash
    with storage.open_read(outcome.artifact.storage_key) as handle:
        original = handle.read()
    source.source_stale = True
    db.commit()
    artifact = get_export_artifact_by_job_id(db, outcome.job.id)
    assert artifact.artifact_sha256 == original_hash
    assert artifact.export_manifest_hash == original_manifest
    with storage.open_read(artifact.storage_key) as handle:
        assert handle.read() == original
    with pytest.raises(P3ExportServiceError) as caught:
        P3ExportService(db, storage=storage).create_export(
            project_id=project.id,
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            idempotency_key="historical_new_export",
            actor_role="admin",
            request_id="historical_new_request",
        )
    assert caught.value.code == "P3_EXPORT_SOURCE_STALE"


def test_list_jobs_has_fixed_query_count(db, storage):
    for index in range(3):
        _create(db, storage, suffix=f"query_count_{index}")
    statements: list[str] = []

    @event.listens_for(db.bind, "before_cursor_execute")
    def count_queries(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    try:
        page = list_export_jobs(db, limit=100, offset=0)
    finally:
        event.remove(db.bind, "before_cursor_execute", count_queries)
    assert page.total == 3
    assert len(page.items) == 3
    assert len(statements) == 2


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is not configured",
)
def test_postgresql_export_idempotency_and_revoke_transaction():
    from scripts.test_environment import require_test_database_url

    url = require_test_database_url(TEST_DATABASE_URL)
    engine = create_engine(url)
    try:
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=Session,
        )
        with Session(engine, expire_on_commit=False) as session:
            project, _source, asset, review = _published(
                session,
                suffix="postgres_export",
            )
            service = P3ExportService(
                session,
                storage=LocalFilesystemP3ExportStorage(
                    ROOT_DIR / ".local-data" / "p3-test-postgres-export"
                ),
            )
            fingerprint = service._request_fingerprint(
                project=project,
                asset=asset,
                review=review,
                export_format=P3ExportFormat.JSONL,
            )
            project_id = project.id
            asset_id = asset.id
        barrier = Barrier(2)

        def create_concurrently():
            with factory() as thread_session:
                barrier.wait()
                result = create_pending_export_job(
                    thread_session,
                    project_id=project_id,
                    asset_version_id=asset_id,
                    export_format=P3ExportFormat.JSONL,
                    export_policy_version=P3_EXPORT_POLICY_VERSION,
                    requested_by_role="admin",
                    request_id="postgres_request",
                    idempotency_key="postgres_export_key",
                    request_fingerprint=fingerprint,
                )
                return result.job.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            job_ids = list(
                executor.map(
                    lambda _index: create_concurrently(),
                    range(2),
                )
            )
        assert len(set(job_ids)) == 1
        with factory() as assertion_session:
            assert assertion_session.query(P3ExportJob).count() == 1
            assert get_export_job_by_id(
                assertion_session,
                job_ids[0],
            ).status is P3ExportJobStatus.PENDING
    finally:
        engine.dispose()
