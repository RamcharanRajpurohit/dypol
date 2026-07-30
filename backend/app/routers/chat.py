"""Chat router — sessions CRUD + send message.

Sessions are scoped to (user, org). All endpoints require an active
workspace via ``current_install`` so we know which GitHub data the
agent should query.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.deps import current_install, current_user
from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSession,
    ChatTurnResponse,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


# ──────────────────────────────────────────────────────────────────
# Health-ish — does the agent have an LLM available?
# ──────────────────────────────────────────────────────────────────
@router.get("/status")
async def chat_status() -> dict:
    return {"agent_enabled": chat_service.is_agent_enabled()}


# ──────────────────────────────────────────────────────────────────
# Sessions
# ──────────────────────────────────────────────────────────────────
@router.get("/sessions", response_model=list[ChatSession])
async def list_sessions(
    include_archived: bool = False,
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> list[ChatSession]:
    return await chat_service.list_sessions(
        user["github_id"], install["account_login"], include_archived=include_archived
    )


@router.post("/sessions", response_model=ChatSession)
async def create_session(
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> ChatSession:
    return await chat_service.create_session(
        user["github_id"], install["account_login"]
    )


@router.get("/sessions/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: str,
    user: dict = Depends(current_user),
) -> ChatSession:
    s = await chat_service.get_session(user["github_id"], session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


@router.patch("/sessions/{session_id}", response_model=ChatSession)
async def patch_session(
    session_id: str,
    body: dict,
    user: dict = Depends(current_user),
) -> ChatSession:
    allowed = {k: v for k, v in body.items() if k in {"title", "pinned", "archived"}}
    if not allowed:
        raise HTTPException(status_code=400, detail="no_valid_fields")
    s = await chat_service.update_session(user["github_id"], session_id, **allowed)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: dict = Depends(current_user),
) -> dict:
    ok = await chat_service.delete_session(user["github_id"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"deleted": session_id}


# ──────────────────────────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────────────────────────
@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def list_messages(
    session_id: str,
    user: dict = Depends(current_user),
) -> list[ChatMessage]:
    s = await chat_service.get_session(user["github_id"], session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return await chat_service.list_messages(session_id)


@router.post("/sessions/{session_id}/messages", response_model=ChatTurnResponse)
async def send_message(
    session_id: str,
    body: ChatSendRequest,
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> ChatTurnResponse:
    if not chat_service.is_agent_enabled():
        raise HTTPException(
            status_code=503,
            detail="agent_unavailable: GROQ_API_KEY or GEMINI_API_KEY required",
        )
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="empty_message")
    try:
        return await chat_service.send_message(
            user["github_id"], install, session_id, body.content
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: str,
    body: ChatSendRequest,
    user: dict = Depends(current_user),
    install: dict = Depends(current_install),
) -> StreamingResponse:
    """Streaming variant of send_message — Server-Sent Events.

    Emits ``tool`` events (live trace, incl. sub-agent steps) and a final
    ``done`` event carrying the same ChatTurnResponse the non-streaming
    endpoint returns. The frontend prefers this and falls back to the
    non-streaming route when unavailable, so both must stay in sync.
    """
    if not chat_service.is_agent_enabled():
        raise HTTPException(
            status_code=503,
            detail="agent_unavailable: configure an LLM provider API key",
        )
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="empty_message")

    generator = chat_service.stream_message(
        user["github_id"], install, session_id, body.content
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering for live SSE
        },
    )
