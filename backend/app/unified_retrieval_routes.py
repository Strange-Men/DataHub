"""Additive M8.2 unified retrieval API; the sealed P1 route is untouched."""

from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.answerability import (
    AnswerabilityConfig,
    AnswerabilityConfigurationError,
    evaluate_answerability,
)
from app.database import get_db
from app.auth import Permission, require_permission
from app.schemas import ApiResponse
from app.unified_retrieval_schemas import UnifiedRetrievalRequest
from app.unified_retrieval_service import (
    UnifiedRetrievalFailure,
    UnifiedRetrievalService,
)


router = APIRouter(prefix="/api/v2/retrieval", tags=["Unified Retrieval"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


@router.post("/search", response_model=None, dependencies=[Depends(require_permission(Permission.RETRIEVAL_UNIFIED))])
def search_unified_knowledge(
    payload: UnifiedRetrievalRequest,
    db: Session = Depends(get_db),
) -> ApiResponse | JSONResponse:
    try:
        response = UnifiedRetrievalService(db).search(payload)
    except AnswerabilityConfigurationError:
        return JSONResponse(
            status_code=500,
            content=ApiResponse(
                success=False,
                data={
                    "error_code": "NO_ANSWER_CONFIG_INVALID",
                    "error_message": "No-answer configuration is invalid.",
                    "results": [],
                },
                requestId=_request_id(),
            ).model_dump(),
        )
    except UnifiedRetrievalFailure as exc:
        answerability = evaluate_answerability(
            query=payload.query,
            evidence=[],
            scope="unified",
            config=AnswerabilityConfig.from_environment(),
            retrieval_unavailable=True,
        )
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
                    "answerability": answerability.model_dump(mode="json"),
                },
                requestId=_request_id(),
            ).model_dump(),
        )
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        requestId=_request_id(),
    )
