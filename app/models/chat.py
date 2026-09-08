"""Schema data percakapan chatbot."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]
Bahasa = Literal["id", "en"]

# Dari mana satu jawaban berasal. Diturunkan dari nama tool yang dipakai:
# search_faq membaca indeks dokumen, tujuh tool lain membaca database.
Sumber = Literal["dokumen", "database"]
Mode = Literal["dokumen", "database", "campuran", "tanpa_sumber"]


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


class TokenUsage(BaseModel):
    """Akumulasi pemakaian token satu giliran percakapan.

    Satu giliran dengan tool memicu beberapa panggilan Anthropic, bukan satu:
    sekali untuk memilih tool, sekali lagi untuk menulis jawaban, dan seterusnya
    tiap iterasi. Objek ini dipakai sekaligus sebagai akumulator yang dimutasi
    di tengah giliran dan sebagai skema respons, supaya tidak ada konversi yang
    bisa menghilangkan angka di antaranya.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    llm_calls: int = 0

    def tambah(self, lain: "TokenUsage") -> None:
        """Tambahkan pemakaian satu panggilan ke akumulator ini.

        Sengaja memutasi objek, bukan mengembalikan yang baru: akumulator hidup
        di ContextVar yang disalin ke task anak workflow, dan hanya mutasi pada
        objek yang sama yang terlihat oleh task induk.

        Args:
            lain: Pemakaian dari satu panggilan LLM.
        """
        self.input_tokens += lain.input_tokens
        self.output_tokens += lain.output_tokens
        self.cache_read_tokens += lain.cache_read_tokens
        self.cache_write_tokens += lain.cache_write_tokens
        self.llm_calls += lain.llm_calls


class Citation(BaseModel):
    """Satu potongan dokumen yang dipakai menyusun jawaban.

    Hanya terisi untuk jawaban yang berasal dari indeks dokumen; jawaban yang
    dibaca dari database tidak punya kutipan.
    """

    file_name: str
    # page_label dari LlamaIndex bertipe string ("1", "2"), bukan integer.
    page: str | None = None
    score: float | None = None
    match_percent: int | None = None
    snippet: str = ""


class AgentReply(BaseModel):
    """Hasil satu giliran agent: jawaban plus jejak tool yang dipakai."""

    answer: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    citations: list[Citation] = Field(default_factory=list)
    mode: Mode = "tanpa_sumber"
    # True kalau jawaban berasal dari fixture contoh, bukan dari model sungguhan.
    stub: bool = False
