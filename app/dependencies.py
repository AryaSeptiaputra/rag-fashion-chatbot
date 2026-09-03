"""Factory client eksternal yang dipakai bersama oleh API, script, dan UI.

Semua factory di-cache karena pembuatannya mahal: model embedding memuat bobot
ke memori, dan client Chroma membuka koneksi ke direktori persist.
"""

from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from supabase import Client, create_client

from app.config import settings
from app.utils.anthropic_compat import CompatAnthropic
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Model keluarga e5 dilatih dengan prefix asimetris: query dan dokumen harus
# diberi penanda berbeda, kalau tidak kualitas retrieval turun drastis.
_E5_QUERY_PREFIX = "query: "
_E5_TEXT_PREFIX = "passage: "


@lru_cache(maxsize=1)
def get_llm() -> CompatAnthropic:
    """Bangun client LLM Claude untuk agent.

    Returns:
        Wrapper LlamaIndex untuk Claude, memakai model dari setting.

    Raises:
        ValueError: Kalau ANTHROPIC_API_KEY belum diset.
    """
    api_key = settings.require_anthropic_key()
    logger.info(f"Menginisialisasi LLM {settings.llm_model}")
    return CompatAnthropic(
        model=settings.llm_model,
        api_key=api_key,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )


@lru_cache(maxsize=1)
def get_embedding_model() -> BaseEmbedding:
    """Muat model embedding HuggingFace lokal.

    Returns:
        Embedding model dengan prefix e5 yang sudah dipasang.
    """
    is_e5 = "e5" in settings.embedding_model.lower()
    logger.info(f"Memuat embedding model {settings.embedding_model}")
    return HuggingFaceEmbedding(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        query_instruction=_E5_QUERY_PREFIX if is_e5 else None,
        text_instruction=_E5_TEXT_PREFIX if is_e5 else None,
    )


@lru_cache(maxsize=1)
def get_chroma_client() -> ClientAPI:
    """Bangun client ChromaDB yang menulis ke direktori persist.

    Returns:
        Client Chroma persisten.
    """
    persist_dir = settings.chroma_path
    persist_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Membuka ChromaDB di {persist_dir}")
    return chromadb.PersistentClient(path=str(persist_dir))


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Bangun client Supabase dengan service-role key.

    Returns:
        Client Supabase.

    Raises:
        ValueError: Kalau kredensial Supabase belum diset.
    """
    url, key = settings.require_supabase()
    logger.info("Menginisialisasi client Supabase")
    return create_client(url, key)
