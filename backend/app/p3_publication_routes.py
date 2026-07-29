"""HTTP API for governed P3 publication with centralized RBAC."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Permission, Principal, require_permission
from app.database import get_db
from app.p3_publication_schemas import (
    P3PublicationActionRequest,
    P3PublicationResponse,
    P3PublishedAssetPageResponse,
    P3PublishedAssetResponse,
)
from app.p3_publication_service import (
    P3PublicationService,
    P3PublicationServiceError,
)
from app.p3_reuse_models import ReuseAssetType


router = APIRouter(
    prefix="/api/p3/reuse-projects",
    tags=["P3 Asset Publication"],
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
    "P3_PUBLICATION_ASSET_NOT_FOUND": 404,
    "P3_PUBLICATION_PROJECT_NOT_ACTIVE": 409,
    "P3_PUBLICATION_ASSET_STATE_INVALID": 409,
    "P3_PUBLICATION_REVIEW_MISSING": 409,
    "P3_PUBLICATION_REVIEW_NOT_APPROVED": 409,
    "P3_PUBLICATION_REVIEW_HASH_MISMATCH": 409,
    "P3_PUBLICATION_CONTENT_HASH_MISMATCH": 409,
    "P3_PUBLICATION_MANIFEST_MISMATCH": 409,
    "P3_PUBLICATION_SOURCE_STALE": 409,
    "P3_PUBLICATION_SOURCE_EVIDENCE_CHANGED": 409,
    "P3_PUBLICATION_GROUNDING_INVALID": 409,
    "P3_PUBLICATION_ROLE_FORBIDDEN": 403,
    "P3_PUBLICATION_IDEMPOTENCY_CONFLICT": 409,
    "P3_PUBLICATION_ALREADY_SUPERSEDED": 409,
    "P3_PUBLICATION_ASSET_ARCHIVED": 409,
    "P3_PUBLICATION_STORAGE_UNAVAILABLE": 503,
}


def _service_call(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except P3PublicationServiceError as exc:
        raise _http_error(
            _ERROR_STATUS.get(exc.code, 500),
            exc.code,
            exc.message,
            exc.context,
        ) from exc
    except Exception as exc:
        raise _http_error(
            500,
            "P3_PUBLICATION_INTERNAL_ERROR",
            "P3 asset publication operation failed safely.",
        ) from exc


@router.post(
    "/{project_id}/assets/{asset_version_id}/publish",
    response_model=P3PublicationResponse,
)
def publish_asset(
    project_id: str,
    asset_version_id: str,
    payload: P3PublicationActionRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_PUBLISH)
    ),
    db: Session = Depends(get_db),
) -> P3PublicationResponse:
    request_id = _request_id()
    outcome = _service_call(
        lambda: P3PublicationService(db).publish_asset(
            project_id=project_id,
            asset_version_id=asset_version_id,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    return P3PublicationResponse(data=outcome, requestId=request_id)


@router.post(
    "/{project_id}/assets/{asset_version_id}/archive",
    response_model=P3PublicationResponse,
)
def archive_asset(
    project_id: str,
    asset_version_id: str,
    payload: P3PublicationActionRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_ARCHIVE)
    ),
    db: Session = Depends(get_db),
) -> P3PublicationResponse:
    request_id = _request_id()
    outcome = _service_call(
        lambda: P3PublicationService(db).archive_asset(
            project_id=project_id,
            asset_version_id=asset_version_id,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    return P3PublicationResponse(data=outcome, requestId=request_id)


@router.get(
    "/{project_id}/published-assets",
    response_model=P3PublishedAssetPageResponse,
)
def list_current_published_assets(
    project_id: str,
    asset_type: ReuseAssetType | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_READ_PUBLISHED)
    ),
    db: Session = Depends(get_db),
) -> P3PublishedAssetPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3PublicationService(db).list_current_published_assets(
            project_id=project_id,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
        )
    )
    return P3PublishedAssetPageResponse(data=page, requestId=request_id)


@router.get(
    "/{project_id}/published-assets/{asset_type}",
    response_model=P3PublishedAssetResponse,
)
def get_current_published_asset(
    project_id: str,
    asset_type: ReuseAssetType,
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_READ_PUBLISHED)
    ),
    db: Session = Depends(get_db),
) -> P3PublishedAssetResponse:
    request_id = _request_id()
    asset = _service_call(
        lambda: P3PublicationService(db).get_current_published_asset(
            project_id=project_id,
            asset_type=asset_type,
        )
    )
    return P3PublishedAssetResponse(data=asset, requestId=request_id)


__all__ = ["router"]
