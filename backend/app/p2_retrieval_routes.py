"""Versioned P2-only retrieval API; no P1 fan-out or fusion."""

from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.answerability import AnswerabilityConfigurationError
from app.database import get_db
from app.auth import Permission, require_permission
from app.p2_retrieval_schemas import P2RetrievalRequest
from app.p2_retrieval_service import P2RetrievalFailure, P2RetrievalService
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/v2/retrieval/p2", tags=["P2 Retrieval"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


@router.post("/search", response_model=None, dependencies=[Depends(require_permission(Permission.RETRIEVAL_P2))])
def search_p2_knowledge(
    payload: P2RetrievalRequest,
    db: Session = Depends(get_db),
) -> ApiResponse | JSONResponse:
    try:
        result = P2RetrievalService(db).search(payload)
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
    except P2RetrievalFailure as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse(
                success=False,
                data=exc.response.model_dump(),
                requestId=_request_id(),
            ).model_dump(),
        )
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())
