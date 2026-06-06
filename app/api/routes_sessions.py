from fastapi import APIRouter, HTTPException

from app.schemas.sessions import MessageItem, SessionHistoryResponse, SessionListItem
from app.services.container import memory_service


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionListItem])
async def list_sessions(limit: int = 50) -> list[SessionListItem]:
    limit = max(1, min(limit, 100))
    return [SessionListItem(**session) for session in memory_service.list_sessions(limit=limit)]


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def session_history(session_id: str) -> SessionHistoryResponse:
    messages = memory_service.get_session_history(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found or has no messages")
    return SessionHistoryResponse(
        session_id=session_id,
        messages=[MessageItem(**message) for message in messages],
    )
