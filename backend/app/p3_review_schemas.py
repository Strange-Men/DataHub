"""Stable P3 manual-revision and human-review contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseReviewDecision,
)


P3_REVIEW_POLICY_VERSION = "p3-review-v1"


class _FrozenReviewSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class P3ReviewChecklist(_FrozenReviewSchema):
    """Role-level human conclusions required by review policy v1."""

    structure_complete: bool
    source_refs_valid: bool
    no_unsupported_claims_confirmed: bool
    safe_for_reuse: bool

    @property
    def all_confirmed(self) -> bool:
        return all(
            (
                self.structure_complete,
                self.source_refs_valid,
                self.no_unsupported_claims_confirmed,
                self.safe_for_reuse,
            )
        )


class P3ReviewDecisionPayload(_FrozenReviewSchema):
    """Validated final decision without audit fields supplied by the caller."""

    decision: ReuseReviewDecision
    comments: str | None = None
    checklist: P3ReviewChecklist

    @field_validator("comments")
    @classmethod
    def normalize_comments(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def enforce_policy(self) -> "P3ReviewDecisionPayload":
        if (
            self.decision is ReuseReviewDecision.APPROVED
            and not self.checklist.all_confirmed
        ):
            raise ValueError(
                "approved requires every p3-review-v1 checklist item."
            )
        if (
            self.decision
            in (
                ReuseReviewDecision.NEEDS_REVISION,
                ReuseReviewDecision.REJECTED,
            )
            and self.comments is None
        ):
            raise ValueError(
                "needs_revision and rejected decisions require comments."
            )
        return self


class _ReviewApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class P3ManualRevisionRequest(_ReviewApiRequest):
    content_payload: dict[str, object]
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3SubmitReviewRequest(_ReviewApiRequest):
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )


class P3ReviewDecisionRequest(_ReviewApiRequest):
    decision: ReuseReviewDecision
    comments: str | None = Field(default=None, max_length=10_000)
    checklist: P3ReviewChecklist
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3ReviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_version_id: str
    decision: ReuseReviewDecision
    comments: str | None
    checklist_payload: dict[str, object]
    review_policy_version: str
    reviewed_content_hash: str
    reviewed_source_manifest_hash: str
    reviewer_role: str
    request_id: str
    created_at: datetime


class P3ReviewPageData(BaseModel):
    items: list[P3ReviewView]
    total: int
    limit: int
    offset: int


class P3ReviewResponse(BaseModel):
    success: Literal[True] = True
    data: P3ReviewView
    requestId: str


class P3ReviewPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3ReviewPageData
    requestId: str


__all__ = [
    "P3_REVIEW_POLICY_VERSION",
    "P3ManualRevisionRequest",
    "P3ReviewChecklist",
    "P3ReviewDecisionRequest",
    "P3ReviewDecisionPayload",
    "P3ReviewPageData",
    "P3ReviewPageResponse",
    "P3ReviewResponse",
    "P3ReviewView",
    "P3SubmitReviewRequest",
]
