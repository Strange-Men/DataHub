"""Focused P3-M7.1 Export Job/Artifact schema and storage tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.p3_export_models import (
    P3ExportArtifact,
    P3ExportFormat,
    P3ExportJob,
    P3ExportJobStatus,
)
from app.p3_export_storage import (
    LocalFilesystemP3ExportStorage,
    P3ExportStorageError,
    get_p3_export_storage,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
)
from scripts.test_environment import require_test_database_url


EXPECTED_P3_TABLES = {
    "reuse_projects",
    "reuse_source_items",
    "reuse_asset_versions",
    "reuse_asset_version_sources",
    "reuse_reviews",
    "export_jobs",
    "export_artifacts",
}
TEST_DATABASE_URL = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()


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
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _project(db: Session, project_id: str = "m71_project") -> ReuseProject:
    row = ReuseProject(
        id=project_id,
        name="M7.1 export schema",
        description=None,
        status=ReuseProjectStatus.ACTIVE,
        created_by_role="cleaner",
        request_id=f"request_{project_id}",
        idempotency_key=f"key_{project_id}",
    )
    db.add(row)
    db.commit()
    return row


def _asset(
    db: Session,
    project: ReuseProject,
    asset_id: str = "m71_asset",
) -> ReuseAssetVersion:
    row = ReuseAssetVersion(
        id=asset_id,
        project_id=project.id,
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        version_number=1,
        status=ReuseAssetVersionStatus.PUBLISHED,
        generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
        template_key="p3.training_material.v1",
        template_version="v1",
        content_payload={},
        content_hash="a" * 64,
        source_manifest_hash="b" * 64,
        idempotency_key=f"key_{asset_id}",
        created_by_role="cleaner",
        request_id=f"request_{asset_id}",
    )
    db.add(row)
    db.commit()
    return row


def _job(
    db: Session,
    project: ReuseProject,
    asset: ReuseAssetVersion,
    *,
    job_id: str = "m71_job",
    export_format: P3ExportFormat = P3ExportFormat.JSONL,
    status: P3ExportJobStatus = P3ExportJobStatus.PENDING,
) -> P3ExportJob:
    row = P3ExportJob(
        id=job_id,
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=export_format,
        status=status,
        export_policy_version="p3-export-v1",
        requested_by_role="admin",
        request_id=f"request_{job_id}",
        idempotency_key=f"key_{job_id}",
        request_fingerprint="c" * 64,
    )
    db.add(row)
    db.commit()
    return row


def _artifact(
    db: Session,
    job: P3ExportJob,
    asset: ReuseAssetVersion,
    *,
    artifact_id: str = "m71_artifact",
    storage_key: str = "m71/job/data.jsonl",
) -> P3ExportArtifact:
    row = P3ExportArtifact(
        id=artifact_id,
        export_job_id=job.id,
        asset_version_id=asset.id,
        export_format=job.export_format,
        storage_backend="local_filesystem",
        storage_key=storage_key,
        safe_file_name="training-material-v1.jsonl",
        content_type="application/x-ndjson",
        encoding="utf-8",
        byte_size=10,
        row_count=1,
        artifact_sha256="d" * 64,
        export_manifest_hash="e" * 64,
    )
    db.add(row)
    db.commit()
    return row


def test_empty_database_creates_exactly_seven_p3_tables() -> None:
    engine = _engine()
    try:
        Base.metadata.create_all(bind=engine)
        tables = set(inspect(engine).get_table_names())
        assert EXPECTED_P3_TABLES <= tables
        assert not {
            "export_manifests",
            "export_files",
            "p3_export_rows",
        } & tables
    finally:
        engine.dispose()


def test_repeat_create_all_is_idempotent_and_preserves_old_p3_rows() -> None:
    engine = _engine()
    try:
        old_tables = [
            table
            for name, table in Base.metadata.tables.items()
            if name.startswith("reuse_")
        ]
        Base.metadata.create_all(bind=engine, tables=old_tables)
        with Session(engine) as db:
            project = _project(db, "legacy_project")
            asset = _asset(db, project, "legacy_asset")
            before = (project.id, asset.content_hash, asset.source_manifest_hash)
        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with Session(engine) as db:
            project = db.get(ReuseProject, "legacy_project")
            asset = db.get(ReuseAssetVersion, "legacy_asset")
            assert project is not None and asset is not None
            assert (project.id, asset.content_hash, asset.source_manifest_hash) == before
        assert EXPECTED_P3_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.parametrize("export_format", list(P3ExportFormat))
def test_both_export_formats_persist(
    db: Session,
    export_format: P3ExportFormat,
) -> None:
    project = _project(db, f"project_{export_format.value}")
    asset = _asset(db, project, f"asset_{export_format.value}")
    row = _job(
        db,
        project,
        asset,
        job_id=f"job_{export_format.value}",
        export_format=export_format,
    )
    assert row.export_format is export_format


@pytest.mark.parametrize("status", list(P3ExportJobStatus))
def test_all_job_statuses_persist(
    db: Session,
    status: P3ExportJobStatus,
) -> None:
    project = _project(db, f"project_{status.value}")
    asset = _asset(db, project, f"asset_{status.value}")
    row = _job(
        db,
        project,
        asset,
        job_id=f"job_{status.value}",
        status=status,
    )
    assert row.status is status


def test_invalid_format_and_status_are_rejected(db: Session) -> None:
    project = _project(db)
    asset = _asset(db, project)
    for field, value in (("export_format", "xml"), ("status", "complete")):
        payload = {
            "id": f"invalid_{field}",
            "project_id": project.id,
            "asset_version_id": asset.id,
            "export_format": P3ExportFormat.JSONL,
            "status": P3ExportJobStatus.PENDING,
            "export_policy_version": "p3-export-v1",
            "requested_by_role": "admin",
            "request_id": f"request_{field}",
            "idempotency_key": f"key_{field}",
            "request_fingerprint": "f" * 64,
        }
        payload[field] = value
        db.add(P3ExportJob(**payload))
        with pytest.raises(
            (LookupError, ValueError, IntegrityError, StatementError)
        ):
            db.commit()
        db.rollback()


def test_job_keys_artifact_job_and_storage_key_are_unique(db: Session) -> None:
    project = _project(db)
    asset = _asset(db, project)
    first = _job(db, project, asset)
    duplicate = P3ExportJob(
        id="duplicate_job",
        project_id=project.id,
        asset_version_id=asset.id,
        export_format=P3ExportFormat.CSV,
        status=P3ExportJobStatus.PENDING,
        export_policy_version="p3-export-v1",
        requested_by_role="admin",
        request_id="duplicate_request",
        idempotency_key=first.idempotency_key,
        request_fingerprint="f" * 64,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    first_artifact = _artifact(db, first, asset)
    for artifact_id, job_id, key in (
        ("duplicate_job_artifact", first.id, "other/key.jsonl"),
        ("duplicate_key_artifact", "second_job", first_artifact.storage_key),
    ):
        job = first
        if job_id == "second_job":
            job = _job(db, project, asset, job_id=job_id)
        db.add(
            P3ExportArtifact(
                id=artifact_id,
                export_job_id=job.id,
                asset_version_id=asset.id,
                export_format=P3ExportFormat.JSONL,
                storage_backend="local_filesystem",
                storage_key=key,
                safe_file_name="file.jsonl",
                content_type="application/x-ndjson",
                encoding="utf-8",
                byte_size=1,
                row_count=1,
                artifact_sha256="a" * 64,
                export_manifest_hash="b" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_nonblank_hashes_and_nonnegative_sizes_are_enforced(db: Session) -> None:
    project = _project(db)
    asset = _asset(db, project)
    job = _job(db, project, asset)
    for field, value in (
        ("artifact_sha256", ""),
        ("export_manifest_hash", ""),
        ("byte_size", -1),
        ("row_count", -1),
    ):
        payload = {
            "id": f"invalid_{field}",
            "export_job_id": job.id,
            "asset_version_id": asset.id,
            "export_format": P3ExportFormat.JSONL,
            "storage_backend": "local_filesystem",
            "storage_key": f"invalid/{field}.jsonl",
            "safe_file_name": "file.jsonl",
            "content_type": "application/x-ndjson",
            "encoding": "utf-8",
            "byte_size": 1,
            "row_count": 1,
            "artifact_sha256": "a" * 64,
            "export_manifest_hash": "b" * 64,
        }
        payload[field] = value
        db.add(P3ExportArtifact(**payload))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_foreign_keys_restrict_and_no_cascade_delete(db: Session) -> None:
    project = _project(db)
    asset = _asset(db, project)
    job = _job(db, project, asset)
    artifact = _artifact(db, job, asset)
    for row in (asset, project, job):
        db.delete(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert db.get(P3ExportJob, job.id) is not None
    assert db.get(P3ExportArtifact, artifact.id) is not None


def test_missing_job_project_and_asset_foreign_keys_fail(db: Session) -> None:
    project = _project(db)
    asset = _asset(db, project)
    bad_job = P3ExportJob(
        id="missing_fks",
        project_id="missing_project",
        asset_version_id="missing_asset",
        export_format=P3ExportFormat.JSONL,
        status=P3ExportJobStatus.PENDING,
        export_policy_version="p3-export-v1",
        requested_by_role="admin",
        request_id="missing_request",
        idempotency_key="missing_key",
        request_fingerprint="f" * 64,
    )
    db.add(bad_job)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    job = _job(db, project, asset)
    db.add(
        P3ExportArtifact(
            id="missing_job_artifact",
            export_job_id="missing_job",
            asset_version_id=asset.id,
            export_format=P3ExportFormat.JSONL,
            storage_backend="local_filesystem",
            storage_key="missing/job.jsonl",
            safe_file_name="file.jsonl",
            content_type="application/x-ndjson",
            encoding="utf-8",
            byte_size=1,
            row_count=1,
            artifact_sha256="a" * 64,
            export_manifest_hash="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.get(P3ExportJob, job.id) is not None


def test_storage_atomic_write_read_exists_and_stat(tmp_path: Path) -> None:
    storage = LocalFilesystemP3ExportStorage(tmp_path)
    payload = b'{"instruction":"safe"}\n'
    stored = storage.write_atomic("job-1/data.jsonl", payload)
    assert stored.storage_backend == "local_filesystem"
    assert stored.storage_key == "job-1/data.jsonl"
    assert stored.byte_size == len(payload)
    assert storage.exists(stored.storage_key)
    with storage.open_read(stored.storage_key) as handle:
        assert handle.read() == payload
    stat = storage.stat(stored.storage_key)
    assert stat.byte_size == len(payload)
    assert not list(tmp_path.rglob(".p3-export-*"))


def test_storage_failure_leaves_no_formal_or_temporary_file(
    tmp_path: Path,
) -> None:
    storage = LocalFilesystemP3ExportStorage(tmp_path)
    with patch("app.p3_export_storage.os.replace", side_effect=OSError):
        with pytest.raises(P3ExportStorageError):
            storage.write_atomic("job-2/data.csv", b"safe")
    assert not (tmp_path / "job-2" / "data.csv").exists()
    assert not list(tmp_path.rglob(".p3-export-*"))


@pytest.mark.parametrize(
    "key",
    (
        "",
        "../outside.jsonl",
        "job/../../outside.csv",
        "/absolute.jsonl",
        r"C:\absolute.csv",
    ),
)
def test_storage_rejects_traversal_and_absolute_paths(
    tmp_path: Path,
    key: str,
) -> None:
    storage = LocalFilesystemP3ExportStorage(tmp_path)
    with pytest.raises(P3ExportStorageError):
        storage.write_atomic(key, b"safe")


def test_storage_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable in this environment.")
    storage = LocalFilesystemP3ExportStorage(root)
    with pytest.raises(P3ExportStorageError):
        storage.write_atomic("escape/data.jsonl", b"safe")
    assert not (outside / "data.jsonl").exists()


def test_default_storage_root_is_ignored_and_configurable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P3_EXPORT_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("P3_EXPORT_STORAGE_BACKEND", "local_filesystem")
    storage = get_p3_export_storage()
    assert isinstance(storage, LocalFilesystemP3ExportStorage)
    assert storage.root == tmp_path.resolve()
    root = Path(__file__).resolve().parents[2]
    ignored = subprocess.run(
        ["git", "check-ignore", ".local-data/p3-exports/probe.jsonl"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0


def test_no_physical_delete_or_sensitive_content_fields_exist() -> None:
    storage_source = Path(
        LocalFilesystemP3ExportStorage.__module__.replace(".", "/")
    )
    del storage_source
    assert not hasattr(LocalFilesystemP3ExportStorage, "delete")
    job_columns = set(P3ExportJob.__table__.columns.keys())
    artifact_columns = set(P3ExportArtifact.__table__.columns.keys())
    forbidden = {
        "token",
        "token_hash",
        "api_key",
        "password",
        "content_payload",
        "file_content",
        "vector",
    }
    assert not forbidden & job_columns
    assert not forbidden & artifact_columns


@pytest.mark.postgres_integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="DATAHUB_TEST_DATABASE_URL is not configured",
)
def test_postgresql_export_constraints_and_repeat_create_all() -> None:
    url = require_test_database_url(TEST_DATABASE_URL)
    engine = create_engine(url)
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with Session(engine, expire_on_commit=False) as db:
            project = _project(db, "pg_m71_project")
            asset = _asset(db, project, "pg_m71_asset")
            job = _job(db, project, asset, job_id="pg_m71_job")
            artifact = _artifact(
                db,
                job,
                asset,
                artifact_id="pg_m71_artifact",
                storage_key="pg/job/data.jsonl",
            )
            assert db.get(P3ExportArtifact, artifact.id) is not None
            db.add(
                P3ExportArtifact(
                    id="pg_duplicate",
                    export_job_id=job.id,
                    asset_version_id=asset.id,
                    export_format=P3ExportFormat.JSONL,
                    storage_backend="local_filesystem",
                    storage_key="pg/job/other.jsonl",
                    safe_file_name="other.jsonl",
                    content_type="application/x-ndjson",
                    encoding="utf-8",
                    byte_size=1,
                    row_count=1,
                    artifact_sha256="a" * 64,
                    export_manifest_hash="b" * 64,
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        assert EXPECTED_P3_TABLES <= set(inspect(engine).get_table_names())
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
