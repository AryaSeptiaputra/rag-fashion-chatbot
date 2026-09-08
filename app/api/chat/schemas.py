"""Schema request dan response endpoint chat."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.chat import Bahasa, Citation, Mode, Sumber, TokenUsage

Channel = Literal["web", "whatsapp", "instagram", "shopee", "tokopedia"]


class ChatRequest(BaseModel):
    """Permintaan satu giliran percakapan."""

    session_id: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Identifier sesi percakapan. Diterbitkan server lewat POST /session "
            "dan divalidasi kepemilikannya; nilai karangan klien ditolak."
        ),
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
    language: Bahasa = Field(
        default="id",
        description="Bahasa jawaban yang diminta pembeli.",
    )


class ToolCallInfo(BaseModel):
    """Ringkasan satu panggilan tool, dikembalikan untuk transparansi."""

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    is_error: bool = False
    latency_ms: int | None = None
    source: Sumber = "database"


class BudgetStatus(BaseModel):
    """Sisa anggaran demo hari ini.

    Angkanya per-proses dan hilang saat server restart; UI melabelinya sebagai
    anggaran proses ini, bukan klaim plafon harian yang persisten.
    """

    spent_usd: float
    limit_usd: float
    remaining_usd: float
    percent_used: int
    resets_at: datetime


class QuotaStatus(BaseModel):
    """Sisa jatah pertanyaan satu pengunjung."""

    limit: int
    remaining: int
    resets_at: datetime


class ChatResponse(BaseModel):
    """Jawaban chatbot beserta seluruh jejak yang membuatnya bisa diperiksa.

    Seluruh field selain tiga yang pertama punya default, sehingga klien lama
    tetap berjalan dan konstruksi ChatResponse yang sudah ada tetap valid.
    """

    session_id: str
    answer: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    mode: Mode = "tanpa_sumber"
    citations: list[Citation] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    budget: BudgetStatus | None = None
    quota: QuotaStatus | None = None
    # Diukur di route, bukan di klien: mengukurnya di peramban mencampur waktu
    # model dengan waktu jaringan.
    latency_ms: int | None = None
    # True kalau jawaban berasal dari fixture contoh, bukan model sungguhan.
    stub: bool = False


class HealthResponse(BaseModel):
    """Status kesiapan layanan."""

    status: str
    llm_model: str
    faq_chunks: int
    supabase_connected: bool


class WarmupStep(BaseModel):
    """Hasil satu langkah pemanasan."""

    name: str
    ok: bool
    ms: int
    detail: str | None = None


class WarmupResponse(BaseModel):
    """Hasil pemanasan seluruh komponen berat.

    Dipanggil saat halaman panduan dibuka, supaya 30-90 detik pemuatan model
    embedding berlangsung selagi pengunjung membaca, bukan setelah ia bertanya.
    """

    ready: bool
    steps: list[WarmupStep] = Field(default_factory=list)
    total_ms: int
    llm_model: str
    faq_chunks: int
    stub: bool = False
    budget: BudgetStatus | None = None
    quota: QuotaStatus | None = None


class SessionResponse(BaseModel):
    """Sesi baru yang diterbitkan server untuk satu pengunjung."""

    session_id: str
    budget: BudgetStatus | None = None
    quota: QuotaStatus | None = None
    stub: bool = False
