"""Transactional persistence for P2-M3 reviews and approved snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import AssetReviewSnapshot, ExtractionReview
from app.review_schemas import (
    AssetReviewSnapshotList,
    AssetReviewSnapshotRecord,
    ExtractionReviewRecord,
    ReviewSubmissionResult,
)


class PendingReviewConflict(RuntimeError):
    def __init__(self, review_id: str) -> None:
        super().__init__("A pending review already exists for this extraction.")
        self.review_id = review_id


class ReviewRowNotFound(RuntimeError):
    pass


class ReviewTransitionConflict(RuntimeError):
    def __init__(self, current_status: str) -> None:
        super().__init__(f"Review in '{current_status}' state is immutable.")
        self.current_status = current_status


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _review_record(row: ExtractionReview) -> ExtractionReviewRecord:
    return ExtractionReviewRecord(
        id=row.id,
        asset_id=row.asset_id,
        extraction_id=row.extraction_id,
        review_status=row.review_status,
        reviewer=row.reviewer,
        review_comment=row.review_comment,
        original_content=row.original_content,
        revised_content=row.revised_content,
        version=int(row.version),
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _snapshot_record(row: AssetReviewSnapshot) -> AssetReviewSnapshotRecord:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return AssetReviewSnapshotRecord(
        id=row.id,
        asset_id=row.asset_id,
        extraction_id=row.extraction_id,
        review_id=row.review_id,
        extract_type=row.extract_type,
        original_content=row.original_content,
        approved_content=row.approved_content,
        metadata_json=metadata,
        version=int(row.version),
        created_at=_iso(row.created_at),
    )


def get_extraction_review(
    db: Session,
    review_id: str,
) -> ExtractionReviewRecord | None:
    row = db.query(ExtractionReview).filter(ExtractionReview.id == review_id).first()
    return _review_record(row) if row is not None else None


def _find_pending_review(
    db: Session,
    extraction_id: str,
) -> ExtractionReview | None:
    return (
        db.query(ExtractionReview)
        .filter(
            ExtractionReview.extraction_id == extraction_id,
            ExtractionReview.review_status == "pending",
        )
        .order_by(ExtractionReview.version.desc())
        .first()
    )


def create_extraction_review(
    db: Session,
    *,
    asset_id: str,
    extraction_id: str,
    original_content: str,
    reviewer: str | None,
) -> ExtractionReviewRecord:
    existing = _find_pending_review(db, extraction_id)
    if existing is not None:
        raise PendingReviewConflict(existing.id)

    current_version = (
        db.query(func.max(ExtractionReview.version))
        .filter(ExtractionReview.extraction_id == extraction_id)
        .scalar()
    )
    now = datetime.now(UTC)
    row = ExtractionReview(
        id=f"extraction_review_{uuid4().hex[:20]}",
        asset_id=asset_id,
        extraction_id=extraction_id,
        review_status="pending",
        reviewer=reviewer,
        original_content=original_content,
        version=int(current_version or 0) + 1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = _find_pending_review(db, extraction_id)
        if raced is not None:
            raise PendingReviewConflict(raced.id)
        raise
    db.refresh(row)
    return _review_record(row)


def finalize_extraction_review(
    db: Session,
    *,
    review_id: str,
    review_status: str,
    reviewer: str,
    review_comment: str | None,
    revised_content: str | None,
    extract_type: str,
    approved_content: str | None,
) -> ReviewSubmissionResult:
    row = (
        db.query(ExtractionReview)
        .filter(ExtractionReview.id == review_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise ReviewRowNotFound(review_id)
    if row.review_status != "pending":
        raise ReviewTransitionConflict(row.review_status)

    row.review_status = review_status
    row.reviewer = reviewer
    row.review_comment = review_comment
    row.revised_content = revised_content
    row.updated_at = datetime.now(UTC)

    snapshot_row: AssetReviewSnapshot | None = None
    if review_status == "approved":
        if approved_content is None:
            raise ValueError("Approved review requires final content.")
        snapshot_row = AssetReviewSnapshot(
            id=f"asset_review_snapshot_{uuid4().hex[:20]}",
            asset_id=row.asset_id,
            extraction_id=row.extraction_id,
            review_id=row.id,
            extract_type=extract_type,
            original_content=row.original_content,
            approved_content=approved_content,
            metadata_json={
                "reviewer": reviewer,
                "review_comment": review_comment,
                "review_status": "approved",
                "immutable": True,
            },
            version=row.version,
            created_at=datetime.now(UTC),
        )
        db.add(snapshot_row)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    if snapshot_row is not None:
        db.refresh(snapshot_row)
    return ReviewSubmissionResult(
        review=_review_record(row),
        snapshot=_snapshot_record(snapshot_row) if snapshot_row is not None else None,
    )


def list_asset_review_snapshots(
    db: Session,
    asset_id: str,
) -> AssetReviewSnapshotList:
    rows = (
        db.query(AssetReviewSnapshot)
        .filter(AssetReviewSnapshot.asset_id == asset_id)
        .order_by(AssetReviewSnapshot.created_at.desc(), AssetReviewSnapshot.id.desc())
        .all()
    )
    return AssetReviewSnapshotList(
        asset_id=asset_id,
        snapshots=[_snapshot_record(row) for row in rows],
    )


def get_asset_review_snapshot(
    db: Session,
    snapshot_id: str,
) -> AssetReviewSnapshotRecord | None:
    row = (
        db.query(AssetReviewSnapshot)
        .filter(AssetReviewSnapshot.id == snapshot_id)
        .first()
    )
    return _snapshot_record(row) if row is not None else None
