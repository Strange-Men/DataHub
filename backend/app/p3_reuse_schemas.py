"""Service-layer contracts for P3 project/source orchestration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.p3_source_eligibility_schemas import P3SourceEligibilityReason


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
