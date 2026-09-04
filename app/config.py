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

    ollama_base_url: str = "http://localhost:11434"

    # LLM utama: memilih dan memanggil tool.
    llm_model: str = "qwen3:1.7b"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.2
    llm_context_window: int = 8192
    llm_request_timeout: float = 180.0
    llm_keep_alive: str = "10m"
    llm_thinking: bool = False

    # LLM penyusun jawaban akhir: tanpa tool, sampling lebih dingin.
    composer_model: str = "qwen3:1.7b"
    composer_max_tokens: int = 512
    composer_temperature: float = 0.1
    composer_history_turns: int = 2

    # Model juri untuk RAGAS dan DeepEval, memakai Claude API.
    #
    # Ini satu-satunya tempat di branch ini yang menyentuh API berbayar, dan
    # itu disengaja: juri adalah alat ukur, bukan bagian produk. Chatbot-nya
    # sendiri tetap berjalan penuh di lokal tanpa kunci API mana pun. Memakai
    # model yang diuji untuk menilai jawabannya sendiri bukan pengukuran, dan
    # juri 7B lokal menilai terlalu berisik untuk dipercaya.
    anthropic_api_key: str = ""
    judge_model: str = "claude-haiku-4-5"
    judge_temperature: float = 0.0

    # Embedding juri tetap lokal: Anthropic tidak menyediakan API embedding,
    # dan metrik yang memakainya hanya mengukur kemiripan, bukan menilai.
    judge_embedding_model: str = "nomic-embed-text"

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

    agent_max_iterations: int = 5
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

    @property
    def ollama_tags_url(self) -> str:
        """URL endpoint daftar model yang sudah ter-pull di Ollama."""
        return f"{self.ollama_base_url.rstrip('/')}/api/tags"

    def require_judge_key(self) -> str:
        """Ambil kunci Claude untuk juri eval, gagal keras kalau belum diset.

        Hanya harness eval yang memanggil ini. Aplikasi chatbot tidak pernah
        membutuhkannya, jadi kunci yang kosong tidak boleh menghalangi apa pun
        selain penilaian mutu.

        Returns:
            Nilai ANTHROPIC_API_KEY.

        Raises:
            ValueError: Kalau ANTHROPIC_API_KEY kosong.
        """
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY wajib diisi untuk menjalankan penilaian mutu. "
                "Chatbot-nya sendiri tidak membutuhkannya."
            )
        return self.anthropic_api_key

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

    @staticmethod
    def _resolve(raw_path: str) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ambil instance Settings tunggal untuk seluruh proses."""
    return Settings()


settings = get_settings()
