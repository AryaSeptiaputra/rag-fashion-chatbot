"""Konfigurasi aplikasi, dibaca dari environment variable / file .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Setting terpusat untuk seluruh layer aplikasi."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.2

    # Tarif Claude Haiku 4.5 dalam USD per juta token, dipakai menghitung biaya
    # dari usage yang dikembalikan API. Sengaja jadi setting, bukan konstanta:
    # angka ini harus dicek ulang di halaman pricing Anthropic setiap kali
    # LLM_MODEL diganti, dan tidak ada yang bisa memvalidasinya secara otomatis.
    price_input_per_mtok: float = Field(
        default=1.00, description="Harga token masukan per juta token."
    )
    price_output_per_mtok: float = Field(
        default=5.00, description="Harga token keluaran per juta token."
    )
    price_cache_read_per_mtok: float = Field(
        default=0.10, description="Harga baca cache prompt per juta token."
    )
    price_cache_write_per_mtok: float = Field(
        default=1.25, description="Harga tulis cache prompt per juta token."
    )

    # Saat true, endpoint chat melayani jawaban contoh dari fixture dan tidak
    # pernah memanggil Anthropic. Dipakai untuk membangun serta memperagakan UI
    # tanpa memakai saldo API.
    demo_stub_llm: bool = False

    # Kunci penanda tangan cookie pengunjung. Wajib diisi saat DEMO_STUB_LLM
    # mati; tanpa itu kuota bisa direset siapa pun dengan menyunting cookie.
    demo_signing_key: str = ""

    # Kuota berlapis. Ketiganya harus lolos sebelum satu pertanyaan dilayani.
    # Lapis pengunjung menahan tab dan sesi baru, lapis IP menahan penghapus
    # cookie, dan plafon anggaran menahan sisanya termasuk VPN.
    demo_visitor_daily_quota: int = 8
    demo_ip_daily_quota: int = 24
    demo_daily_budget_usd: float = 0.10
    demo_message_max_chars: int = 500

    # Berapa banyak proxy tepercaya di depan aplikasi. 0 berarti X-Forwarded-For
    # diabaikan sepenuhnya, karena header itu bisa dipalsukan siapa saja dan
    # memercayainya membuat lapis kuota IP tidak ada gunanya.
    trusted_proxy_count: int = 0

    # Asal yang boleh memanggil API dari domain berbeda, dipisah koma. Kosong
    # berarti CORSMiddleware tidak dipasang sama sekali -- frontend disajikan
    # dari proses yang sama, jadi same-origin dan tidak butuh CORS.
    cors_allow_origins: str = ""

    demo_facts_ttl_seconds: int = 300

    supabase_url: str = ""
    supabase_service_key: str = ""

    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_device: str = "cpu"

    chroma_persist_dir: str = "storage/chroma"
    chroma_collection: str = "faq"

    faq_source_dir: str = "data/raw/faq"
    chunk_size: int = 320
    chunk_overlap: int = 64
    retrieval_top_k: int = 4

    agent_max_iterations: int = 8
    history_turn_limit: int = 10

    log_format: str = "text"
    support_contact: str = "admin@brand.example"


    @property
    def chroma_path(self) -> Path:
        """Path absolut direktori persist ChromaDB."""
        return self._resolve(self.chroma_persist_dir)

    @property
    def faq_path(self) -> Path:
        """Path absolut direktori sumber dokumen FAQ."""
        return self._resolve(self.faq_source_dir)

    def require_supabase(self) -> tuple[str, str]:
        """Ambil kredensial Supabase, gagal keras kalau belum diset.

        Returns:
            Pasangan (url, service_key).

        Raises:
            ValueError: Kalau SUPABASE_URL atau SUPABASE_SERVICE_KEY kosong.
        """
        if not self.supabase_url or not self.supabase_service_key:
            raise ValueError(
                "SUPABASE_URL dan SUPABASE_SERVICE_KEY wajib diisi di .env"
            )
        return self.supabase_url, self.supabase_service_key

    def require_anthropic_key(self) -> str:
        """Ambil API key Anthropic, gagal keras kalau belum diset.

        Returns:
            Nilai ANTHROPIC_API_KEY.

        Raises:
            ValueError: Kalau ANTHROPIC_API_KEY kosong.
        """
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY wajib diisi di .env")
        return self.anthropic_api_key

    @staticmethod
    def _resolve(raw_path: str) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ambil instance Settings tunggal untuk seluruh proses."""
    return Settings()


settings = get_settings()
