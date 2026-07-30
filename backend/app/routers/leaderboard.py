from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import LeaderboardEntry
from app.services.leaderboard import compute_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/", response_model=list[LeaderboardEntry])
async def leaderboard(
    days: int = 30,
    limit: int = 25,
    install: dict = Depends(current_install),
) -> list[LeaderboardEntry]:
    return await compute_leaderboard(
        install.get("install_id"), install["account_login"], days=days, limit=limit
    )
