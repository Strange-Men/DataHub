"""Public health routes with strict liveness/readiness separation."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.health_service import legacy_health, live_health, ready_health


router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict[str, object]:
    return live_health()


@router.get("/health/ready")
def health_ready() -> JSONResponse:
    payload, ready = ready_health()
    return JSONResponse(content=payload, status_code=200 if ready else 503)


@router.get("/health")
def health_legacy() -> dict[str, object]:
    return legacy_health()


@router.get("/api/health")
def api_health_legacy() -> dict[str, object]:
    return legacy_health()


__all__ = ["router"]
