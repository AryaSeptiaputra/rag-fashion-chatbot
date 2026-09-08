"""Endpoint data acuan untuk halaman panduan demo."""

from functools import lru_cache

from fastapi import APIRouter, Response

from app.dependencies import get_supabase_client
from app.models.demo import DemoFacts
from app.repositories.demo import DemoRepository
from app.services.demo_facts import DemoFactsService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@lru_cache(maxsize=1)
def _layanan() -> DemoFactsService:
    """Rakit DemoFactsService sekali per proses.

    Returns:
        Service beserta cache TTL-nya.
    """
    return DemoFactsService(DemoRepository(get_supabase_client()))


@router.get("/facts", response_model=DemoFacts)
def facts(response: Response, refresh: bool = False) -> DemoFacts:
    """Kirim SKU, nomor pesanan, dan kode promo yang benar-benar ada.

    Tanpa data ini pengunjung harus mengarang SKU, dan tiga dari delapan tool
    praktis mustahil dicoba -- chatbot lalu terlihat bodoh justru ketika ia
    berperilaku benar dengan menolak mengarang.

    Kegagalan database dijawab 200 dengan available=false, bukan 502: halaman
    panduan adalah hal pertama yang dilihat pengunjung, dan blok contoh yang
    disembunyikan jauh lebih baik daripada kotak error merah di sana.

    Args:
        response: Respons yang akan dikirim; header cache diatur di sini.
        refresh: Lewati cache dan baca ulang dari database.

    Returns:
        Data acuan halaman panduan.
    """
    try:
        fakta = _layanan().collect(refresh=refresh)
    except ValueError as exc:
        # Kredensial Supabase belum diisi; tetap 200 dengan alasan yang tercatat.
        logger.error(f"Data acuan demo tidak tersedia: {exc}")
        return DemoFacts(available=False)

    if fakta.available:
        response.headers["Cache-Control"] = "public, max-age=300"
    return fakta
