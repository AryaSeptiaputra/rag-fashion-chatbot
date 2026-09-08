"""Entry point aplikasi FastAPI."""

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat.routes import router as chat_router
from app.api.demo.routes import router as demo_router
from app.api.guards import AnggaranHarian, KuotaHarian
from app.api.identity import RegistriSesi
from app.config import PROJECT_ROOT, settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

WEB_DIR = PROJECT_ROOT / "web"


def create_app() -> FastAPI:
    """Bangun instance FastAPI beserta router, pengaman, dan frontend-nya.

    Returns:
        Aplikasi FastAPI siap dijalankan.
    """
    application = FastAPI(
        title="RAG Fashion Chatbot",
        description=(
            "Customer service AI untuk clothing brand: menjawab FAQ, "
            "ketersediaan stok, detail produk, dan status pesanan."
        ),
        version="0.1.0",
    )

    # Pengaman hidup di app.state, bukan sebagai global modul: setiap test
    # memanggil create_app() sendiri, dan global akan membocorkan hitungan
    # kuota antar-test lalu memunculkan 429 yang tidak bisa ditebak.
    application.state.anggaran = AnggaranHarian(settings.demo_daily_budget_usd)
    application.state.kuota_pengunjung = KuotaHarian(
        settings.demo_visitor_daily_quota, "kuota_pengunjung_habis"
    )
    application.state.kuota_ip = KuotaHarian(
        settings.demo_ip_daily_quota, "kuota_ip_habis"
    )
    application.state.registri_sesi = RegistriSesi()
    application.state.kunci_warmup = threading.Lock()

    _pasang_cors(application)
    application.include_router(chat_router)
    application.include_router(demo_router)
    _pasang_frontend(application)

    logger.info("Aplikasi FastAPI siap")
    return application


def _pasang_cors(application: FastAPI) -> None:
    """Pasang CORS hanya kalau ada asal lintas domain yang diizinkan.

    Frontend disajikan dari proses yang sama, jadi same-origin dan tidak butuh
    CORS sama sekali. Tidak memasang middleware lebih aman daripada memasang
    yang permisif; setelan ini hanya untuk pengembangan, saat halaman dibuka
    langsung dari disk.

    Args:
        application: Aplikasi yang sedang dibangun.
    """
    asal = [
        bagian.strip()
        for bagian in settings.cors_allow_origins.split(",")
        if bagian.strip()
    ]
    if not asal:
        return

    application.add_middleware(
        CORSMiddleware,
        allow_origins=asal,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    logger.info(f"CORS diaktifkan untuk: {asal}")


def _pasang_frontend(application: FastAPI) -> None:
    """Sajikan frontend statis tanpa menutupi rute API.

    Berkas statis sengaja dipasang di /static dan halaman utama sebagai rute
    eksplisit, bukan mount di "/". Mount di akar akan menangkap setiap path yang
    belum ter-route, sehingga salah ketik seperti /api/v1/chats menghasilkan 404
    teks polos dari StaticFiles alih-alih 404 JSON yang bisa dibaca.

    Args:
        application: Aplikasi yang sedang dibangun.
    """
    if not WEB_DIR.is_dir():
        logger.warning(f"Direktori frontend tidak ada di {WEB_DIR}; API tetap jalan")
        return

    application.mount(
        "/static", StaticFiles(directory=WEB_DIR / "static"), name="static"
    )

    @application.get("/", include_in_schema=False)
    def halaman_utama() -> FileResponse:
        """Kirim satu-satunya dokumen HTML frontend."""
        return FileResponse(WEB_DIR / "index.html")

    logger.info(f"Frontend disajikan dari {WEB_DIR}")


app = create_app()
