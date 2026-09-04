"""Perakitan model juri untuk RAGAS dan DeepEval.

Juri memakai Claude API, terpisah dari Qwen3-1.7B yang diuji. Pemisahan itu
disengaja dan merupakan satu-satunya titik di branch ini yang menyentuh layanan
berbayar: juri adalah alat ukur, bukan bagian produk. Chatbot-nya tetap berjalan
penuh di lokal tanpa kunci API mana pun.

Embedding tetap lokal lewat Ollama karena Anthropic tidak menyediakan API
embedding, dan metrik yang memakainya hanya mengukur kemiripan vektor -- bukan
memberi penilaian yang mutunya bergantung pada kekuatan model.

Import ragas, deepeval, dan anthropic sengaja ditahan di dalam fungsi, bukan di
tingkat modul: berkas ini melayani beberapa pustaka sekaligus, dan import di
atas akan membuat perakitan juri RAGAS gagal hanya karena DeepEval belum
terpasang.
"""

from typing import Any

from openai import OpenAI

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Endpoint kompatibel Ollama memeriksa keberadaan header Authorization, tapi
# tidak memvalidasi isinya.
_PLACEHOLDER_KEY = "ollama"


def build_anthropic_client() -> Any:
    """Bangun client Claude untuk juri.

    Returns:
        Client anthropic yang sudah membawa kunci API.

    Raises:
        ValueError: Kalau ANTHROPIC_API_KEY belum diset.
    """
    from anthropic import Anthropic

    return Anthropic(api_key=settings.require_judge_key())


def build_embedding_client() -> OpenAI:
    """Bangun client HTTP ke endpoint kompatibel OpenAI milik Ollama.

    Dipakai hanya untuk embedding juri. Paket openai di sini murni transport;
    tidak ada akun maupun kunci OpenAI yang terlibat.

    Returns:
        Client yang menunjuk server Ollama lokal.
    """
    base_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
    logger.info(f"Client embedding juri diarahkan ke {base_url}")
    return OpenAI(api_key=_PLACEHOLDER_KEY, base_url=base_url)


def build_ragas_judge(client: Any | None = None) -> Any:
    """Bangun LLM juri untuk RAGAS.

    RAGAS meneruskan provider "anthropic" ke instructor.from_anthropic, jadi
    yang diharapkan adalah instance SDK anthropic apa adanya.

    temperature diset eksplisit karena default RAGAS 0.01, bukan 0. Selisihnya
    kecil, tapi alat ukur yang memberi skor berbeda pada masukan yang sama
    membuat perbandingan antar-run kehilangan arti.

    Args:
        client: Client anthropic; dibuat sendiri kalau tidak diberikan.

    Returns:
        Objek LLM RAGAS siap dipakai metrik.
    """
    from ragas.llms import llm_factory

    logger.info(f"Juri RAGAS: {settings.judge_model} (Claude API)")
    return llm_factory(
        settings.judge_model,
        provider="anthropic",
        client=client or build_anthropic_client(),
        temperature=settings.judge_temperature,
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
    resolved = client or build_embedding_client()

    try:
        from ragas.embeddings import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(
            client=resolved, model=settings.judge_embedding_model
        )
    except (ImportError, TypeError, ValueError) as exc:
        logger.info(f"Kelas OpenAIEmbeddings tidak terpakai ({exc}); mencoba factory")
        embeddings = _embeddings_via_factory(resolved)

    if embeddings is not None:
        logger.info(f"Embedding juri: {settings.judge_embedding_model} (Ollama lokal)")
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
        AnthropicModel yang bisa dioper ke metrik DeepEval mana pun.

    Raises:
        ValueError: Kalau ANTHROPIC_API_KEY belum diset.
    """
    from deepeval.models import AnthropicModel

    logger.info(f"Juri DeepEval: {settings.judge_model} (Claude API)")
    return AnthropicModel(
        model=settings.judge_model,
        api_key=settings.require_judge_key(),
        temperature=settings.judge_temperature,
    )
