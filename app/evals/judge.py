"""Perakitan model juri lokal untuk RAGAS dan DeepEval.

Keduanya dijalankan lewat Ollama. RAGAS 0.4 menuntut client yang sudah jadi
dan tidak lagi menyediakan wrapper LangChain maupun LlamaIndex, jadi jalurnya
adalah client `openai` yang diarahkan ke endpoint kompatibel milik Ollama.
Paket openai di sini murni transport HTTP; tidak ada akun maupun kunci OpenAI
yang terlibat.

Import ragas dan deepeval sengaja ditahan di dalam fungsi, bukan di tingkat
modul: berkas ini melayani dua pustaka sekaligus, dan import di atas akan
membuat perakitan juri RAGAS gagal hanya karena DeepEval belum terpasang.
"""

from typing import Any

from openai import OpenAI

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Endpoint kompatibel Ollama tetap memeriksa keberadaan header Authorization,
# tapi tidak memvalidasi isinya.
_PLACEHOLDER_KEY = "ollama"


def build_openai_compatible_client() -> OpenAI:
    """Bangun client HTTP ke endpoint kompatibel OpenAI milik Ollama.

    Returns:
        Client yang menunjuk server Ollama lokal.
    """
    base_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
    logger.info(f"Client juri diarahkan ke {base_url}")
    return OpenAI(api_key=_PLACEHOLDER_KEY, base_url=base_url)


def build_ragas_judge(client: OpenAI | None = None) -> Any:
    """Bangun LLM juri untuk RAGAS.

    Args:
        client: Client kompatibel OpenAI; dibuat sendiri kalau tidak diberikan.

    Returns:
        Objek LLM RAGAS siap dioper ke evaluate().
    """
    from ragas.llms import llm_factory

    logger.info(f"Juri RAGAS: {settings.judge_model}")
    return llm_factory(
        settings.judge_model,
        provider="openai",
        client=client or build_openai_compatible_client(),
    )


def build_ragas_embeddings(client: OpenAI | None = None) -> Any | None:
    """Bangun model embedding untuk metrik RAGAS yang membutuhkannya.

    Hanya AnswerRelevancy yang memakainya. RAGAS sedang memindahkan jalur ini
    dari embedding_factory ke kelas provider, jadi keduanya dicoba berurutan.
    Kalau dua-duanya gagal, fungsi mengembalikan None dan metrik tersebut
    dilepas: satu metrik tidak boleh menggugurkan seluruh run.

    Args:
        client: Client kompatibel OpenAI; dibuat sendiri kalau tidak diberikan.

    Returns:
        Objek embedding RAGAS, atau None kalau tidak bisa dirakit.
    """
    resolved = client or build_openai_compatible_client()

    try:
        from ragas.embeddings import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(
            client=resolved, model=settings.judge_embedding_model
        )
    except (ImportError, TypeError, ValueError) as exc:
        logger.info(f"Kelas OpenAIEmbeddings tidak terpakai ({exc}); mencoba factory")
        embeddings = _embeddings_via_factory(resolved)

    if embeddings is not None:
        logger.info(f"Embedding juri: {settings.judge_embedding_model}")
    return embeddings


def _embeddings_via_factory(client: OpenAI) -> Any | None:
    """Jalur lama embedding_factory, dipakai kalau kelas provider tidak cocok."""
    try:
        from ragas.embeddings.base import embedding_factory

        return embedding_factory(
            settings.judge_embedding_model, provider="openai", client=client
        )
    except (ImportError, TypeError, ValueError) as exc:
        logger.warning(
            f"Embedding juri '{settings.judge_embedding_model}' tidak bisa dirakit: "
            f"{exc}. AnswerRelevancy akan dilewati dan dicatat di laporan."
        )
        return None


def build_deepeval_judge() -> Any:
    """Bangun model juri untuk DeepEval.

    Returns:
        OllamaModel yang bisa dioper ke metrik DeepEval mana pun.
    """
    from deepeval.models import OllamaModel

    logger.info(f"Juri DeepEval: {settings.judge_model}")
    return OllamaModel(
        model=settings.judge_model,
        base_url=settings.ollama_base_url,
        temperature=settings.judge_temperature,
    )
