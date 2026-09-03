"""Penyesuaian encoding console untuk script yang mencetak keluaran model."""

import sys
from typing import TextIO


def configure_console_encoding() -> None:
    """Paksa stdout dan stderr memakai UTF-8 dengan fallback aman.

    Console Windows memakai code page ANSI (cp1252 untuk locale Indonesia),
    yang tidak bisa mencetak emoji maupun sebagian tanda baca tipografis.
    Jawaban Claude rutin memuat keduanya, sehingga print() bisa melempar
    UnicodeEncodeError dan menghentikan script di tengah jalan -- terutama
    scripts/run_eval.py yang mencetak jawaban apa adanya.

    errors="replace" dipilih agar karakter yang tidak terwakili diganti tanda
    tanya alih-alih menjatuhkan proses; laporan JSON tetap menyimpan teks utuh.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Stream yang sudah di-redirect ke pipa non-teks tidak bisa
            # dikonfigurasi ulang; biarkan apa adanya.
            continue


def safe_text(value: str, stream: TextIO | None = None) -> str:
    """Buang karakter yang tidak bisa dicetak stream tujuan.

    Dipakai sebagai jaring pengaman kalau configure_console_encoding gagal,
    misalnya saat keluaran dialihkan ke file dengan encoding tetap.

    Args:
        value: Teks yang akan dicetak.
        stream: Stream tujuan; default sys.stdout.

    Returns:
        Teks yang aman dicetak ke stream tersebut.
    """
    target = stream or sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")
