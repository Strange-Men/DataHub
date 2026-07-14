"""P2-M3 API schemas for human review and immutable approved snapshots."""

from typing import Literal

from pydantic import BaseModel, Field


ReviewStatus = Literal["pending", "approved", "rejected", "needs_revision"]
ReviewDecision = Literal["approved", "rejected", "needs_revision"]


class CreateExtractionReviewRequest(BaseModel):
    extraction_id: str = Field(min_length=1, max_length=160)
    reviewer: str | None = Field(default=None, max_length=160)


class SubmitExtractionReviewRequest(BaseModel):
    review_status: ReviewDecision
    reviewer: str = Field(min_length=1, max_length=160)
    review_comment: str | None = Field(default=None, max_length=4000)
    revised_content: str | None = Field(default=None, max_length=100000)


class ExtractionReviewRecord(BaseModel):
    id: str
    asset_id: str
    extraction_id: str
    review_status: ReviewStatus
    reviewer: str | None
    review_comment: str | None
    original_content: str
    revised_content: str | None
    version: int
    created_at: str
    updated_at: str


class AssetReviewSnapshotRecord(BaseModel):
    id: str
    asset_id: str
    extraction_id: str
    review_id: str
    extract_type: str
    original_content: str
    approved_content: str
    metadata_json: dict[str, object]
    version: int
    created_at: str


class ReviewSubmissionResult(BaseModel):
    review: ExtractionReviewRecord
    snapshot: AssetReviewSnapshotRecord | None


class AssetReviewSnapshotList(BaseModel):
    asset_id: str
    snapshots: list[AssetReviewSnapshotRecord]
