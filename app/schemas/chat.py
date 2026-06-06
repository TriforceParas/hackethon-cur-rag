from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    mode: str
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    memory_used: bool = False
    tools_used: list[str] = Field(default_factory=list)
