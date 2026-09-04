"""Resolusi kelas exception pihak ketiga yang nama/lokasinya berubah antar versi."""

import httpx
from ollama import ResponseError as _OllamaResponseError

from app.config import settings

# ChromaDB memindahkan kelas exception "koleksi tidak ada" antar versi minor,
# jadi di-resolve sekali saat import dengan fallback yang aman.
try:
    from chromadb.errors import NotFoundError as _ChromaNotFoundError

    COLLECTION_MISSING_ERRORS: tuple[type[Exception], ...] = (
        _ChromaNotFoundError,
        ValueError,
        KeyError,
    )
except ImportError:  # pragma: no cover - hanya untuk versi ChromaDB lama
    COLLECTION_MISSING_ERRORS = (ValueError, KeyError)


# Kegagalan menghubungi LLM lokal. httpx.TransportError menampung connect
# error dan timeout sekaligus; ollama.ResponseError adalah error tingkat HTTP
# dari server Ollama, mis. tag model belum di-pull.
LLM_UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    _OllamaResponseError,
    httpx.TransportError,
    ConnectionError,
)


def describe_llm_error(exc: Exception) -> str:
    """Susun pesan kegagalan LLM yang menyebut langkah perbaikannya.

    Operator varian lokal hampir selalu berhadapan dengan dua penyebab yang
    sama: server Ollama mati, atau tag model belum di-pull. Pesan generik
    "layanan AI tidak bisa dihubungi" tidak membedakan keduanya.

    Args:
        exc: Exception yang tertangkap dari jalur pemanggilan LLM.

    Returns:
        Pesan siap tampil untuk operator.
    """
    if isinstance(exc, _OllamaResponseError):
        return (
            f"Ollama menolak permintaan: {exc}. "
            f"Pastikan model sudah di-pull: ollama pull {settings.llm_model}"
        )
    if isinstance(exc, httpx.TimeoutException):
        return (
            f"Model lokal tidak selesai menjawab dalam "
            f"{settings.llm_request_timeout:.0f} detik."
        )
    return (
        f"Ollama di {settings.ollama_base_url} tidak bisa dihubungi. "
        "Pastikan servernya jalan (ollama serve)."
    )
