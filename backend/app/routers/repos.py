from fastapi import APIRouter, Depends, Query

from app.auth.deps import current_install
from app.models.schemas import PR, Repo
from app.services.prs import list_repo_prs
from app.services.repos import get_repo, list_org_repos, repo_commit_activity

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("/", response_model=list[Repo])
async def list_repos(
    install: dict = Depends(current_install),
    include_archived: bool = Query(False),
) -> list[Repo]:
    return await list_org_repos(
        install.get("install_id"),
        install["account_login"],
        include_archived=include_archived,
    )


@router.get("/{name}", response_model=Repo)
async def repo_detail(name: str, install: dict = Depends(current_install)) -> Repo:
    full_name = f"{install['account_login']}/{name}"
    repo = await get_repo(install.get("install_id"), full_name)
    repo.spark = await repo_commit_activity(install.get("install_id"), full_name)
    return repo


@router.get("/{name}/prs", response_model=list[PR])
async def repo_prs(
    name: str,
    state: str = "all",
    limit: int = 50,
    install: dict = Depends(current_install),
) -> list[PR]:
    full_name = f"{install['account_login']}/{name}"
    return await list_repo_prs(install.get("install_id"), full_name, state=state, limit=limit)
