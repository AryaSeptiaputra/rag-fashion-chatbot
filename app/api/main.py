"""Entry point aplikasi FastAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat.routes import router as chat_router
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def create_app() -> FastAPI:
    """Bangun instance FastAPI beserta router dan middleware-nya.

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

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    application.include_router(chat_router)
    logger.info("Aplikasi FastAPI siap")
    return application


app = create_app()
