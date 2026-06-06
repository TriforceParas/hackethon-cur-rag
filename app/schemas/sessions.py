from pydantic import BaseModel


class MessageItem(BaseModel):
    role: str
    content: str
    mode: str | None = None
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]


class SessionListItem(BaseModel):
    session_id: str
    title: str
    message_count: int
    last_mode: str | None = None
    created_at: str
    updated_at: str
