"""HTTP API for governed P3 draft assets with centralized RBAC."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Permission, Principal, require_permission
from app.database import get_db
from app.p3_asset_schemas import (
    P3AssetGenerateRequest,
    P3AssetVersionPageData,
    P3AssetVersionPageResponse,
    P3AssetVersionResponse,
    P3AssetVersionSourcePageData,
    P3AssetVersionSourcePageResponse,
    P3AssetVersionSourceView,
    P3AssetVersionView,
    P3LLMAssetGenerateRequest,
)
from app.p3_asset_service import P3AssetService, P3AssetServiceError
from app.p3_llm_draft_service import P3LLMDraftService
from app.p3_reuse_models import ReuseAssetType, ReuseAssetVersionStatus


router = APIRouter(
    prefix="/api/p3/reuse-projects",
    tags=["P3 Draft Assets"],
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
    "P3_ASSET_PROJECT_NOT_FOUND": 404,
    "P3_ASSET_NOT_FOUND": 404,
    "P3_ASSET_VALIDATION_ERROR": 422,
    "P3_ASSET_SOURCE_CONTENT_UNAVAILABLE": 422,
    "P3_ASSET_TEMPLATE_NOT_FOUND": 422,
    "P3_ASSET_TEMPLATE_INVALID": 422,
    "P3_ASSET_LIMIT_EXCEEDED": 422,
    "P3_ASSET_PROJECT_NOT_ACTIVE": 409,
    "P3_ASSET_NO_SOURCES": 409,
    "P3_ASSET_SOURCE_STALE": 409,
    "P3_ASSET_SOURCE_INELIGIBLE": 409,
    "P3_ASSET_SOURCE_EVIDENCE_CHANGED": 409,
    "P3_ASSET_IDEMPOTENCY_CONFLICT": 409,
    "P3_ASSET_STORAGE_UNAVAILABLE": 503,
    "P3_ASSET_GENERATION_FAILED": 500,
    "P3_LLM_DRAFT_DISABLED": 503,
    "P3_LLM_PROVIDER_NOT_CONFIGURED": 503,
    "P3_LLM_CONTEXT_LIMIT_EXCEEDED": 422,
    "P3_LLM_PROVIDER_TIMEOUT": 503,
    "P3_LLM_PROVIDER_UNAVAILABLE": 503,
    "P3_LLM_OUTPUT_INVALID_JSON": 502,
    "P3_LLM_OUTPUT_SCHEMA_INVALID": 502,
    "P3_LLM_UNKNOWN_SOURCE_REF": 502,
    "P3_LLM_GROUNDING_INCOMPLETE": 502,
    "P3_LLM_OUTPUT_TOO_LARGE": 502,
    "P3_LLM_GENERATION_FAILED": 502,
}


def _service_call(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except P3AssetServiceError as exc:
        raise _http_error(
            _ERROR_STATUS.get(exc.code, 500),
            exc.code,
            exc.message,
            exc.context,
        ) from exc
    except Exception as exc:
        raise _http_error(
            500,
            "P3_ASSET_INTERNAL_ERROR",
            "P3 draft asset operation failed safely.",
        ) from exc


def _version_response(
    version: object,
    request_id: str,
) -> P3AssetVersionResponse:
    return P3AssetVersionResponse(
        data=P3AssetVersionView.model_validate(version),
        requestId=request_id,
    )


@router.post(
    "/{project_id}/assets/generate",
    response_model=P3AssetVersionResponse,
    status_code=201,
)
def generate_draft_asset(
    project_id: str,
    payload: P3AssetGenerateRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_GENERATE)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionResponse:
    request_id = _request_id()
    version = _service_call(
        lambda: P3AssetService(db).generate_draft_asset(
            project_id=project_id,
            asset_type=payload.asset_type,
            template_key=payload.template_key,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    return _version_response(version, request_id)


@router.post(
    "/{project_id}/assets/generate-llm-draft",
    response_model=P3AssetVersionResponse,
    status_code=201,
)
def generate_llm_draft(
    project_id: str,
    payload: P3LLMAssetGenerateRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_GENERATE_LLM)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionResponse:
    request_id = _request_id()
    version = _service_call(
        lambda: P3LLMDraftService(db).generate_llm_draft(
            project_id=project_id,
            asset_type=payload.asset_type,
            prompt_key=payload.prompt_key,
            provider_profile=payload.provider_profile,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    return _version_response(version, request_id)


@router.get(
    "/{project_id}/assets",
    response_model=P3AssetVersionPageResponse,
)
def list_draft_assets(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    asset_type: ReuseAssetType | None = None,
    status: ReuseAssetVersionStatus | None = None,
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_READ)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3AssetService(db).list_project_asset_versions(
            project_id=project_id,
            asset_type=asset_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    )
    return P3AssetVersionPageResponse(
        data=P3AssetVersionPageData(
            items=[
                P3AssetVersionView.model_validate(item)
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
        requestId=request_id,
    )


@router.get(
    "/{project_id}/assets/{asset_version_id}",
    response_model=P3AssetVersionResponse,
)
def get_draft_asset(
    project_id: str,
    asset_version_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_READ)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionResponse:
    request_id = _request_id()
    version = _service_call(
        lambda: P3AssetService(db).get_asset_version(
            project_id=project_id,
            asset_version_id=asset_version_id,
        )
    )
    return _version_response(version, request_id)


@router.get(
    "/{project_id}/assets/{asset_version_id}/sources",
    response_model=P3AssetVersionSourcePageResponse,
)
def list_draft_asset_sources(
    project_id: str,
    asset_version_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(
        require_permission(Permission.P3_ASSET_READ)
    ),
    db: Session = Depends(get_db),
) -> P3AssetVersionSourcePageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3AssetService(db).list_asset_version_sources(
            project_id=project_id,
            asset_version_id=asset_version_id,
            limit=limit,
            offset=offset,
        )
    )
    return P3AssetVersionSourcePageResponse(
        data=P3AssetVersionSourcePageData(
            items=[
                P3AssetVersionSourceView.model_validate(item)
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
        requestId=request_id,
    )


__all__ = ["router"]
