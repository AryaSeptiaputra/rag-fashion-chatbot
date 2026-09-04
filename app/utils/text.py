"""Pembersih teks keluaran model sebelum dibaca pembeli."""

import re

# Qwen3 adalah model hybrid-thinking: walau think dimatikan di level API,
# template chat sesekali masih memancarkan blok penalaran sebagai teks biasa.
# Blok itu tidak boleh sampai ke pembeli, jadi dibuang di sini apa pun kondisinya.
_CLOSED_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINKING = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)
_STRAY_TAG = re.compile(r"</?think>", re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Buang blok penalaran <think> dari keluaran model.

    Blok yang tidak tertutup ikut dibuang sampai akhir teks: jawaban yang
    terpotong di tengah penalaran lebih baik hilang sama sekali daripada
    terkirim setengah jadi ke pembeli.

    Args:
        text: Teks mentah dari model.

    Returns:
        Teks tanpa blok penalaran, sudah di-strip spasi tepi.
    """
    cleaned = _CLOSED_THINKING.sub("", text)
    cleaned = _UNCLOSED_THINKING.sub("", cleaned)
    return _STRAY_TAG.sub("", cleaned).strip()
