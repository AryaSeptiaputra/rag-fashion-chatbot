"""Gerbang kesiapan LLM lokal sebelum aplikasi atau eval dijalankan.

Tiga hal dibuktikan berurutan, dari yang paling murah ke paling mahal:
server Ollama hidup dengan model yang benar, model bisa menjawab tanpa
membocorkan blok penalaran, dan model benar-benar memancarkan tool call.
Yang ketiga adalah kemampuan paling rapuh pada model 1.7B, dan paling mahal
kalau baru ketahuan di tengah eval 41 kasus.

Jalankan: python scripts/smoke_llm.py
"""

import asyncio
import sys

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.tools import FunctionTool

from app.config import settings
from app.dependencies import get_llm, probe_llm_ready
from app.utils.console import configure_console_encoding
from app.utils.errors import LLM_UNAVAILABLE_ERRORS, describe_llm_error
from app.utils.logger import setup_logger
from app.utils.text import strip_thinking

logger = setup_logger(__name__)

_PROBE_QUESTION = "Sisa stok SKU TSH-0001 berapa?"


def check_server() -> bool:
    """Periksa server Ollama dan ketersediaan model.

    Returns:
        True kalau siap.
    """
    ready, detail = probe_llm_ready()
    if not ready:
        logger.error(detail)
        return False

    logger.info(detail)
    return True


async def check_chat() -> bool:
    """Panggil model sekali dan pastikan keluarannya bersih.

    Returns:
        True kalau model menjawab dan jawabannya tidak memuat blok <think>.
    """
    llm = get_llm()
    try:
        response = await llm.achat(
            [
                ChatMessage(
                    role=MessageRole.USER,
                    content="Balas dengan satu kata saja: OK",
                )
            ]
        )
    except LLM_UNAVAILABLE_ERRORS as exc:
        logger.error(describe_llm_error(exc), exc_info=True)
        return False

    raw = str(response.message.content or "")
    if "<think>" in raw.lower():
        logger.error(
            "Keluaran model masih memuat blok <think>. Periksa LLM_THINKING di .env"
        )
        return False

    print(f"Jawaban model: {strip_thinking(raw)}")
    return True


async def check_tool_calling() -> bool:
    """Pastikan model benar-benar memanggil tool, bukan menjawab dari teks.

    Returns:
        True kalau tool dummy benar-benar dipanggil.
    """
    called: list[str] = []

    def cek_stok_demo(sku: str) -> str:
        """Cek sisa stok satu SKU.

        PAKAI setiap kali pembeli menanyakan ketersediaan atau sisa stok.

        Args:
            sku: SKU produk, mis. "TSH-0001".

        Returns:
            Sisa stok SKU tersebut.
        """
        called.append(sku)
        return f"SKU {sku}: sisa 3 potong."

    agent = FunctionAgent(
        tools=[FunctionTool.from_defaults(fn=cek_stok_demo, name="cek_stok_demo")],
        llm=get_llm(),
        system_prompt=(
            "Kamu asisten toko. Data stok hanya boleh berasal dari tool. "
            "Jangan pernah menebak angka stok."
        ),
    )

    try:
        await agent.run(user_msg=_PROBE_QUESTION, max_iterations=3)
    except LLM_UNAVAILABLE_ERRORS as exc:
        logger.error(describe_llm_error(exc), exc_info=True)
        return False
    except (RuntimeError, ValueError) as exc:
        logger.error(f"Agent gagal menyelesaikan probe tool: {exc}", exc_info=True)
        return False

    if not called:
        logger.error(
            f"Model {settings.llm_model} tidak memanggil tool untuk pertanyaan "
            f"'{_PROBE_QUESTION}'. Agent tidak akan bekerja dengan model ini."
        )
        return False

    print(f"Tool call terdeteksi: cek_stok_demo(sku={called[0]!r})")
    return True


async def run_checks() -> int:
    """Jalankan seluruh pemeriksaan berurutan.

    Returns:
        0 kalau semua lolos, 1 kalau ada yang gagal.
    """
    if not check_server():
        return 1
    if not await check_chat():
        return 1
    if not await check_tool_calling():
        return 1

    print(f"\nSmoke test lulus. {settings.llm_model} siap dipakai agent.")
    return 0


def main() -> int:
    """Entry point script smoke test.

    Returns:
        Exit code proses.
    """
    configure_console_encoding()
    logger.info(
        f"Menguji {settings.llm_model} di {settings.ollama_base_url} "
        f"(composer: {settings.composer_model})"
    )
    return asyncio.run(run_checks())


if __name__ == "__main__":
    sys.exit(main())
