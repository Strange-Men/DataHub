"""Additive M8.2 unified retrieval API; the sealed P1 route is untouched."""

from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ApiResponse
from app.unified_retrieval_schemas import UnifiedRetrievalRequest
from app.unified_retrieval_service import (
    UnifiedRetrievalFailure,
    UnifiedRetrievalService,
)


router = APIRouter(prefix="/api/v2/retrieval", tags=["Unified Retrieval"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


@router.post("/search", response_model=None)
def search_unified_knowledge(
    payload: UnifiedRetrievalRequest,
    db: Session = Depends(get_db),
) -> ApiResponse | JSONResponse:
    try:
        response = UnifiedRetrievalService(db).search(payload)
    except UnifiedRetrievalFailure as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse(
                success=False,
                data={
                    "retrieval_id": exc.retrieval_id,
                    "request_id": exc.request_id,
                    "retrieval_mode": "unified_retrieval_error",
                    "fallback_used": False,
                    "fallback_reason": exc.reason,
                    "results": [],
                },
                requestId=_request_id(),
            ).model_dump(),
        )
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        requestId=_request_id(),
    )
