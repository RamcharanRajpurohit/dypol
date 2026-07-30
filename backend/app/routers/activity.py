from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import ActivityEvent
from app.services.activity import list_org_events

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/", response_model=list[ActivityEvent])
async def activity(
    limit: int = 50,
    install: dict = Depends(current_install),
) -> list[ActivityEvent]:
    return await list_org_events(install, limit=limit)
