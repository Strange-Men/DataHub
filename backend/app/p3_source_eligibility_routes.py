"""Read-only P3 source-eligibility API protected by centralized RBAC."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import Permission, require_permission
from app.database import get_db
from app.p3_source_eligibility import (
    check_source_eligibility,
    check_sources_eligibility,
)
from app.p3_source_eligibility_schemas import (
    P3SourceEligibilityBatchData,
    P3SourceEligibilityBatchRequest,
    P3SourceEligibilityBatchResponse,
    P3SourceEligibilityRequest,
    P3SourceEligibilitySingleData,
    P3SourceEligibilitySingleResponse,
)


router = APIRouter(
    prefix="/api/p3/source-eligibility",
    tags=["P3 Source Eligibility"],
    dependencies=[Depends(require_permission(Permission.P3_SOURCE_READ))],
)


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "P3_SOURCE_ELIGIBILITY_UNAVAILABLE",
            "message": "Source eligibility could not be checked.",
            "details": {},
        },
    )


@router.post(
    "/check",
    response_model=P3SourceEligibilitySingleResponse,
)
def check_p3_source_eligibility(
    payload: P3SourceEligibilityRequest,
    db: Session = Depends(get_db),
) -> P3SourceEligibilitySingleResponse:
    try:
        decision = check_source_eligibility(db, payload.model_dump(mode="json"))
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    return P3SourceEligibilitySingleResponse(
        data=P3SourceEligibilitySingleData(decision=decision),
        requestId=_request_id(),
    )


@router.post(
    "/check-batch",
    response_model=P3SourceEligibilityBatchResponse,
)
def check_p3_sources_eligibility(
    payload: P3SourceEligibilityBatchRequest,
    db: Session = Depends(get_db),
) -> P3SourceEligibilityBatchResponse:
    try:
        decisions = check_sources_eligibility(
            db,
            [source.model_dump(mode="json") for source in payload.sources],
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    return P3SourceEligibilityBatchResponse(
        data=P3SourceEligibilityBatchData(decisions=decisions),
        requestId=_request_id(),
    )
