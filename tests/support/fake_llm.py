"""LLM palsu untuk menguji agent tanpa memanggil Claude API.

Yang dipalsukan hanya lapisan HTTP: atribut client SDK diganti, sementara
seluruh jalur asli tetap berjalan -- wrapper LlamaIndex membangun permintaan,
mengurai balasan jadi blok, mengisi ChatResponse.raw dengan dict(Message), lalu
override di CompatAnthropic mencatat pemakaiannya. Dengan begitu uji ini benar
benar menguji kode kita, bukan tiruannya.
"""

from typing import Any

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from app.utils.anthropic_compat import CompatAnthropic


def pesan_teks(
    teks: str, input_tokens: int = 2500, output_tokens: int = 40
) -> Message:
    """Bangun balasan berisi jawaban akhir.

    Args:
        teks: Isi jawaban.
        input_tokens: Token masukan yang dilaporkan.
        output_tokens: Token keluaran yang dilaporkan.

    Returns:
        Message SDK Anthropic yang sah.
    """
    return _pesan(
        [TextBlock(text=teks, type="text")],
        "end_turn",
        input_tokens,
        output_tokens,
    )


def pesan_tool(
    nama: str,
    argumen: dict[str, Any],
    input_tokens: int = 3000,
    output_tokens: int = 60,
) -> Message:
    """Bangun balasan yang meminta pemanggilan satu tool.

    Args:
        nama: Nama tool yang diminta.
        argumen: Argumen tool.
        input_tokens: Token masukan yang dilaporkan.
        output_tokens: Token keluaran yang dilaporkan.

    Returns:
        Message SDK Anthropic berisi blok tool_use.
    """
    blok = ToolUseBlock(id="toolu_uji", input=argumen, name=nama, type="tool_use")
    return _pesan([blok], "tool_use", input_tokens, output_tokens)


def _pesan(
    content: list[Any], stop_reason: str, input_tokens: int, output_tokens: int
) -> Message:
    return Message(
        id="msg_uji",
        content=content,
        model="claude-haiku-4-5",
        role="assistant",
        stop_reason=stop_reason,  # type: ignore[arg-type]
        stop_sequence=None,
        type="message",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


class _MessagesPalsu:
    """Pengganti client.messages yang mengembalikan balasan yang sudah disiapkan."""

    def __init__(self, balasan: list[Message]) -> None:
        self.antrean = list(balasan)
        self.permintaan: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        """Layani satu permintaan dari antrean.

        Args:
            **kwargs: Parameter permintaan; direkam untuk diperiksa uji.

        Returns:
            Balasan berikutnya; balasan terakhir diulang kalau antrean habis.
        """
        self.permintaan.append(kwargs)
        if len(self.antrean) > 1:
            return self.antrean.pop(0)
        return self.antrean[0]


class _ClientPalsu:
    """Pengganti AsyncAnthropic yang tidak menyentuh jaringan."""

    def __init__(self, balasan: list[Message]) -> None:
        self.messages = _MessagesPalsu(balasan)


class LlmPalsu(CompatAnthropic):
    """CompatAnthropic dengan client SDK diganti dan jalur yang dipakai dicatat.

    Mencatat metode mana yang dipanggil agent adalah inti uji ini: jalur
    streaming (astream_chat) tidak melewati pencatat pemakaian sama sekali,
    sehingga biayanya akan tercatat nol tanpa satu pun error.
    """

    def pasang(self, balasan: list[Message]) -> None:
        """Siapkan antrean balasan dan pasang client palsu.

        Args:
            balasan: Balasan berurutan yang akan dilayani.
        """
        object.__setattr__(self, "_jalur", [])
        self._aclient = _ClientPalsu(balasan)
        self._client = _ClientPalsu(balasan)

    @property
    def jalur(self) -> list[str]:
        """Nama metode yang dipanggil agent, berurutan."""
        return getattr(self, "_jalur", [])

    @property
    def permintaan(self) -> list[dict[str, Any]]:
        """Parameter tiap permintaan yang sampai ke client palsu."""
        return self._aclient.messages.permintaan  # type: ignore[union-attr]

    async def achat(self, messages: Any, **kwargs: Any) -> Any:
        """Catat bahwa jalur non-streaming dipakai, lalu teruskan ke induk."""
        self.jalur.append("achat")
        return await super().achat(messages, **kwargs)

    async def astream_chat(self, messages: Any, **kwargs: Any) -> Any:
        """Catat bahwa jalur streaming dipakai, lalu teruskan ke induk."""
        self.jalur.append("astream_chat")
        return await super().astream_chat(messages, **kwargs)


def buat_llm_palsu(balasan: list[Message]) -> LlmPalsu:
    """Bangun LLM palsu siap pakai.

    Args:
        balasan: Balasan berurutan yang akan dilayani.

    Returns:
        LLM yang bisa diberikan ke ChatbotService seperti LLM sungguhan.
    """
    llm = LlmPalsu(model="claude-haiku-4-5", api_key="kunci-palsu", max_tokens=256)
    llm.pasang(balasan)
    return llm
