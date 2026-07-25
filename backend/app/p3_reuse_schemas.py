"""Service-layer contracts for P3 project/source orchestration."""

from __future__ import annotations

from enum import Enum

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.p3_reuse_models import ReuseProjectStatus
from app.p3_source_eligibility_schemas import P3SourceEligibilityReason
from app.p3_source_eligibility_schemas import P3SourceType


P3_SOURCE_TRACE_SCHEMA_VERSION = "p3-source-trace-v1"


class P3SourceEvidenceSnapshot(BaseModel):
    """Safe eligibility evidence captured from the M1.1 decision."""

    schema_version: str = P3_SOURCE_TRACE_SCHEMA_VERSION
    source_type: str
    source_id: str
    source_status: str | None = None
    source_version: int | None = None
    content_fingerprint: str
    eligibility_policy_version: str
    approved_review_id: str | None = None
    snapshot_id: str | None = None
    knowledge_asset_id: str | None = None
    lineage_complete: bool
    checked_conditions: list[str] = Field(default_factory=list)

    def manifest_payload(self) -> dict[str, object]:
        """Return only stable governance evidence used by the lineage hash."""

        return self.model_dump(
            mode="json",
            exclude={"source_status", "checked_conditions"},
        )


class P3SourceRevalidationStatus(str, Enum):
    VALID = "valid"
    STALE = "stale"
    SKIPPED_REMOVED = "skipped_removed"


class P3SourceRevalidationResult(BaseModel):
    source_item_id: str
    project_id: str
    status: P3SourceRevalidationStatus
    eligible: bool
    reason_code: P3SourceEligibilityReason
    source_stale: bool


class P3ProjectRevalidationResult(BaseModel):
    project_id: str
    results: list[P3SourceRevalidationResult]
    total: int
    limit: int


class _P3ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class P3ProjectCreateRequest(_P3ApiRequest):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3ProjectUpdateRequest(_P3ApiRequest):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def require_update(self) -> "P3ProjectUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one mutable field is required.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null.")
        return self


class P3SourceAddRequest(_P3ApiRequest):
    source_type: P3SourceType | Literal["RAW_BAD_CASE"]
    source_id: str = Field(min_length=1, max_length=200)
    source_version: int | None = Field(default=None, ge=1)
    expected_fingerprint: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )


class P3BatchRevalidationRequest(_P3ApiRequest):
    limit: int = Field(default=100, ge=1, json_schema_extra={"maximum": 100})


class P3ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    status: ReuseProjectStatus
    created_by_role: str
    request_id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class P3SourceItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_type: P3SourceType
    source_id: str
    source_version: int | None
    source_fingerprint: str
    eligibility_policy_version: str
    approved_review_id: str | None
    snapshot_id: str | None
    knowledge_asset_id: str | None
    lineage_manifest_hash: str | None
    source_trace: dict[str, object]
    selected_by_role: str
    request_id: str
    created_at: datetime
    removed_at: datetime | None
    source_stale: bool


class P3ProjectPageData(BaseModel):
    items: list[P3ProjectView]
    total: int
    limit: int
    offset: int


class P3SourceItemPageData(BaseModel):
    items: list[P3SourceItemView]
    total: int
    limit: int
    offset: int


class P3ProjectResponse(BaseModel):
    success: Literal[True] = True
    data: P3ProjectView
    requestId: str


class P3ProjectPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3ProjectPageData
    requestId: str


class P3SourceItemResponse(BaseModel):
    success: Literal[True] = True
    data: P3SourceItemView
    requestId: str


class P3SourceItemPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3SourceItemPageData
    requestId: str


class P3SourceRevalidationResponse(BaseModel):
    success: Literal[True] = True
    data: P3SourceRevalidationResult
    requestId: str


class P3ProjectRevalidationResponse(BaseModel):
    success: Literal[True] = True
    data: P3ProjectRevalidationResult
    requestId: str
