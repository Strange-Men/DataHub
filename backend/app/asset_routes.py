"""Additive P2-M1 Asset APIs; no P1 route or business behavior is changed."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.asset_repositories import get_asset, list_assets
from app.asset_service import (
    AssetValidationFailure,
    DuplicateAssetFailure,
    ingest_asset,
    max_upload_bytes,
)
from app.asset_storage import AssetStorageError, get_asset_storage_adapter
from app.database import get_db
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/assets", tags=["P2 Material Assets"])


def _request_id() -> str:
    from uuid import uuid4

    return f"req_{uuid4().hex[:12]}"


@router.post("/upload", response_model=ApiResponse, status_code=201)
async def upload_asset(
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP material")],
    asset_type: Annotated[str, Form()] = "image",
    eval_run_scope: Annotated[str | None, Form(max_length=110)] = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    limit = max_upload_bytes()
    try:
        content = await file.read(limit + 1)
    finally:
        await file.close()
    try:
        storage = get_asset_storage_adapter()
        asset = ingest_asset(
            db,
            storage,
            file_name=file.filename,
            declared_mime_type=file.content_type,
            content=content,
            asset_type=asset_type.strip().lower(),
            eval_run_scope=eval_run_scope,
        )
    except AssetValidationFailure as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message, "details": exc.details or {}},
        ) from exc
    except DuplicateAssetFailure as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ASSET_DUPLICATE",
                "message": "The same file content has already been uploaded.",
                "details": {"existing_asset_id": exc.asset_id},
            },
        ) from exc
    except AssetStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASSET_STORAGE_UNAVAILABLE",
                "message": str(exc),
                "details": {},
            },
        ) from exc
    return ApiResponse(success=True, data=asset.model_dump(), requestId=_request_id())


@router.get("", response_model=ApiResponse)
def get_assets(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = list_assets(db, page=page, page_size=page_size)
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())


@router.get("/{asset_id}", response_model=ApiResponse)
def get_asset_detail(asset_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    asset = get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ASSET_NOT_FOUND", "message": "Asset was not found."},
        )
    return ApiResponse(success=True, data=asset.model_dump(), requestId=_request_id())
