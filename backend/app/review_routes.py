"""Additive P2-M3 human review and immutable snapshot APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.asset_repositories import get_asset
from app.auth import Permission, require_permission
from app.database import get_db
from app.review_repositories import (
    PendingReviewConflict,
    list_asset_review_snapshots,
)
from app.review_schemas import (
    CreateExtractionReviewRequest,
    SubmitExtractionReviewRequest,
)
from app.review_service import (
    ReviewAssetNotFoundError,
    ReviewExtractionAssetMismatchError,
    ReviewExtractionNotFoundError,
    ReviewNotFoundError,
    ReviewService,
    ReviewStateError,
)
from app.schemas import ApiResponse


router = APIRouter(prefix="/api", tags=["P2 Human Review"])


def _request_id() -> str:
    from uuid import uuid4

    return f"req_{uuid4().hex[:12]}"


def _asset_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "ASSET_NOT_FOUND", "message": "Asset was not found."},
    )


@router.post("/assets/{asset_id}/reviews", response_model=ApiResponse, status_code=201, dependencies=[Depends(require_permission(Permission.P2_REVISE))])
def create_review(
    asset_id: str,
    request: CreateExtractionReviewRequest,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        review = ReviewService(db).create_review(
            asset_id=asset_id,
            extraction_id=request.extraction_id,
            reviewer=request.reviewer,
        )
    except ReviewAssetNotFoundError as exc:
        raise _asset_not_found() from exc
    except ReviewExtractionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EXTRACTION_NOT_FOUND",
                "message": "Extraction result was not found.",
            },
        ) from exc
    except ReviewExtractionAssetMismatchError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EXTRACTION_ASSET_MISMATCH",
                "message": "Extraction result does not belong to this Asset.",
            },
        ) from exc
    except PendingReviewConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PENDING_REVIEW_EXISTS",
                "message": "A pending review already exists for this extraction.",
                "details": {"existing_review_id": exc.review_id},
            },
        ) from exc
    return ApiResponse(success=True, data=review.model_dump(), requestId=_request_id())


@router.get("/reviews/{review_id}", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_READ))])
def get_review(review_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    try:
        review = ReviewService(db).get_review(review_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "REVIEW_NOT_FOUND", "message": "Review was not found."},
        ) from exc
    return ApiResponse(success=True, data=review.model_dump(), requestId=_request_id())


@router.patch("/reviews/{review_id}", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_REVIEW))])
def submit_review(
    review_id: str,
    request: SubmitExtractionReviewRequest,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = ReviewService(db).submit_review(
            review_id,
            review_status=request.review_status,
            reviewer=request.reviewer,
            review_comment=request.review_comment,
            revised_content=request.revised_content,
        )
    except ReviewNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "REVIEW_NOT_FOUND", "message": "Review was not found."},
        ) from exc
    except ReviewExtractionNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVIEW_SOURCE_MISSING",
                "message": "The source extraction is no longer available.",
            },
        ) from exc
    except ReviewExtractionAssetMismatchError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVIEW_SOURCE_MISMATCH",
                "message": "The review source trace is inconsistent.",
            },
        ) from exc
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=409 if exc.current_status is not None else 400,
            detail={
                "code": "INVALID_REVIEW_TRANSITION",
                "message": str(exc),
                "details": {"current_status": exc.current_status},
            },
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())


@router.get("/assets/{asset_id}/snapshots", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_READ))])
def get_asset_snapshots(
    asset_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    if get_asset(db, asset_id) is None:
        raise _asset_not_found()
    snapshots = list_asset_review_snapshots(db, asset_id)
    return ApiResponse(
        success=True,
        data=snapshots.model_dump(),
        requestId=_request_id(),
    )
