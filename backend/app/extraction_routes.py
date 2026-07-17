"""Additive P2-M2 Asset extraction APIs using the mock provider only."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.asset_repositories import get_asset
from app.auth import Permission, require_permission
from app.database import get_db
from app.extraction_providers import get_extraction_provider
from app.extraction_repositories import list_asset_extractions
from app.extraction_schemas import ExtractionExecutionResult, ExtractionRequest
from app.extraction_service import ExtractionAssetNotFoundError, ExtractionService
from app.schemas import ApiResponse


router = APIRouter(prefix="/api", tags=["P2 Asset Extraction"])


def _request_id() -> str:
    from uuid import uuid4

    return f"req_{uuid4().hex[:12]}"


@router.post("/assets/{asset_id}/extract", response_model=ApiResponse, status_code=201, dependencies=[Depends(require_permission(Permission.P2_EXTRACT))])
def create_asset_extraction_job(
    asset_id: str,
    request: ExtractionRequest,
    db: Session = Depends(get_db),
) -> ApiResponse:
    provider = get_extraction_provider(request.provider)
    try:
        execution = ExtractionService(db).create_and_execute(
            asset_id=asset_id,
            extract_type=request.extract_type,
            provider=provider,
        )
    except ExtractionAssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ASSET_NOT_FOUND",
                "message": "Asset was not found.",
            },
        ) from exc
    result = ExtractionExecutionResult(
        job=execution.job,
        result=execution.result,
    )
    return ApiResponse(
        success=True,
        data=result.model_dump(),
        requestId=_request_id(),
    )

@router.get("/assets/{asset_id}/extractions", response_model=ApiResponse, dependencies=[Depends(require_permission(Permission.P2_READ))])
def get_asset_extractions(
    asset_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    if get_asset(db, asset_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ASSET_NOT_FOUND",
                "message": "Asset was not found.",
            },
        )
    result = list_asset_extractions(db, asset_id)
    return ApiResponse(
        success=True,
        data=result.model_dump(),
        requestId=_request_id(),
    )
