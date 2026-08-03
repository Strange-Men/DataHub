"""Public, read-only runtime capability endpoint."""

from fastapi import APIRouter

from app.capability_schemas import CapabilitiesResponse
from app.capability_service import get_capabilities


router = APIRouter(tags=["capabilities"])


@router.get("/api/capabilities", response_model=CapabilitiesResponse)
def read_capabilities() -> CapabilitiesResponse:
    return get_capabilities()


__all__ = ["router"]
