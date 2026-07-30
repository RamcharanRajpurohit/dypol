from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import DigestSummary
from app.services.digest import weekly_digest

router = APIRouter(prefix="/digest", tags=["digest"])


@router.get("/", response_model=DigestSummary)
async def digest(days: int = 7, install: dict = Depends(current_install)) -> DigestSummary:
    return await weekly_digest(install.get("install_id"), install["account_login"], days=days)
