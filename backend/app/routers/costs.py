"""Cost analytics — the per-turn ledger rolled up, plus what-if replays."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.deps import current_install, current_user
from app.services import agent_runs
from app.telemetry.replay import replay

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/summary")
async def summary(
    days: int = Query(7, ge=1, le=90),
    mine: bool = False,
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> dict:
    # The org always comes from the caller's bound install — never the query
    # string — so one workspace can't read another's spend.
    return await agent_runs.cost_summary(
        install["account_login"], days=days, user_id=user["github_id"] if mine else None
    )


class ReplayRequest(BaseModel):
    model_map: dict[str, str]
    price_overrides: dict[str, tuple[float, float]] | None = None
    limit: int = Field(5_000, ge=1, le=agent_runs.MAX_REPLAY_RUNS)


@router.post("/replay")
async def what_if(
    body: ReplayRequest,
    install: dict = Depends(current_install),
) -> dict:
    runs = await agent_runs.iter_runs(install["account_login"], limit=body.limit)
    return replay(runs, body.model_map, body.price_overrides).as_dict()
