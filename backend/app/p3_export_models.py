"""P3 governed export Job and Artifact persistence models."""

from __future__ import annotations

import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base
from app.p3_reuse_models import ReuseAssetVersion, ReuseProject  # noqa: F401


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class P3ExportFormat(str, Enum):
    """Stable P3 v1 structured export formats."""

    JSONL = "jsonl"
    CSV = "csv"


class P3ExportJobStatus(str, Enum):
    """Frozen synchronous export Job lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REVOKED = "revoked"


class P3ExportJob(Base):
    """Audited request to export one governed published Asset Version."""

    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint(
            "length(trim(export_policy_version)) > 0",
            name="ck_export_jobs_policy_not_blank",
        ),
        CheckConstraint(
            "length(trim(request_fingerprint)) > 0",
            name="ck_export_jobs_fingerprint_not_blank",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_export_jobs_idempotency_key",
        ),
        UniqueConstraint(
            "revoke_idempotency_key",
            name="uq_export_jobs_revoke_idempotency_key",
        ),
    )

    id = Column(String(200), primary_key=True)
    project_id = Column(
        String(200),
        ForeignKey("reuse_projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_version_id = Column(
        String(200),
        ForeignKey("reuse_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    export_format = Column(
        SqlEnum(
            P3ExportFormat,
            name="p3_export_format",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    status = Column(
        SqlEnum(
            P3ExportJobStatus,
            name="p3_export_job_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=P3ExportJobStatus.PENDING.value,
        index=True,
    )
    export_policy_version = Column(String(100), nullable=False)
    requested_by_role = Column(String(50), nullable=False)
    request_id = Column(String(200), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_fingerprint = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_role = Column(String(50), nullable=True)
    revoke_request_id = Column(String(200), nullable=True)
    revoke_idempotency_key = Column(String(200), nullable=True)
    failure_code = Column(String(100), nullable=True)
    failure_message = Column(Text, nullable=True)


class P3ExportArtifact(Base):
    """Immutable metadata for one locally stored governed export file."""

    __tablename__ = "export_artifacts"
    __table_args__ = (
        CheckConstraint(
            "length(trim(storage_backend)) > 0",
            name="ck_export_artifacts_backend_not_blank",
        ),
        CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_export_artifacts_storage_key_not_blank",
        ),
        CheckConstraint(
            "length(trim(safe_file_name)) > 0",
            name="ck_export_artifacts_file_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(content_type)) > 0",
            name="ck_export_artifacts_content_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(encoding)) > 0",
            name="ck_export_artifacts_encoding_not_blank",
        ),
        CheckConstraint(
            "length(trim(artifact_sha256)) > 0",
            name="ck_export_artifacts_sha_not_blank",
        ),
        CheckConstraint(
            "length(trim(export_manifest_hash)) > 0",
            name="ck_export_artifacts_manifest_not_blank",
        ),
        CheckConstraint(
            "byte_size >= 0",
            name="ck_export_artifacts_byte_size_nonnegative",
        ),
        CheckConstraint(
            "row_count >= 0",
            name="ck_export_artifacts_row_count_nonnegative",
        ),
        UniqueConstraint(
            "export_job_id",
            name="uq_export_artifacts_export_job_id",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_export_artifacts_storage_key",
        ),
    )

    id = Column(String(200), primary_key=True)
    export_job_id = Column(
        String(200),
        ForeignKey("export_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_version_id = Column(
        String(200),
        ForeignKey("reuse_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    export_format = Column(
        SqlEnum(
            P3ExportFormat,
            name="p3_export_artifact_format",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    storage_backend = Column(String(50), nullable=False)
    storage_key = Column(String(500), nullable=False)
    safe_file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    encoding = Column(String(50), nullable=False)
    byte_size = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=False)
    artifact_sha256 = Column(String(128), nullable=False)
    export_manifest_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_role = Column(String(50), nullable=True)
    revoke_request_id = Column(String(200), nullable=True)


__all__ = [
    "P3ExportArtifact",
    "P3ExportFormat",
    "P3ExportJob",
    "P3ExportJobStatus",
]
