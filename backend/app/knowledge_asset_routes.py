"""Additive P2-M4 Knowledge Asset governance APIs."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import Permission, require_permission
from app.knowledge_asset_repositories import KnowledgeSourceTraceError, list_knowledge_assets
from app.knowledge_asset_service import (
    KnowledgeAssetNotFoundError,
    KnowledgeAssetService,
    KnowledgeSnapshotNotApprovedError,
    KnowledgeSnapshotNotFoundError,
    KnowledgeSourceTraceInvalidError,
)
from app.schemas import ApiResponse


router = APIRouter(prefix="/api", tags=["P2 Knowledge Assets"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _knowledge_asset_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "KNOWLEDGE_ASSET_NOT_FOUND",
            "message": "Knowledge Asset was not found.",
        },
    )


def _source_trace_invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "KNOWLEDGE_SOURCE_TRACE_INVALID", "message": message},
    )


@router.post("/snapshots/{snapshot_id}/publish", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_PUBLISH))])
def publish_snapshot(
    snapshot_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = KnowledgeAssetService(db).publish_snapshot(snapshot_id)
    except KnowledgeSnapshotNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SNAPSHOT_NOT_FOUND",
                "message": "Approved snapshot was not found.",
            },
        ) from exc
    except KnowledgeSnapshotNotApprovedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SNAPSHOT_NOT_APPROVED",
                "message": "Only snapshots backed by an approved Review can be published.",
            },
        ) from exc
    except KnowledgeSourceTraceInvalidError as exc:
        raise _source_trace_invalid(str(exc)) from exc
    response.status_code = 201 if result.created else 200
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())


@router.get("/knowledge-assets", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_READ))])
def get_knowledge_assets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    asset_id: str | None = None,
    status: Literal["draft", "active", "archived"] | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        records = list_knowledge_assets(
            db,
            page=page,
            page_size=page_size,
            asset_id=asset_id,
            status=status,
        )
    except KnowledgeSourceTraceError as exc:
        raise _source_trace_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=records.model_dump(), requestId=_request_id())


@router.get("/knowledge-assets/{knowledge_asset_id}", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_READ))])
def get_knowledge_asset_detail(
    knowledge_asset_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        record = KnowledgeAssetService(db).get_asset(knowledge_asset_id)
    except KnowledgeAssetNotFoundError as exc:
        raise _knowledge_asset_not_found() from exc
    except KnowledgeSourceTraceInvalidError as exc:
        raise _source_trace_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=record.model_dump(), requestId=_request_id())


@router.post("/knowledge-assets/{knowledge_asset_id}/archive", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_ARCHIVE))])
def archive_knowledge_asset(
    knowledge_asset_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        record = KnowledgeAssetService(db).archive(knowledge_asset_id)
    except KnowledgeAssetNotFoundError as exc:
        raise _knowledge_asset_not_found() from exc
    except KnowledgeSourceTraceInvalidError as exc:
        raise _source_trace_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=record.model_dump(), requestId=_request_id())
