"""Stable P3 manual-revision and human-review contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.p3_reuse_models import ReuseReviewDecision


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


__all__ = [
    "P3_REVIEW_POLICY_VERSION",
    "P3ReviewChecklist",
    "P3ReviewDecisionPayload",
]
