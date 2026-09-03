"""Schema data percakapan chatbot."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    """Satu pesan dalam percakapan."""

    role: Role
    content: str
    created_at: datetime | None = None


class ToolCallRecord(BaseModel):
    """Jejak satu panggilan tool oleh agent, untuk audit dan eval."""

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    result_summary: str | None = None
    is_error: bool = False
    latency_ms: int | None = None


class AgentReply(BaseModel):
    """Hasil satu giliran agent: jawaban plus jejak tool yang dipakai."""

    answer: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
