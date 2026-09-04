"""Perakitan model juri DeepEval.

Juri memakai Claude API, terpisah dari Qwen3-1.7B yang diuji. Pemisahan itu
disengaja dan merupakan satu-satunya titik di branch ini yang menyentuh layanan
berbayar: juri adalah alat ukur, bukan bagian produk. Chatbot-nya tetap berjalan
penuh di lokal tanpa kunci API mana pun.

Import anthropic dan deepeval sengaja ditahan di dalam fungsi, bukan di tingkat
modul, supaya kegagalan memasang salah satunya tidak membuat modul ini gagal
di-import seluruhnya.
"""

from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def build_anthropic_client() -> Any:
    """Bangun client Claude untuk juri.

    Returns:
        Client anthropic yang sudah membawa kunci API.

    Raises:
        ValueError: Kalau ANTHROPIC_API_KEY belum diset.
    """
    from anthropic import Anthropic

    return Anthropic(api_key=settings.require_judge_key())


def build_deepeval_judge() -> Any:
    """Bangun model juri untuk metrik DeepEval.

    Returns:
        AnthropicModel yang bisa dioper ke metrik DeepEval mana pun.

    Raises:
        ValueError: Kalau ANTHROPIC_API_KEY belum diset.
    """
    from deepeval.models import AnthropicModel

    logger.info(f"Juri DeepEval: {settings.judge_model} (Claude API)")
    return AnthropicModel(
        model=settings.judge_model,
        api_key=settings.require_judge_key(),
        temperature=settings.judge_temperature,
    )
