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


class ToolObservation(BaseModel):
    """Hasil satu tool secara utuh, bahan mentah penyusunan jawaban akhir.

    Terpisah dari ToolCallRecord karena tujuannya berbeda: record dipotong
    demi audit dan persistensi, observation harus utuh supaya composer tidak
    menyusun jawaban di atas daftar produk atau kutipan FAQ yang terpenggal.
    Observation tidak pernah disimpan ke database.
    """

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    result: str
    is_error: bool = False
    contexts: list[str] = Field(
        default_factory=list,
        description=(
            "Potongan dokumen mentah di balik hasil tool, sebelum diformat. "
            "Hanya terisi untuk tool yang memang melakukan retrieval."
        ),
    )


class AgentReply(BaseModel):
    """Hasil satu giliran agent: jawaban plus jejak tool yang dipakai."""

    answer: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_outputs: list[str] = Field(
        default_factory=list,
        description=(
            "Keluaran tool secara utuh, tanpa pemotongan 500 karakter yang "
            "berlaku di ToolCallRecord. Inilah bukti yang benar-benar dilihat "
            "composer, jadi inilah pembanding yang sah saat menilai apakah "
            "jawaban bersandar pada bukti."
        ),
    )
    retrieved_contexts: list[str] = Field(
        default_factory=list,
        description=(
            "Gabungan potongan hasil retrieval seluruh tool pada giliran ini, "
            "dipakai harness eval untuk menilai mutu retrieval."
        ),
    )
