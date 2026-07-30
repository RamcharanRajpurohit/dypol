from fastapi import APIRouter

from app.clients.github import get_app_jwt
from app.core.config import get_settings
from app.core.db import get_client
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = get_settings()
    db_ok = False
    try:
        await get_client().admin.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    gh_ok = False
    try:
        get_app_jwt()  # signs successfully → keys/config OK
        gh_ok = True
    except Exception:
        gh_ok = False
    return HealthResponse(ok=db_ok and gh_ok, org=s.github_app_slug, db=db_ok, github=gh_ok)
