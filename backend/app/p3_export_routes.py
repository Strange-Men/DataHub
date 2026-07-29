"""HTTP API for governed P3 export creation, read, download, and revoke."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from typing import TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import Permission, Principal, require_permission
from app.database import get_db
from app.p3_export_models import P3ExportFormat, P3ExportJobStatus
from app.p3_export_schemas import (
    P3ExportApiOutcome,
    P3ExportApiRevokeOutcome,
    P3ExportArtifactResponse,
    P3ExportCreateRequest,
    P3ExportJobMetadata,
    P3ExportJobPageResponse,
    P3ExportJobResponse,
    P3ExportOutcomeResponse,
    P3ExportRevokeRequest,
    P3ExportRevokeResponse,
)
from app.p3_export_service import P3ExportService, P3ExportServiceError


router = APIRouter(tags=["P3 Governed Exports"])
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
    "P3_EXPORT_PROJECT_NOT_FOUND": 404,
    "P3_EXPORT_ASSET_NOT_FOUND": 404,
    "P3_EXPORT_JOB_NOT_FOUND": 404,
    "P3_EXPORT_ARTIFACT_NOT_FOUND": 404,
    "P3_EXPORT_PROJECT_NOT_ACTIVE": 409,
    "P3_EXPORT_ASSET_NOT_PUBLISHED": 409,
    "P3_EXPORT_ASSET_NOT_CURRENT": 409,
    "P3_EXPORT_REVIEW_INVALID": 409,
    "P3_EXPORT_CONTENT_HASH_MISMATCH": 409,
    "P3_EXPORT_MANIFEST_MISMATCH": 409,
    "P3_EXPORT_SOURCE_STALE": 409,
    "P3_EXPORT_SOURCE_EVIDENCE_CHANGED": 409,
    "P3_EXPORT_GROUNDING_INVALID": 409,
    "P3_EXPORT_IDEMPOTENCY_CONFLICT": 409,
    "P3_EXPORT_JOB_STATE_INVALID": 409,
    "P3_EXPORT_FORMAT_UNSUPPORTED": 422,
    "P3_EXPORT_PAYLOAD_INVALID": 422,
    "P3_EXPORT_ARTIFACT_REVOKED": 410,
    "P3_EXPORT_STORAGE_FAILED": 503,
    "P3_EXPORT_SERIALIZATION_FAILED": 500,
    "P3_EXPORT_ROLE_FORBIDDEN": 403,
}


def _service_call(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except P3ExportServiceError as exc:
        raise _http_error(
            _ERROR_STATUS.get(exc.code, 500),
            exc.code,
            exc.message,
            exc.context,
        ) from exc
    except Exception as exc:
        raise _http_error(
            500,
            "P3_EXPORT_INTERNAL_ERROR",
            "P3 export operation failed safely.",
        ) from exc


@router.post(
    "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/exports",
    response_model=P3ExportOutcomeResponse,
    status_code=201,
)
def create_export(
    project_id: str,
    asset_version_id: str,
    payload: P3ExportCreateRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_CREATE)
    ),
    db: Session = Depends(get_db),
) -> P3ExportOutcomeResponse:
    request_id = _request_id()
    service = P3ExportService(db)
    outcome = _service_call(
        lambda: service.create_export(
            project_id=project_id,
            asset_version_id=asset_version_id,
            export_format=payload.export_format,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    artifact = (
        _service_call(lambda: service.get_export_artifact(outcome.job.id))
        if outcome.artifact is not None
        else None
    )
    return P3ExportOutcomeResponse(
        data=P3ExportApiOutcome(
            job=P3ExportJobMetadata.model_validate(outcome.job),
            artifact=artifact,
            replayed=outcome.replayed,
        ),
        requestId=request_id,
    )


@router.get(
    "/api/p3/reuse-projects/{project_id}/exports",
    response_model=P3ExportJobPageResponse,
)
def list_project_exports(
    project_id: str,
    export_format: P3ExportFormat | None = None,
    status: P3ExportJobStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ExportJobPageResponse:
    request_id = _request_id()
    page = _service_call(
        lambda: P3ExportService(db).list_project_exports(
            project_id=project_id,
            export_format=export_format,
            status=status,
            limit=limit,
            offset=offset,
        )
    )
    return P3ExportJobPageResponse(data=page, requestId=request_id)


@router.get(
    "/api/p3/exports/{export_job_id}",
    response_model=P3ExportJobResponse,
)
def get_export_job(
    export_job_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ExportJobResponse:
    request_id = _request_id()
    job = _service_call(
        lambda: P3ExportService(db).get_export_job(export_job_id)
    )
    return P3ExportJobResponse(data=job, requestId=request_id)


@router.get(
    "/api/p3/exports/{export_job_id}/artifact",
    response_model=P3ExportArtifactResponse,
)
def get_export_artifact(
    export_job_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_READ)
    ),
    db: Session = Depends(get_db),
) -> P3ExportArtifactResponse:
    request_id = _request_id()
    artifact = _service_call(
        lambda: P3ExportService(db).get_export_artifact(export_job_id)
    )
    return P3ExportArtifactResponse(data=artifact, requestId=request_id)


@router.get("/api/p3/export-artifacts/{artifact_id}/download")
def download_export_artifact(
    artifact_id: str,
    _principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_DOWNLOAD)
    ),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    download = _service_call(
        lambda: P3ExportService(db).get_artifact_download(artifact_id)
    )
    return StreamingResponse(
        BytesIO(download.content),
        media_type=download.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{download.safe_file_name}"'
            ),
            "Content-Length": str(download.byte_size),
            "ETag": f'"sha256-{download.artifact_sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/api/p3/exports/{export_job_id}/revoke",
    response_model=P3ExportRevokeResponse,
)
def revoke_export(
    export_job_id: str,
    payload: P3ExportRevokeRequest,
    principal: Principal = Depends(
        require_permission(Permission.P3_EXPORT_REVOKE)
    ),
    db: Session = Depends(get_db),
) -> P3ExportRevokeResponse:
    request_id = _request_id()
    service = P3ExportService(db)
    outcome = _service_call(
        lambda: service.revoke_export(
            job_id=export_job_id,
            idempotency_key=payload.idempotency_key,
            actor_role=principal.role.value,
            request_id=request_id,
        )
    )
    artifact = _service_call(
        lambda: service.get_export_artifact(export_job_id)
    )
    return P3ExportRevokeResponse(
        data=P3ExportApiRevokeOutcome(
            job=P3ExportJobMetadata.model_validate(outcome.job),
            artifact=artifact,
            replayed=outcome.replayed,
        ),
        requestId=request_id,
    )


__all__ = ["router"]
