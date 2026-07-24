"""Stable schemas for P3 governed-source eligibility decisions."""

from enum import Enum

from pydantic import BaseModel, Field


P3_SOURCE_ELIGIBILITY_POLICY_VERSION = "p3-source-eligibility-v1"


class P3SourceType(str, Enum):
    """Governed source types accepted by P3 v1."""

    P1_KNOWLEDGE = "P1_KNOWLEDGE"
    P2_KNOWLEDGE_ASSET = "P2_KNOWLEDGE_ASSET"
    APPROVED_BAD_CASE_CORRECTION = "APPROVED_BAD_CASE_CORRECTION"


class P3SourceEligibilityReason(str, Enum):
    """Centralized, stable reason codes for source decisions."""

    ELIGIBLE = "ELIGIBLE"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_TYPE_UNSUPPORTED = "SOURCE_TYPE_UNSUPPORTED"
    SOURCE_NOT_APPROVED = "SOURCE_NOT_APPROVED"
    SOURCE_ARCHIVED = "SOURCE_ARCHIVED"
    SOURCE_SUPERSEDED = "SOURCE_SUPERSEDED"
    SOURCE_NOT_CURRENT = "SOURCE_NOT_CURRENT"
    SOURCE_FINGERPRINT_MISMATCH = "SOURCE_FINGERPRINT_MISMATCH"
    SOURCE_TRACE_INCOMPLETE = "SOURCE_TRACE_INCOMPLETE"
    RAW_BAD_CASE_NOT_ALLOWED = "RAW_BAD_CASE_NOT_ALLOWED"
    BAD_CASE_CORRECTION_NOT_APPROVED = "BAD_CASE_CORRECTION_NOT_APPROVED"
    SOURCE_STATE_INVALID = "SOURCE_STATE_INVALID"


class P3SourceReference(BaseModel):
    """Caller-supplied stable identity and optional optimistic guards."""

    source_type: P3SourceType
    source_id: str = Field(min_length=1, max_length=200)
    source_version: int | None = Field(default=None, ge=1)
    expected_fingerprint: str | None = Field(default=None, min_length=1, max_length=128)


class P3SourceEligibilityDecision(BaseModel):
    """Safe, deterministic result of one read-only eligibility check."""

    source_type: str
    source_id: str
    eligible: bool
    reason_code: P3SourceEligibilityReason
    source_status: str | None = None
    source_version: int | None = None
    content_fingerprint: str | None = None
    approved_review_id: str | None = None
    snapshot_id: str | None = None
    knowledge_asset_id: str | None = None
    lineage_complete: bool = False
    checked_conditions: list[str] = Field(default_factory=list)
    policy_version: str = P3_SOURCE_ELIGIBILITY_POLICY_VERSION
