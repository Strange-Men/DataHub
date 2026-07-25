"""Governed P3 reuse-project and source-selection HTTP API."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import Permission, Principal, require_permission
from app.database import get_db
from app.p3_reuse_models import ReuseProjectStatus
from app.p3_reuse_schemas import (
    P3BatchRevalidationRequest,
    P3ProjectCreateRequest,
    P3ProjectPageData,
    P3ProjectPageResponse,
    P3ProjectResponse,
    P3ProjectRevalidationResponse,
    P3ProjectUpdateRequest,
    P3ProjectView,
    P3SourceAddRequest,
    P3SourceItemPageData,
    P3SourceItemPageResponse,
    P3SourceItemResponse,
    P3SourceItemView,
    P3SourceRevalidationResponse,
)
from app.p3_reuse_service import (
    P3ProjectStateError,
    P3ReuseService,
    P3ServiceConflict,
    P3ServiceNotFound,
    P3ServiceValidationError,
    P3SourceIneligible,
    P3SourceStale,
)
from app.p3_source_eligibility_schemas import P3SourceType


router = APIRouter(prefix="/api/p3/reuse-projects", tags=["P3 Reuse Projects"])
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


def _service_call(
    operation: Callable[[], _T],
    *,
    not_found_code: str = "P3_PROJECT_NOT_FOUND",
    conflict_code: str = "P3_SOURCE_EVIDENCE_CONFLICT",
) -> _T:
    try:
        return operation()
    except P3ServiceNotFound as exc:
        raise _http_error(404, not_found_code, exc.message, exc.context) from exc
    except P3ProjectStateError as exc:
        raise _http_error(
            409,
            "P3_PROJECT_STATE_INVALID",
            exc.message,
            exc.context,
        ) from exc
    except P3SourceIneligible as exc:
        details = {**exc.context, "reason_code": exc.reason_code.value}
        raise _http_error(
            409,
            "P3_SOURCE_INELIGIBLE",
            exc.message,
            details,
        ) from exc
    except P3SourceStale as exc:
        details = {**exc.context, "reason_code": exc.reason_code.value}
        raise _http_error(409, "P3_SOURCE_STALE", exc.message, details) from exc
    except P3ServiceConflict as exc:
        raise _http_error(409, conflict_code, exc.message, exc.context) from exc
    except P3ServiceValidationError as exc:
        code = (
            "P3_SOURCE_LIMIT_EXCEEDED"
            if "limit" in exc.message.lower()
            or "count exceeds" in exc.message.lower()
            else "P3_VALIDATION_ERROR"
        )
        raise _http_error(422, code, exc.message, exc.context) from exc
    except SQLAlchemyError as exc:
        raise _http_error(
            503,
            "P3_STORAGE_UNAVAILABLE",
            "P3 storage is temporarily unavailable.",
        ) from exc


def _project_response(project: object, request_id: str) -> P3ProjectResponse:
    return P3ProjectResponse(
        data=P3ProjectView.model_validate(project),
        requestId=request_id,
    )


def _source_response(source: object, request_id: str) -> P3SourceItemResponse:
    return P3SourceItemResponse(
        data=P3SourceItemView.model_validate(source),
        requestId=request_id,
    )


@router.post("", response_model=P3ProjectResponse, status_code=201)
def create_project(
    payload: P3ProjectCreateRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_WRITE)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectResponse:
    request_id = _request_id()
    project = _service_call(
        lambda: P3ReuseService(db).create_project(
            name=payload.name,
            description=payload.description,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        ),
        conflict_code="P3_PROJECT_IDEMPOTENCY_CONFLICT",
    )
    return _project_response(project, request_id)


@router.get("", response_model=P3ProjectPageResponse)
def list_projects(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: ReuseProjectStatus | None = None,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3ReuseService(db).list_projects(
            limit=limit,
            offset=offset,
            status=status,
        )
    )
    return P3ProjectPageResponse(
        data=P3ProjectPageData(
            items=[P3ProjectView.model_validate(item) for item in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
        requestId=request_id,
    )


@router.get("/{project_id}", response_model=P3ProjectResponse)
def get_project(
    project_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectResponse:
    request_id = _request_id()
    project = _service_call(lambda: P3ReuseService(db).get_project(project_id))
    return _project_response(project, request_id)


@router.patch("/{project_id}", response_model=P3ProjectResponse)
def update_project(
    project_id: str,
    payload: P3ProjectUpdateRequest,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_WRITE)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectResponse:
    request_id = _request_id()
    updates = {
        field: getattr(payload, field)
        for field in payload.model_fields_set
    }
    project = _service_call(
        lambda: P3ReuseService(db).update_project_metadata(
            project_id,
            **updates,
        )
    )
    return _project_response(project, request_id)


@router.post("/{project_id}/activate", response_model=P3ProjectResponse)
def activate_project(
    project_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_ACTIVATE)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectResponse:
    request_id = _request_id()
    project = _service_call(lambda: P3ReuseService(db).activate_project(project_id))
    return _project_response(project, request_id)


@router.post("/{project_id}/archive", response_model=P3ProjectResponse)
def archive_project(
    project_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_ARCHIVE)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectResponse:
    request_id = _request_id()
    project = _service_call(lambda: P3ReuseService(db).archive_project(project_id))
    return _project_response(project, request_id)


@router.post(
    "/{project_id}/sources",
    response_model=P3SourceItemResponse,
    status_code=201,
)
def add_source(
    project_id: str,
    payload: P3SourceAddRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_SOURCE_MANAGE)
    ),
    db: Session = Depends(get_db),
) -> P3SourceItemResponse:
    request_id = _request_id()
    source = _service_call(
        lambda: P3ReuseService(db).add_source_to_project(
            project_id=project_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            source_version=payload.source_version,
            expected_fingerprint=payload.expected_fingerprint,
            actor_role=principal.role.value,
            request_id=request_id,
        ),
        conflict_code="P3_SOURCE_EVIDENCE_CONFLICT",
    )
    return _source_response(source, request_id)


@router.get(
    "/{project_id}/sources",
    response_model=P3SourceItemPageResponse,
)
def list_sources(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_removed: bool = False,
    source_type: P3SourceType | None = None,
    source_stale: bool | None = None,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3SourceItemPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3ReuseService(db).list_project_source_items(
            project_id=project_id,
            limit=limit,
            offset=offset,
            include_removed=include_removed,
            source_type=source_type,
            source_stale=source_stale,
        )
    )
    return P3SourceItemPageResponse(
        data=P3SourceItemPageData(
            items=[
                P3SourceItemView.model_validate(item)
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        ),
        requestId=request_id,
    )


@router.get(
    "/{project_id}/sources/{source_item_id}",
    response_model=P3SourceItemResponse,
)
def get_source(
    project_id: str,
    source_item_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_PROJECT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3SourceItemResponse:
    request_id = _request_id()
    source = _service_call(
        lambda: P3ReuseService(db).get_source_item(
            project_id=project_id,
            source_item_id=source_item_id,
        ),
        not_found_code="P3_SOURCE_ITEM_NOT_FOUND",
    )
    return _source_response(source, request_id)


@router.delete(
    "/{project_id}/sources/{source_item_id}",
    response_model=P3SourceItemResponse,
)
def remove_source(
    project_id: str,
    source_item_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_SOURCE_MANAGE)
    ),
    db: Session = Depends(get_db),
) -> P3SourceItemResponse:
    request_id = _request_id()
    source = _service_call(
        lambda: P3ReuseService(db).remove_source_from_project(
            project_id=project_id,
            source_item_id=source_item_id,
        ),
        not_found_code="P3_SOURCE_ITEM_NOT_FOUND",
    )
    return _source_response(source, request_id)


@router.post(
    "/{project_id}/sources/{source_item_id}/revalidate",
    response_model=P3SourceRevalidationResponse,
)
def revalidate_source(
    project_id: str,
    source_item_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_SOURCE_MANAGE)
    ),
    db: Session = Depends(get_db),
) -> P3SourceRevalidationResponse:
    request_id = _request_id()
    result = _service_call(
        lambda: P3ReuseService(db).revalidate_source_item(
            project_id=project_id,
            source_item_id=source_item_id,
        ),
        not_found_code="P3_SOURCE_ITEM_NOT_FOUND",
    )
    return P3SourceRevalidationResponse(data=result, requestId=request_id)


@router.post(
    "/{project_id}/sources/revalidate",
    response_model=P3ProjectRevalidationResponse,
)
def revalidate_project_sources(
    project_id: str,
    payload: P3BatchRevalidationRequest,
    _principal: Principal = Depends(
        require_permission(Permission.P3_SOURCE_MANAGE)
    ),
    db: Session = Depends(get_db),
) -> P3ProjectRevalidationResponse:
    request_id = _request_id()
    result = _service_call(
        lambda: P3ReuseService(db).revalidate_project_sources(
            project_id,
            limit=payload.limit,
        )
    )
    return P3ProjectRevalidationResponse(data=result, requestId=request_id)
