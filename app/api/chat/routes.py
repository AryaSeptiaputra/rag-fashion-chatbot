"""Endpoint HTTP untuk percakapan chatbot."""

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from app.api.chat.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ToolCallInfo,
)
from app.api.chat.service import get_chat_service
from app.config import settings
from app.dependencies import get_chroma_client, get_supabase_client
from app.repositories.base import RepositoryError
from app.services.chatbot import ChatbotService
from app.utils.errors import COLLECTION_MISSING_ERRORS
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatbotService = Depends(get_chat_service),
) -> ChatResponse:
    """Jawab satu pesan pembeli.

    Args:
        request: Pesan pembeli beserta session_id dan kanal.
        service: ChatbotService hasil dependency injection.

    Returns:
        Jawaban chatbot beserta jejak tool yang dipakai.

    Raises:
        HTTPException: 503 kalau index FAQ atau kredensial belum siap,
            502 kalau akses database gagal.
    """
    try:
        reply = await service.answer(
            session_id=request.session_id,
            message=request.message,
            channel=request.channel,
        )
    except RepositoryError as exc:
        logger.error(f"Akses database gagal: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except anthropic.RateLimitError as exc:
        logger.warning(f"Claude API membatasi laju permintaan: {exc}")
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan ke layanan AI. Coba lagi sebentar lagi.",
        ) from exc
    except anthropic.APIStatusError as exc:
        # Termasuk saldo kredit habis, API key ditolak, dan gangguan sisi Claude.
        # Tanpa penanganan ini, kegagalan tersebut muncul sebagai HTTP 500 tanpa
        # petunjuk apa pun bagi operator.
        logger.error(
            f"Claude API mengembalikan {exc.status_code}: {exc.message}", exc_info=True
        )
        raise HTTPException(
            status_code=502,
            detail=f"Layanan AI tidak bisa dihubungi ({exc.status_code}): {exc.message}",
        ) from exc
    except anthropic.APIConnectionError as exc:
        logger.error("Gagal terhubung ke Claude API", exc_info=True)
        raise HTTPException(
            status_code=502, detail="Layanan AI tidak bisa dihubungi."
        ) from exc
    except (ValueError, RuntimeError) as exc:
        logger.error(f"Layanan belum siap: {exc}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        session_id=request.session_id,
        answer=reply.answer,
        tool_calls=[
            ToolCallInfo(
                tool_name=call.tool_name,
                arguments=call.arguments,
                is_error=call.is_error,
                latency_ms=call.latency_ms,
            )
            for call in reply.tool_calls
        ],
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Laporkan kesiapan komponen: index FAQ dan koneksi Supabase.

    Kedua komponen diperiksa terpisah supaya kegagalan satu tidak menutupi
    status yang lain. Hitungan chunk dibaca langsung dari ChromaDB agar
    health check tidak perlu memuat model embedding yang berat.

    Returns:
        Status layanan; "degraded" kalau ada komponen yang belum siap.
    """
    faq_chunks = 0
    try:
        collection = get_chroma_client().get_collection(settings.chroma_collection)
        faq_chunks = collection.count()
    except COLLECTION_MISSING_ERRORS as exc:
        logger.warning(f"Index FAQ belum siap: {exc}")

    supabase_connected = False
    try:
        get_supabase_client()
        supabase_connected = True
    except ValueError as exc:
        logger.warning(f"Supabase belum siap: {exc}")

    is_ready = faq_chunks > 0 and supabase_connected
    return HealthResponse(
        status="ok" if is_ready else "degraded",
        llm_model=settings.llm_model,
        faq_chunks=faq_chunks,
        supabase_connected=supabase_connected,
    )
