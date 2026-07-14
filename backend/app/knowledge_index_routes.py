"""Additive P2-M6 Knowledge Index control-plane APIs."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.knowledge_index_repositories import KnowledgeIndexSourceTraceError, list_index_entries
from app.knowledge_index_service import (
    IndexKnowledgeAssetNotActiveError,
    IndexKnowledgeAssetNotFoundError,
    KnowledgeIndexNotFoundError,
    KnowledgeIndexProjectionError,
    KnowledgeIndexService,
    KnowledgeIndexSourceInvalidError,
)
from app.schemas import ApiResponse


router = APIRouter(prefix="/api", tags=["P2 Knowledge Index"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _source_invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "KNOWLEDGE_INDEX_SOURCE_INVALID", "message": message},
    )


@router.post("/knowledge-assets/{knowledge_asset_id}/index", response_model=ApiResponse)
def create_knowledge_index(
    knowledge_asset_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = KnowledgeIndexService(db).create_index(knowledge_asset_id)
    except IndexKnowledgeAssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_ASSET_NOT_FOUND",
                "message": "Knowledge Asset was not found.",
            },
        ) from exc
    except IndexKnowledgeAssetNotActiveError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "KNOWLEDGE_ASSET_NOT_ACTIVE",
                "message": "Only active Knowledge Assets can create an index projection.",
            },
        ) from exc
    except KnowledgeIndexSourceInvalidError as exc:
        raise _source_invalid(str(exc)) from exc
    except KnowledgeIndexProjectionError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "KNOWLEDGE_INDEX_PROJECTION_FAILED", "message": str(exc)},
        ) from exc
    response.status_code = 201 if result.created else 200
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())


@router.get("/knowledge-index", response_model=ApiResponse)
def get_knowledge_index_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Literal[
        "pending", "building", "ready", "serving", "failed", "archived"
    ]
    | None = None,
    asset_id: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        records = list_index_entries(
            db,
            page=page,
            page_size=page_size,
            status=status,
            asset_id=asset_id,
        )
    except KnowledgeIndexSourceTraceError as exc:
        raise _source_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=records.model_dump(), requestId=_request_id())


@router.get("/knowledge-index/{index_entry_id}", response_model=ApiResponse)
def get_knowledge_index_detail(
    index_entry_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        record = KnowledgeIndexService(db).get_index(index_entry_id)
    except KnowledgeIndexNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_INDEX_NOT_FOUND",
                "message": "Knowledge Index entry was not found.",
            },
        ) from exc
    except KnowledgeIndexSourceInvalidError as exc:
        raise _source_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=record.model_dump(), requestId=_request_id())


@router.post("/knowledge-index/{index_entry_id}/archive", response_model=ApiResponse)
def archive_knowledge_index(
    index_entry_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        record = KnowledgeIndexService(db).archive(index_entry_id)
    except KnowledgeIndexNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_INDEX_NOT_FOUND",
                "message": "Knowledge Index entry was not found.",
            },
        ) from exc
    except KnowledgeIndexSourceInvalidError as exc:
        raise _source_invalid(str(exc)) from exc
    return ApiResponse(success=True, data=record.model_dump(), requestId=_request_id())
