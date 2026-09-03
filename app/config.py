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

    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Dipakai Streamlit UI untuk memanggil REST API.",
    )

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
