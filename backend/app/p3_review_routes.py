"""HTTP API for P3 manual revision and human review with centralized RBAC."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Permission, Principal, require_permission
from app.database import get_db
from app.p3_asset_schemas import (
    P3AssetVersionResponse,
    P3AssetVersionView,
)
from app.p3_review_schemas import (
    P3ManualRevisionRequest,
    P3ReviewDecisionRequest,
    P3ReviewPageData,
    P3ReviewPageResponse,
    P3ReviewResponse,
    P3ReviewView,
    P3SubmitReviewRequest,
)
from app.p3_review_service import P3ReviewService, P3ReviewServiceError
from app.p3_reuse_models import ReuseAssetType, ReuseReviewDecision


router = APIRouter(
    prefix="/api/p3/reuse-projects",
    tags=["P3 Manual Revision and Review"],
)
_T = TypeVar("_T")


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _http_error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


_ERROR_STATUS = {
    "P3_REVIEW_ASSET_NOT_FOUND": 404,
    "P3_REVIEW_PROJECT_NOT_ACTIVE": 409,
    "P3_REVIEW_PARENT_STATE_INVALID": 409,
    "P3_REVIEW_ASSET_STATE_INVALID": 409,
    "P3_REVIEW_CONTENT_INVALID": 422,
    "P3_REVIEW_CONTENT_HASH_MISMATCH": 409,
    "P3_REVIEW_SOURCE_STALE": 409,
    "P3_REVIEW_SOURCE_EVIDENCE_CHANGED": 409,
    "P3_REVIEW_SOURCE_REF_INVALID": 422,
    "P3_REVIEW_GROUNDING_INCOMPLETE": 422,
    "P3_REVIEW_CHECKLIST_INVALID": 422,
    "P3_REVIEW_COMMENTS_REQUIRED": 422,
    "P3_REVIEW_ALREADY_DECIDED": 409,
    "P3_REVIEW_IDEMPOTENCY_CONFLICT": 409,
    "P3_REVIEW_STORAGE_UNAVAILABLE": 503,
}


def _service_call(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except P3ReviewServiceError as exc:
        raise _http_error(
            _ERROR_STATUS.get(exc.code, 500),
            exc.code,
            exc.message,
            exc.context,
        ) from exc
    except Exception as exc:
        raise _http_error(
            500,
            "P3_REVIEW_INTERNAL_ERROR",
            "P3 review operation failed safely.",
        ) from exc


def _version_response(
    version: object,
    request_id: str,
) -> P3AssetVersionResponse:
    return P3AssetVersionResponse(
        data=P3AssetVersionView.model_validate(version),
        requestId=request_id,
    )


def _review_response(
    review: object,
    request_id: str,
) -> P3ReviewResponse:
    return P3ReviewResponse(
        data=P3ReviewView.model_validate(review),
        requestId=request_id,
    )


@router.post(
    "/{project_id}/assets/{asset_version_id}/revisions",
    response_model=P3AssetVersionResponse,
    status_code=201,
)
def create_manual_revision(
    project_id: str,
    asset_version_id: str,
    payload: P3ManualRevisionRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_EDIT)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionResponse:
    request_id = _request_id()
    version = _service_call(
        lambda: P3ReviewService(db).create_manual_revision(
            project_id=project_id,
            parent_asset_version_id=asset_version_id,
            content_payload=payload.content_payload,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    return _version_response(version, request_id)


@router.post(
    "/{project_id}/assets/{asset_version_id}/submit-review",
    response_model=P3AssetVersionResponse,
)
def submit_review(
    project_id: str,
    asset_version_id: str,
    payload: P3SubmitReviewRequest,
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_SUBMIT_REVIEW)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionResponse:
    request_id = _request_id()
    version = _service_call(
        lambda: P3ReviewService(db).submit_for_review(
            project_id=project_id,
            asset_version_id=asset_version_id,
            idempotency_key=payload.idempotency_key,
        )
    )
    return _version_response(version, request_id)


@router.post(
    "/{project_id}/assets/{asset_version_id}/review",
    response_model=P3ReviewResponse,
    status_code=201,
)
def decide_review(
    project_id: str,
    asset_version_id: str,
    payload: P3ReviewDecisionRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_REVIEW_DECIDE)
    ),
    db: Session = Depends(get_db),
) -> P3ReviewResponse:
    request_id = _request_id()
    review = _service_call(
        lambda: P3ReviewService(db).decide_review(
            project_id=project_id,
            asset_version_id=asset_version_id,
            decision=payload.decision,
            comments=payload.comments,
            checklist=payload.checklist.model_dump(mode="json"),
            idempotency_key=payload.idempotency_key,
            reviewer_role=principal.role.value,
            request_id=request_id,
        )
    )
    return _review_response(review, request_id)


@router.get(
    "/{project_id}/assets/{asset_version_id}/reviews",
    response_model=P3ReviewResponse,
)
def get_review(
    project_id: str,
    asset_version_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_REVIEW_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ReviewResponse:
    request_id = _request_id()
    review = _service_call(
        lambda: P3ReviewService(db).get_review(
            project_id=project_id,
            asset_version_id=asset_version_id,
        )
    )
    return _review_response(review, request_id)


@router.get(
    "/{project_id}/reviews",
    response_model=P3ReviewPageResponse,
)
def list_project_reviews(
    project_id: str,
    decision: ReuseReviewDecision | None = None,
    asset_type: ReuseAssetType | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(
        require_permission(Permission.P3_REVIEW_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ReviewPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3ReviewService(db).list_project_reviews(
            project_id=project_id,
            decision=decision,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
        )
    )
    return P3ReviewPageResponse(
        data=P3ReviewPageData(
            items=[
                P3ReviewView.model_validate(item)
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
        requestId=request_id,
    )


__all__ = ["router"]
