from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import Alert
from app.services.alerts import list_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[Alert])
async def alerts(limit: int = 100, install: dict = Depends(current_install)) -> list[Alert]:
    return await list_alerts(install.get("install_id"), install["account_login"], limit=limit)
