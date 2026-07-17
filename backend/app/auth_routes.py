"""Minimal authenticated-principal inspection route for the operator UI."""

from uuid import uuid4

from fastapi import APIRouter, Security

from app.auth import Principal, get_current_principal
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/me", response_model=ApiResponse)
def get_authenticated_principal(
    principal: Principal = Security(get_current_principal),
) -> ApiResponse:
    return ApiResponse(
        success=True,
        data={
            "role": principal.role.value,
            "auth_mode": principal.auth_mode.value,
            "authenticated": principal.authenticated,
        },
        requestId=f"req_{uuid4().hex[:12]}",
    )
