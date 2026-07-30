from fastapi import APIRouter, Depends

from app.auth.deps import current_install, current_user
from app.core.config import get_settings
from app.models.schemas import Member
from app.services.members import list_members

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/org")
async def org_info(
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> dict:
    s = get_settings()
    return {
        "org": install["account_login"],
        "account_type": install.get("account_type"),
        "repository_selection": install.get("repository_selection"),
        "env": s.app_env,
        "user_login": user["login"],
        "cache": {
            "repos": s.cache_ttl_repos,
            "prs": s.cache_ttl_prs,
            "members": s.cache_ttl_members,
        },
    }


@router.get("/members", response_model=list[Member])
async def members(install: dict = Depends(current_install)) -> list[Member]:
    return await list_members(install.get("install_id"), install["account_login"])
