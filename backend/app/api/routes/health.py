"""System health endpoint.

Phase 1 returns basic liveness metadata. In later phases this will also
report on database, vector-store, and model availability.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "time": datetime.now(timezone.utc).isoformat(),
    }