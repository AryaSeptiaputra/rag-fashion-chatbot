"""Gerbang kompatibilitas: pastikan wrapper LLM LlamaIndex jalan dengan SDK anthropic terpasang.

Paket llama-index-llms-anthropic menyatakan anthropic>=0.75.0 tanpa batas atas,
sementara anthropic 1.x sudah pindah dari httpx ke httpx2. Script ini memanggil
API sekali dengan prompt sangat pendek untuk membuktikan jalur itu benar-benar
bekerja sebelum sisa aplikasi dibangun di atasnya.

Jalankan: python scripts/smoke_llm.py
"""

import sys

import anthropic
from llama_index.core.base.llms.types import ChatMessage, MessageRole

from app.config import settings
from app.dependencies import get_llm
from app.utils.console import configure_console_encoding
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def main() -> int:
    """Panggil LLM sekali dan laporkan hasilnya.

    Returns:
        0 kalau berhasil, 1 kalau gagal.
    """
    configure_console_encoding()

    try:
        settings.require_anthropic_key()
    except ValueError as exc:
        logger.error(f"Konfigurasi belum lengkap: {exc}")
        return 1

    logger.info(
        f"Menguji {settings.llm_model} lewat wrapper LlamaIndex "
        f"(anthropic SDK {anthropic.__version__})"
    )

    try:
        llm = get_llm()
        response = llm.chat(
            [
                ChatMessage(
                    role=MessageRole.USER,
                    content="Balas dengan satu kata saja: OK",
                )
            ]
        )
    except anthropic.AuthenticationError:
        logger.error("ANTHROPIC_API_KEY ditolak. Periksa kembali nilainya di .env")
        return 1
    except anthropic.NotFoundError:
        logger.error(
            f"Model '{settings.llm_model}' tidak ditemukan. "
            "Periksa nilai LLM_MODEL di .env"
        )
        return 1
    except anthropic.APIStatusError as exc:
        logger.error(f"Claude API mengembalikan error {exc.status_code}: {exc.message}")
        return 1
    except anthropic.APIConnectionError:
        logger.error("Gagal terhubung ke Claude API. Periksa koneksi internet.")
        return 1
    except TypeError as exc:
        logger.error(
            f"Wrapper LlamaIndex tidak kompatibel dengan anthropic "
            f"{anthropic.__version__}: {exc}",
            exc_info=True,
        )
        return 1

    print(f"Smoke test lulus. Jawaban model: {response.message.content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
