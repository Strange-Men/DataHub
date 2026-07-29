"""Stable schemas and policy constants for governed P3 exports."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.p3_export_models import (
    P3ExportArtifact,
    P3ExportFormat,
    P3ExportJob,
    P3ExportJobStatus,
)


P3_EXPORT_POLICY_VERSION = "p3-export-v1"
P3_EXPORT_SCHEMA_VERSION = "p3-export-v1"


class P3ExportErrorCode(str, Enum):
    PROJECT_NOT_FOUND = "P3_EXPORT_PROJECT_NOT_FOUND"
    PROJECT_NOT_ACTIVE = "P3_EXPORT_PROJECT_NOT_ACTIVE"
    ASSET_NOT_FOUND = "P3_EXPORT_ASSET_NOT_FOUND"
    ASSET_NOT_PUBLISHED = "P3_EXPORT_ASSET_NOT_PUBLISHED"
    ASSET_NOT_CURRENT = "P3_EXPORT_ASSET_NOT_CURRENT"
    REVIEW_INVALID = "P3_EXPORT_REVIEW_INVALID"
    CONTENT_HASH_MISMATCH = "P3_EXPORT_CONTENT_HASH_MISMATCH"
    MANIFEST_MISMATCH = "P3_EXPORT_MANIFEST_MISMATCH"
    SOURCE_STALE = "P3_EXPORT_SOURCE_STALE"
    SOURCE_EVIDENCE_CHANGED = "P3_EXPORT_SOURCE_EVIDENCE_CHANGED"
    GROUNDING_INVALID = "P3_EXPORT_GROUNDING_INVALID"
    FORMAT_UNSUPPORTED = "P3_EXPORT_FORMAT_UNSUPPORTED"
    PAYLOAD_INVALID = "P3_EXPORT_PAYLOAD_INVALID"
    SERIALIZATION_FAILED = "P3_EXPORT_SERIALIZATION_FAILED"
    STORAGE_FAILED = "P3_EXPORT_STORAGE_FAILED"
    IDEMPOTENCY_CONFLICT = "P3_EXPORT_IDEMPOTENCY_CONFLICT"
    JOB_NOT_FOUND = "P3_EXPORT_JOB_NOT_FOUND"
    JOB_STATE_INVALID = "P3_EXPORT_JOB_STATE_INVALID"
    ARTIFACT_NOT_FOUND = "P3_EXPORT_ARTIFACT_NOT_FOUND"
    ARTIFACT_REVOKED = "P3_EXPORT_ARTIFACT_REVOKED"
    ROLE_FORBIDDEN = "P3_EXPORT_ROLE_FORBIDDEN"


class P3ExportJobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    asset_version_id: str
    export_format: P3ExportFormat
    status: P3ExportJobStatus
    export_policy_version: str
    requested_by_role: str
    request_id: str
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_role: str | None = None
    revoke_request_id: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class P3ExportJobMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    project_id: str
    asset_version_id: str
    export_format: P3ExportFormat
    status: P3ExportJobStatus
    export_policy_version: str
    requested_by_role: str
    request_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    revoked_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class P3ExportArtifactView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    export_job_id: str
    asset_version_id: str
    export_format: P3ExportFormat
    storage_backend: str
    storage_key: str
    safe_file_name: str
    content_type: str
    encoding: str
    byte_size: int
    row_count: int
    artifact_sha256: str
    export_manifest_hash: str
    created_at: datetime
    revoked_at: datetime | None = None
    revoked_by_role: str | None = None
    revoke_request_id: str | None = None


class P3ExportArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    export_job_id: str
    asset_version_id: str
    export_format: P3ExportFormat
    safe_file_name: str
    content_type: str
    encoding: str
    byte_size: int
    row_count: int
    artifact_sha256: str
    export_manifest_hash: str
    created_at: datetime
    revoked_at: datetime | None = None
    source_stale: bool
    current_reuse_eligible: bool


class P3ExportJobPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[P3ExportJobMetadata]
    total: int
    limit: int
    offset: int


class P3ExportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    export_format: P3ExportFormat
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3ExportRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=1, max_length=200)


class P3ExportJobResponse(BaseModel):
    success: Literal[True] = True
    data: P3ExportJobMetadata
    requestId: str


class P3ExportJobPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3ExportJobPage
    requestId: str


class P3ExportArtifactResponse(BaseModel):
    success: Literal[True] = True
    data: P3ExportArtifactMetadata
    requestId: str


class P3ExportDownload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    content: bytes
    safe_file_name: str
    content_type: str
    artifact_sha256: str
    byte_size: int


class P3ExportManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    export_policy_version: str
    schema_version: str
    project_id: str
    asset_version_id: str
    asset_type: str
    version_number: int
    generation_mode: str
    content_hash: str
    source_manifest_hash: str
    review_id: str
    review_policy_version: str
    export_format: str
    encoding: str
    row_count: int
    source_snapshot_refs: list[dict[str, Any]]


class P3ExportOutcome(BaseModel):
    job: P3ExportJobView
    artifact: P3ExportArtifactView | None = None
    replayed: bool = False


class P3ExportRevokeOutcome(BaseModel):
    job: P3ExportJobView
    artifact: P3ExportArtifactView
    replayed: bool = False


class P3ExportApiOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    job: P3ExportJobMetadata
    artifact: P3ExportArtifactMetadata | None = None
    replayed: bool = False


class P3ExportApiRevokeOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    job: P3ExportJobMetadata
    artifact: P3ExportArtifactMetadata
    replayed: bool = False


class P3ExportOutcomeResponse(BaseModel):
    success: Literal[True] = True
    data: P3ExportApiOutcome
    requestId: str


class P3ExportRevokeResponse(BaseModel):
    success: Literal[True] = True
    data: P3ExportApiRevokeOutcome
    requestId: str


def export_outcome(
    job: P3ExportJob,
    artifact: P3ExportArtifact | None,
    *,
    replayed: bool = False,
) -> P3ExportOutcome:
    return P3ExportOutcome(
        job=P3ExportJobView.model_validate(job),
        artifact=(
            P3ExportArtifactView.model_validate(artifact)
            if artifact is not None
            else None
        ),
        replayed=replayed,
    )


__all__ = [
    "P3_EXPORT_POLICY_VERSION",
    "P3_EXPORT_SCHEMA_VERSION",
    "P3ExportArtifactView",
    "P3ExportApiOutcome",
    "P3ExportApiRevokeOutcome",
    "P3ExportArtifactMetadata",
    "P3ExportArtifactResponse",
    "P3ExportCreateRequest",
    "P3ExportDownload",
    "P3ExportErrorCode",
    "P3ExportJobView",
    "P3ExportJobMetadata",
    "P3ExportJobPage",
    "P3ExportJobPageResponse",
    "P3ExportJobResponse",
    "P3ExportManifest",
    "P3ExportOutcome",
    "P3ExportOutcomeResponse",
    "P3ExportRevokeRequest",
    "P3ExportRevokeOutcome",
    "P3ExportRevokeResponse",
    "export_outcome",
]
