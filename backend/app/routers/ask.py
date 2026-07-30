from fastapi import APIRouter, Depends

from app.auth.deps import current_install
from app.models.schemas import AskAnswer, AskRequest
from app.services.ask import ask as ask_service

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("/", response_model=AskAnswer)
async def ask(req: AskRequest, install: dict = Depends(current_install)) -> AskAnswer:
    return await ask_service(
        install.get("install_id"), install["account_login"], req.q, repo=req.repo, limit=req.limit
    )
