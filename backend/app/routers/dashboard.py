from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import DashboardSummary
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardSummary)
async def dashboard_summary(install: dict = Depends(current_install)) -> DashboardSummary:
    return await build_dashboard(install)
