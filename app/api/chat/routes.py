"""Endpoint HTTP untuk percakapan chatbot."""

import time

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.chat.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionResponse,
    ToolCallInfo,
    WarmupResponse,
    WarmupStep,
)
from app.api.chat.service import _cached_chatbot_service, get_chat_service
from app.api.guards import baca_ip_klien
from app.api.identity import baca_atau_terbitkan
from app.config import settings
from app.dependencies import (
    get_chroma_client,
    get_embedding_model,
    get_supabase_client,
)
from app.repositories.base import RepositoryError
from app.services.chatbot import ChatbotService
from app.tools.registry import resolve_source
from app.utils.errors import COLLECTION_MISSING_ERRORS
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/session", response_model=SessionResponse)
def buat_sesi(request: Request, response: Response) -> SessionResponse:
    """Terbitkan sesi percakapan baru untuk pengunjung ini.

    session_id sengaja diterbitkan server, bukan dikarang klien: kalau klien
    yang menentukannya, siapa pun yang tahu id orang lain bisa melanjutkan
    percakapan orang itu, dan jatah bertanya bisa direset hanya dengan membuat
    id baru.

    Args:
        request: Permintaan masuk.
        response: Respons yang akan dikirim; cookie identitas dipasang di sini.

    Returns:
        Sesi baru beserta sisa jatah dan anggaran.
    """
    visitor_id = baca_atau_terbitkan(request, response)
    session_id = request.app.state.registri_sesi.terbitkan(visitor_id)

    logger.info(f"Sesi {session_id} diterbitkan untuk pengunjung {visitor_id}")
    return SessionResponse(
        session_id=session_id,
        budget=request.app.state.anggaran.status(),
        quota=request.app.state.kuota_pengunjung.status(visitor_id),
        stub=settings.demo_stub_llm,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    response: Response,
    service: ChatbotService = Depends(get_chat_service),
) -> ChatResponse:
    """Jawab satu pesan pembeli.

    Args:
        request: Pesan pembeli beserta session_id, kanal, dan bahasa.
        http_request: Permintaan HTTP mentah, dipakai membaca identitas dan IP.
        response: Respons yang akan dikirim.
        service: ChatbotService hasil dependency injection.

    Returns:
        Jawaban chatbot beserta sumber, biaya, dan sisa jatahnya.

    Raises:
        HTTPException: 403 kalau sesi milik pengunjung lain, 429 kalau jatah
            atau anggaran habis, 502 kalau layanan hulu gagal, 503 kalau
            komponen belum siap.
    """
    state = http_request.app.state
    visitor_id = baca_atau_terbitkan(http_request, response)

    if not state.registri_sesi.dimiliki_oleh(request.session_id, visitor_id):
        # Bisa berarti sesi milik orang lain, atau sesi lama yang sudah hilang
        # karena server restart. Keduanya dijawab sama: minta klien memulai sesi
        # baru lewat /session, jangan diam-diam dilayani.
        logger.warning(f"Sesi {request.session_id} bukan milik {visitor_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "sesi_tidak_dikenali"},
        )

    # Plafon anggaran diperiksa lebih dulu supaya permintaan yang pasti ditolak
    # tidak ikut memakan jatah pengunjung.
    state.anggaran.pastikan_tersedia()
    kuota = state.kuota_pengunjung.pakai(visitor_id)
    state.kuota_ip.pakai(baca_ip_klien(http_request))

    mulai = time.perf_counter()
    try:
        reply = await service.answer(
            session_id=request.session_id,
            message=request.message,
            channel=request.channel,
            language=request.language,
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

    latency_ms = int((time.perf_counter() - mulai) * 1000)
    state.anggaran.catat(reply.cost_usd)

    return ChatResponse(
        session_id=request.session_id,
        answer=reply.answer,
        tool_calls=[
            ToolCallInfo(
                tool_name=call.tool_name,
                arguments=call.arguments,
                is_error=call.is_error,
                latency_ms=call.latency_ms,
                source=resolve_source(call.tool_name),
            )
            for call in reply.tool_calls
        ],
        mode=reply.mode,
        citations=reply.citations,
        usage=reply.usage,
        cost_usd=reply.cost_usd,
        budget=state.anggaran.status(),
        quota=kuota,
        latency_ms=latency_ms,
        stub=reply.stub,
    )


@router.post("/warmup", response_model=WarmupResponse)
def warmup(request: Request) -> WarmupResponse:
    """Panaskan seluruh komponen berat tanpa memanggil Claude sama sekali.

    Dipanggil saat halaman panduan dibuka, supaya pemuatan model embedding yang
    memakan 30-90 detik berlangsung selagi pengunjung membaca, bukan setelah ia
    mengetik pertanyaan pertama.

    Sengaja didefinisikan sinkron: memuat bobot model ratusan megabita di dalam
    event loop akan membekukan setiap permintaan lain. Route sinkron dijalankan
    FastAPI di threadpool, sama seperti health().

    POST, bukan GET, supaya prefetcher peramban dan crawler tidak bisa memicu
    pemuatan seberat itu tanpa sengaja.

    Args:
        request: Permintaan masuk.

    Returns:
        Hasil tiap langkah pemanasan beserta status kesiapan.
    """
    mulai = time.perf_counter()
    steps: list[WarmupStep] = []
    faq_chunks = 0

    with request.app.state.kunci_warmup:
        steps.append(_langkah("embedding_model", lambda: get_embedding_model()))

        def buka_chroma() -> None:
            nonlocal faq_chunks
            collection = get_chroma_client().get_collection(settings.chroma_collection)
            faq_chunks = collection.count()

        steps.append(
            _langkah("chroma", buka_chroma, dilewati=COLLECTION_MISSING_ERRORS)
        )
        steps.append(_langkah("supabase", lambda: get_supabase_client()))
        steps.append(_langkah("chatbot_service", lambda: _cached_chatbot_service()))

    return WarmupResponse(
        ready=all(step.ok for step in steps) and faq_chunks > 0,
        steps=steps,
        total_ms=int((time.perf_counter() - mulai) * 1000),
        llm_model=settings.llm_model,
        faq_chunks=faq_chunks,
        stub=settings.demo_stub_llm,
        budget=request.app.state.anggaran.status(),
    )


def _langkah(
    nama: str,
    kerjakan: object,
    dilewati: tuple[type[Exception], ...] = (),
) -> WarmupStep:
    """Jalankan satu langkah pemanasan dan catat hasilnya.

    Tiap langkah punya try sendiri supaya satu kegagalan tidak menutupi status
    langkah lainnya -- alasan yang sama dengan pemisahan probe di health().

    Args:
        nama: Nama langkah untuk ditampilkan.
        kerjakan: Callable tanpa argumen yang melakukan pemanasan.
        dilewati: Exception tambahan yang dianggap kegagalan wajar.

    Returns:
        Hasil langkah beserta lamanya.
    """
    mulai = time.perf_counter()
    try:
        kerjakan()  # type: ignore[operator]
        ok, detail = True, None
    except (ValueError, RuntimeError, OSError, *dilewati) as exc:
        logger.warning(f"Pemanasan '{nama}' gagal: {exc}")
        ok, detail = False, str(exc)

    return WarmupStep(
        name=nama,
        ok=ok,
        ms=int((time.perf_counter() - mulai) * 1000),
        detail=detail,
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
