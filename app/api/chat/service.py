"""Perakitan dependency untuk endpoint chat.

Seluruh objek berat (LLM, embedding model, client Chroma, client Supabase)
diambil dari factory ber-cache di app.dependencies, jadi ChatbotService di sini
hanya merangkai, bukan membuat ulang tiap request.
"""

from functools import lru_cache

from fastapi import HTTPException

from app.dependencies import (
    get_chroma_client,
    get_composer_llm,
    get_embedding_model,
    get_llm,
    get_supabase_client,
)
from app.repositories.catalog import CatalogRepository
from app.repositories.chat import ChatRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.sales import SalesRepository
from app.repositories.sizing import SizingRepository
from app.services.catalog import CatalogService
from app.services.chatbot import ChatbotService
from app.services.composer import AnswerComposer
from app.services.inventory import InventoryService
from app.services.memory import ConversationMemory
from app.services.order import OrderService
from app.services.retrieval import FAQRetriever
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def build_chatbot_service() -> ChatbotService:
    """Rakit ChatbotService lengkap dengan seluruh dependensinya.

    Returns:
        ChatbotService siap pakai.

    Raises:
        ValueError: Kalau kredensial Supabase belum diset.
    """
    supabase = get_supabase_client()
    chroma = get_chroma_client()
    embed_model = get_embedding_model()

    catalog_repository = CatalogRepository(supabase)
    inventory_repository = InventoryRepository(supabase)
    sizing_repository = SizingRepository(supabase)
    sales_repository = SalesRepository(supabase)
    chat_repository = ChatRepository(supabase)

    return ChatbotService(
        llm=get_llm(),
        composer=AnswerComposer(llm=get_composer_llm()),
        faq_retriever=FAQRetriever(chroma_client=chroma, embed_model=embed_model),
        catalog_service=CatalogService(catalog_repository, sales_repository),
        inventory_service=InventoryService(inventory_repository, sizing_repository),
        order_service=OrderService(sales_repository),
        memory=ConversationMemory(chat_repository),
    )


@lru_cache(maxsize=1)
def _cached_chatbot_service() -> ChatbotService:
    """Rakit ChatbotService sekali per proses.

    Returns:
        ChatbotService yang di-cache.
    """
    logger.info("Merakit ChatbotService")
    return build_chatbot_service()


def get_chat_service() -> ChatbotService:
    """Dependency FastAPI untuk ChatbotService.

    Kegagalan perakitan diterjemahkan jadi HTTPException di sini, bukan di
    handler: dependency di-resolve sebelum badan handler dijalankan, jadi
    try/except di dalam handler tidak akan pernah melihat error ini.
    lru_cache tidak menyimpan exception, sehingga request berikutnya mencoba
    lagi setelah konfigurasi diperbaiki.

    Returns:
        ChatbotService siap pakai.

    Raises:
        HTTPException: 503 kalau kredensial atau komponen belum siap.
    """
    try:
        return _cached_chatbot_service()
    except (ValueError, RuntimeError) as exc:
        logger.error(f"ChatbotService belum bisa dirakit: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"Layanan belum siap: {exc}",
        ) from exc
