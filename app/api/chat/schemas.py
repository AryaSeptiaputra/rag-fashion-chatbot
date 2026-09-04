"""Schema request dan response endpoint chat."""

from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["web", "whatsapp", "instagram", "shopee", "tokopedia"]


class ChatRequest(BaseModel):
    """Permintaan satu giliran percakapan."""

    session_id: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier sesi percakapan; giliran dengan id sama berbagi riwayat.",
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Pesan dari pembeli.",
    )
    channel: Channel = Field(
        default="web",
        description="Kanal asal percakapan.",
    )


class ToolCallInfo(BaseModel):
    """Ringkasan satu panggilan tool, dikembalikan untuk transparansi."""

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    is_error: bool = False
    latency_ms: int | None = None


class ChatResponse(BaseModel):
    """Jawaban chatbot beserta jejak tool yang dipakai."""

    session_id: str
    answer: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Status kesiapan layanan."""

    status: str
    llm_model: str
    llm_ready: bool
    llm_detail: str
    faq_chunks: int
    supabase_connected: bool
