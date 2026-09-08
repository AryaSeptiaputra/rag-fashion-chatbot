"""Pencatatan pemakaian token per giliran dan perhitungan biayanya.

Satu giliran percakapan yang memakai tool memicu beberapa panggilan Anthropic,
bukan satu. Objek respons agent LlamaIndex hanya membawa panggilan terakhir,
jadi akumulasi dilakukan di sisi client LLM (lihat app/utils/anthropic_compat.py)
dan disimpan di ContextVar supaya tiap request punya akumulatornya sendiri.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from app.config import settings
from app.models.chat import TokenUsage
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Akumulator giliran yang sedang berjalan. Isinya objek mutable dan HANYA boleh
# dimutasi, tidak pernah di-set ulang dari dalam giliran: workflow LlamaIndex
# menjalankan tiap langkah sebagai task terpisah yang mewarisi salinan konteks,
# dan set() di task anak tidak terlihat oleh task induk sementara mutasi pada
# objek yang sama terlihat di mana-mana.
_usage_giliran: ContextVar[TokenUsage | None] = ContextVar(
    "usage_giliran", default=None
)

# Bentuk respons yang tidak dikenal diperingatkan sekali saja; tanpa flag ini
# satu giliran bisa menulis lima baris log yang sama.
_sudah_memperingatkan = False


@contextmanager
def lacak_usage_giliran() -> Iterator[TokenUsage]:
    """Buka akumulator baru untuk satu giliran percakapan.

    Harus dimasuki SEBELUM agent.run(), karena di situlah task anak workflow
    dibuat dan konteksnya disalin.

    Yields:
        Akumulator yang akan terisi selama giliran berjalan.
    """
    akumulator = TokenUsage()
    token = _usage_giliran.set(akumulator)
    try:
        yield akumulator
    finally:
        _usage_giliran.reset(token)


def catat_respons(raw: object) -> None:
    """Tambahkan pemakaian satu respons LLM ke akumulator giliran aktif.

    Tidak melakukan apa-apa kalau dipanggil di luar giliran, misalnya dari
    script atau smoke test. Kegagalan membaca usage tidak boleh menggagalkan
    jawaban, jadi fungsi ini tidak pernah melempar.

    Args:
        raw: Field ``raw`` dari ChatResponse LlamaIndex.
    """
    akumulator = _usage_giliran.get()
    if akumulator is None:
        return
    akumulator.tambah(baca_usage(raw))


def baca_usage(raw: object) -> TokenUsage:
    """Baca jumlah token dari payload mentah Anthropic.

    Bentuk yang sebenarnya dikirim llama-index-llms-anthropic 0.12.0 adalah
    dict hasil ``dict(Message)`` dengan kunci "usage" berisi objek
    ``anthropic.types.Usage`` -- bukan dict bersarang, karena dict() pada model
    pydantic tidak rekursif. Bentuk lain tetap ditoleransi supaya perubahan
    versi paket tidak langsung mematikan pencatatan.

    Args:
        raw: Payload mentah, bentuk apa pun.

    Returns:
        Pemakaian token; seluruhnya nol kalau bentuknya tidak dikenali.
    """
    global _sudah_memperingatkan

    usage = _ambil_bagian_usage(raw)
    if usage is None:
        if not _sudah_memperingatkan:
            _sudah_memperingatkan = True
            logger.warning(
                f"Bentuk respons LLM tidak dikenali ({type(raw).__name__}); "
                "pemakaian token tidak tercatat. Periksa versi "
                "llama-index-llms-anthropic."
            )
        return TokenUsage()

    return TokenUsage(
        input_tokens=_bilangan(usage, "input_tokens"),
        output_tokens=_bilangan(usage, "output_tokens"),
        cache_read_tokens=_bilangan(usage, "cache_read_input_tokens"),
        cache_write_tokens=_bilangan(usage, "cache_creation_input_tokens"),
        llm_calls=1,
    )


def hitung_biaya_usd(usage: TokenUsage) -> float:
    """Hitung biaya satu giliran dalam dolar.

    Dibulatkan enam desimal, bukan dua: satu giliran Haiku 4.5 jatuh di kisaran
    $0,0003-$0,002, sehingga dua desimal akan menampilkan semuanya sebagai
    $0.00.

    Args:
        usage: Pemakaian token satu giliran.

    Returns:
        Biaya dalam USD.
    """
    juta = 1_000_000
    total = (
        usage.input_tokens / juta * settings.price_input_per_mtok
        + usage.output_tokens / juta * settings.price_output_per_mtok
        + usage.cache_read_tokens / juta * settings.price_cache_read_per_mtok
        + usage.cache_write_tokens / juta * settings.price_cache_write_per_mtok
    )
    return round(total, 6)


def _ambil_bagian_usage(raw: object) -> object | None:
    """Cari bagian usage di dalam payload mentah.

    Args:
        raw: Payload mentah.

    Returns:
        Objek atau dict berisi jumlah token, atau None kalau tidak ketemu.
    """
    if isinstance(raw, dict):
        if "usage" in raw:
            return raw["usage"]
        # Sebagian versi meratakan usage ke tingkat atas.
        if "input_tokens" in raw or "output_tokens" in raw:
            return raw
        return None

    usage = getattr(raw, "usage", None)
    return usage if usage is not None else None


def _bilangan(usage: object, nama: str) -> int:
    """Ambil satu field token dari objek atau dict usage.

    Args:
        usage: Objek Usage Anthropic atau dict setara.
        nama: Nama field yang dicari.

    Returns:
        Nilainya sebagai integer; 0 kalau tidak ada atau bukan angka.
    """
    nilai: Any
    if isinstance(usage, dict):
        nilai = usage.get(nama)
    else:
        nilai = getattr(usage, nama, None)

    return nilai if isinstance(nilai, int) and not isinstance(nilai, bool) else 0
