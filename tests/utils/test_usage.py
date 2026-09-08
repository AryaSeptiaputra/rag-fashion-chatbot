"""Uji pembacaan usage dan perhitungan biaya, seluruhnya tanpa memanggil API."""

from anthropic.types import Message, TextBlock, Usage

from app.models.chat import TokenUsage
from app.utils.usage import baca_usage, catat_respons, hitung_biaya_usd


def bentuk_asli(
    input_tokens: int = 3560,
    output_tokens: int = 190,
    cache_read: int = 0,
    cache_write: int = 0,
) -> dict[str, object]:
    """Bangun payload persis seperti yang dikirim wrapper Anthropic LlamaIndex.

    llama-index-llms-anthropic 0.12.0 mengisi ChatResponse.raw dengan
    ``dict(Message)``. Karena dict() pada model pydantic tidak rekursif, kunci
    "usage" berisi objek Usage, bukan dict bersarang. Fixture ini dibangun dari
    tipe SDK yang sesungguhnya supaya uji ini ikut gagal kalau bentuknya berubah
    di versi berikutnya.

    Args:
        input_tokens: Jumlah token masukan.
        output_tokens: Jumlah token keluaran.
        cache_read: Token yang dibaca dari cache prompt.
        cache_write: Token yang ditulis ke cache prompt.

    Returns:
        Payload mentah setara ChatResponse.raw.
    """
    message = Message(
        id="msg_test",
        content=[TextBlock(text="halo", type="text")],
        model="claude-haiku-4-5",
        role="assistant",
        stop_reason="end_turn",
        stop_sequence=None,
        type="message",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )
    return dict(message)


class TestBacaUsage:
    """baca_usage harus tahan terhadap perubahan bentuk payload."""

    def test_membaca_bentuk_asli_dari_wrapper(self) -> None:
        usage = baca_usage(bentuk_asli(cache_read=2600, cache_write=120))

        assert usage.input_tokens == 3560
        assert usage.output_tokens == 190
        assert usage.cache_read_tokens == 2600
        assert usage.cache_write_tokens == 120
        assert usage.llm_calls == 1

    def test_membaca_objek_message_langsung(self) -> None:
        """Kalau versi berikutnya berhenti membungkus Message jadi dict."""
        message = Message(
            id="msg_test",
            content=[TextBlock(text="halo", type="text")],
            model="claude-haiku-4-5",
            role="assistant",
            stop_reason="end_turn",
            stop_sequence=None,
            type="message",
            usage=Usage(input_tokens=100, output_tokens=20),
        )

        usage = baca_usage(message)

        assert (usage.input_tokens, usage.output_tokens) == (100, 20)
        assert usage.llm_calls == 1

    def test_membaca_usage_berbentuk_dict(self) -> None:
        usage = baca_usage({"usage": {"input_tokens": 12, "output_tokens": 3}})

        assert (usage.input_tokens, usage.output_tokens) == (12, 3)

    def test_membaca_usage_yang_diratakan(self) -> None:
        usage = baca_usage({"input_tokens": 7, "output_tokens": 2})

        assert (usage.input_tokens, usage.output_tokens) == (7, 2)

    def test_bentuk_tak_dikenal_menghasilkan_nol_tanpa_melempar(self) -> None:
        """Kegagalan membaca usage tidak boleh menggagalkan jawaban pembeli."""
        for sampah in (None, "teks", 42, {"tidak": "relevan"}, object()):
            usage = baca_usage(sampah)

            assert usage == TokenUsage()
            assert usage.llm_calls == 0

    def test_field_yang_hilang_dianggap_nol(self) -> None:
        usage = baca_usage({"usage": {"input_tokens": 5}})

        assert usage.input_tokens == 5
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0

    def test_boolean_tidak_dihitung_sebagai_angka(self) -> None:
        """bool subclass dari int di Python; True tidak boleh jadi 1 token."""
        usage = baca_usage({"usage": {"input_tokens": True, "output_tokens": 4}})

        assert usage.input_tokens == 0
        assert usage.output_tokens == 4


class TestHitungBiaya:
    """Aritmetika biaya memakai tarif dari settings."""

    def test_masukan_dan_keluaran(self) -> None:
        # 1000/1e6 * 1.00 + 500/1e6 * 5.00 = 0.001 + 0.0025
        biaya = hitung_biaya_usd(TokenUsage(input_tokens=1000, output_tokens=500))

        assert biaya == 0.0035

    def test_token_cache_ikut_dihitung(self) -> None:
        # baca 10_000 * 0.10/1e6 = 0.001 ; tulis 10_000 * 1.25/1e6 = 0.0125
        biaya = hitung_biaya_usd(
            TokenUsage(cache_read_tokens=10_000, cache_write_tokens=10_000)
        )

        assert biaya == 0.0135

    def test_giliran_kosong_tidak_berbiaya(self) -> None:
        assert hitung_biaya_usd(TokenUsage()) == 0.0

    def test_dibulatkan_enam_desimal_bukan_dua(self) -> None:
        """Dua desimal akan menampilkan tiap giliran Haiku sebagai $0.00."""
        biaya = hitung_biaya_usd(TokenUsage(input_tokens=300, output_tokens=40))

        assert biaya == 0.0005
        assert round(biaya, 2) == 0.0, "justru inilah alasan enam desimal dipakai"


class TestTambah:
    """TokenUsage.tambah memutasi objek, bukan mengembalikan yang baru."""

    def test_menjumlahkan_seluruh_field(self) -> None:
        akumulator = TokenUsage()

        akumulator.tambah(TokenUsage(input_tokens=10, output_tokens=2, llm_calls=1))
        akumulator.tambah(TokenUsage(input_tokens=5, cache_read_tokens=3, llm_calls=1))

        assert akumulator.input_tokens == 15
        assert akumulator.output_tokens == 2
        assert akumulator.cache_read_tokens == 3
        assert akumulator.llm_calls == 2


def test_catat_respons_di_luar_giliran_tidak_melempar() -> None:
    """Script dan smoke test memanggil LLM tanpa membuka akumulator."""
    catat_respons(bentuk_asli())
