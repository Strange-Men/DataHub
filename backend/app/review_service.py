"""P2-M3 orchestration for human decisions and immutable snapshots."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.asset_repositories import get_asset
from app.extraction_repositories import get_asset_extraction
from app.review_repositories import (
    PendingReviewConflict,
    ReviewRowNotFound,
    ReviewTransitionConflict,
    create_extraction_review,
    finalize_extraction_review,
    get_extraction_review,
)
from app.review_schemas import ExtractionReviewRecord, ReviewSubmissionResult


class ReviewAssetNotFoundError(RuntimeError):
    pass


class ReviewExtractionNotFoundError(RuntimeError):
    pass


class ReviewExtractionAssetMismatchError(RuntimeError):
    pass


class ReviewNotFoundError(RuntimeError):
    pass


class ReviewStateError(RuntimeError):
    def __init__(self, message: str, *, current_status: str | None = None) -> None:
        super().__init__(message)
        self.current_status = current_status


class ReviewService:
    """Creates review tasks and atomically records terminal human decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_review(
        self,
        *,
        asset_id: str,
        extraction_id: str,
        reviewer: str | None = None,
    ) -> ExtractionReviewRecord:
        if get_asset(self.db, asset_id) is None:
            raise ReviewAssetNotFoundError(asset_id)
        extraction = get_asset_extraction(self.db, extraction_id)
        if extraction is None:
            raise ReviewExtractionNotFoundError(extraction_id)
        if extraction.asset_id != asset_id:
            raise ReviewExtractionAssetMismatchError(extraction_id)
        normalized_reviewer = reviewer.strip() if reviewer and reviewer.strip() else None
        return create_extraction_review(
            self.db,
            asset_id=asset_id,
            extraction_id=extraction.id,
            original_content=extraction.content,
            reviewer=normalized_reviewer,
        )

    def get_review(self, review_id: str) -> ExtractionReviewRecord:
        review = get_extraction_review(self.db, review_id)
        if review is None:
            raise ReviewNotFoundError(review_id)
        return review

    def submit_review(
        self,
        review_id: str,
        *,
        review_status: str,
        reviewer: str,
        review_comment: str | None = None,
        revised_content: str | None = None,
    ) -> ReviewSubmissionResult:
        if review_status not in {"approved", "rejected", "needs_revision"}:
            raise ReviewStateError("Unsupported review decision.")
        normalized_reviewer = reviewer.strip()
        if not normalized_reviewer:
            raise ReviewStateError("Reviewer is required.")

        review = self.get_review(review_id)
        extraction = get_asset_extraction(self.db, review.extraction_id)
        if extraction is None:
            raise ReviewExtractionNotFoundError(review.extraction_id)
        if extraction.asset_id != review.asset_id:
            raise ReviewExtractionAssetMismatchError(extraction.id)

        normalized_comment = (
            review_comment.strip() if review_comment and review_comment.strip() else None
        )
        normalized_revised = revised_content.strip() if revised_content is not None else None
        approved_content: str | None = None
        if review_status == "approved":
            approved_content = (
                normalized_revised
                if normalized_revised is not None
                else review.original_content
            )
            if not approved_content:
                raise ReviewStateError("Approved content cannot be empty.")

        try:
            return finalize_extraction_review(
                self.db,
                review_id=review.id,
                review_status=review_status,
                reviewer=normalized_reviewer,
                review_comment=normalized_comment,
                revised_content=normalized_revised,
                extract_type=extraction.extract_type,
                approved_content=approved_content,
            )
        except ReviewRowNotFound as exc:
            raise ReviewNotFoundError(review_id) from exc
        except ReviewTransitionConflict as exc:
            raise ReviewStateError(
                "Only pending reviews can receive a decision.",
                current_status=exc.current_status,
            ) from exc


__all__ = [
    "PendingReviewConflict",
    "ReviewAssetNotFoundError",
    "ReviewExtractionAssetMismatchError",
    "ReviewExtractionNotFoundError",
    "ReviewNotFoundError",
    "ReviewService",
    "ReviewStateError",
]
