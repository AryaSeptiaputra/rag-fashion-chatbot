"""Factory client eksternal yang dipakai bersama oleh API, script, dan UI.

Semua factory di-cache karena pembuatannya mahal: model embedding memuat bobot
ke memori, dan client Chroma membuka koneksi ke direktori persist.
"""

from functools import lru_cache

import chromadb
import httpx
from chromadb.api import ClientAPI
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from supabase import Client, create_client

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Model keluarga e5 dilatih dengan prefix asimetris: query dan dokumen harus
# diberi penanda berbeda, kalau tidak kualitas retrieval turun drastis.
_E5_QUERY_PREFIX = "query: "
_E5_TEXT_PREFIX = "passage: "

_PROBE_TIMEOUT_SECONDS = 2.0


@lru_cache(maxsize=1)
def get_llm() -> Ollama:
    """Bangun LLM utama yang memilih dan memanggil tool.

    is_function_calling_model wajib True: FunctionAgent membaca flag itu dari
    metadata dan menolak wrapper yang mengaku tidak bisa memanggil tool.

    Returns:
        Wrapper LlamaIndex untuk model Ollama sesuai setting.
    """
    logger.info(f"Menginisialisasi LLM utama {settings.llm_model} lewat Ollama")
    return Ollama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        context_window=settings.llm_context_window,
        request_timeout=settings.llm_request_timeout,
        keep_alive=settings.llm_keep_alive,
        thinking=settings.llm_thinking,
        is_function_calling_model=True,
        additional_kwargs={"num_predict": settings.llm_max_tokens},
    )


@lru_cache(maxsize=1)
def get_composer_llm() -> Ollama:
    """Bangun LLM penyusun jawaban akhir.

    Dibuat sebagai instance terpisah, bukan get_llm() yang di-mutate, supaya
    temperature dan batas token kedua peran tidak saling menimpa. Keduanya
    menunjuk tag model yang sama, jadi Ollama tetap memuat satu salinan bobot.

    Returns:
        Wrapper LlamaIndex dengan sampling yang lebih dingin dan tanpa tool.
    """
    logger.info(f"Menginisialisasi LLM composer {settings.composer_model}")
    return Ollama(
        model=settings.composer_model,
        base_url=settings.ollama_base_url,
        temperature=settings.composer_temperature,
        context_window=settings.llm_context_window,
        request_timeout=settings.llm_request_timeout,
        keep_alive=settings.llm_keep_alive,
        thinking=settings.llm_thinking,
        is_function_calling_model=False,
        additional_kwargs={"num_predict": settings.composer_max_tokens},
    )


def probe_llm_ready() -> tuple[bool, str]:
    """Periksa server Ollama hidup dan model yang dipakai sudah ter-pull.

    Dipanggil dari endpoint health. Mode kegagalan paling sering di varian
    lokal adalah server belum jalan atau model belum di-pull; keduanya harus
    terlihat sebelum pembeli mengirim pesan, bukan muncul sebagai 502 di
    tengah percakapan.

    Returns:
        Pasangan (siap, keterangan). Keterangan berisi langkah perbaikan
        kalau belum siap.
    """
    try:
        response = httpx.get(settings.ollama_tags_url, timeout=_PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        tags = {model["name"] for model in response.json().get("models", [])}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning(f"Ollama belum siap: {exc}")
        return False, (
            f"Ollama di {settings.ollama_base_url} tidak merespons. "
            "Jalankan: ollama serve"
        )

    missing = [
        name
        for name in {settings.llm_model, settings.composer_model}
        if name not in tags and f"{name}:latest" not in tags
    ]
    if missing:
        return False, "Model belum di-pull: " + ", ".join(
            f"ollama pull {name}" for name in sorted(missing)
        )

    return True, f"Ollama siap dengan {len(tags)} model ter-pull"


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
