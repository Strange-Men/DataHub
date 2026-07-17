"""Versioned CustomerOpsAgent retrieval with explicit Unified opt-in."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.customerops_unified_schemas import CustomerOpsUnifiedRetrievalRequest
from app.auth import Permission, require_permission
from app.customerops_unified_service import (
    CustomerOpsUnifiedFailure,
    CustomerOpsUnifiedRetrievalService,
)
from app.database import get_db
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/v2/customer-ops-agent", tags=["CustomerOpsAgent v2"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": code, "message": message, "details": {}},
            "requestId": _request_id(),
        },
    )


@router.post("/retrieve", response_model=None, dependencies=[Depends(require_permission(Permission.AGENT_CUSTOMEROPS))])
def retrieve_for_customerops_agent_v2(
    payload: CustomerOpsUnifiedRetrievalRequest,
    db: Session = Depends(get_db),
    x_datahub_client: str | None = Header(default=None, alias="X-DataHub-Client"),
) -> ApiResponse | JSONResponse:
    if x_datahub_client != "CustomerOpsAgent":
        return _error(
            "UNAUTHORIZED_CLIENT",
            "CustomerOpsAgent client header is required.",
            401,
        )
    try:
        response = CustomerOpsUnifiedRetrievalService(db).retrieve(payload)
    except CustomerOpsUnifiedFailure as exc:
        return JSONResponse(
            status_code=503,
            content=ApiResponse(
                success=False,
                data={
                    "retrieval_mode": "customerops_retrieval_error",
                    "fallback_used": False,
                    "fallback_reason": exc.reason,
                    "request_id": exc.request_id,
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
