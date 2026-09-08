"""Chatbot mode contoh: melayani jawaban siap pakai tanpa memanggil Claude.

Antarmukanya sama persis dengan ChatbotService, sehingga route, pengaman, dan
skema respons tidak perlu tahu mana yang sedang dipakai. Satu-satunya yang
membedakan di permukaan adalah penanda ``stub`` pada balasan, dan penanda itu
wajib: angka biaya yang terlihat sungguhan padahal karangan adalah persis
kebohongan yang seluruh meter biaya ini dibuat untuk mencegahnya.

Kelas ini juga menjadi fondasi mode rekaman nanti, saat plafon anggaran habis
dan demo harus tetap menjawab alih-alih menampilkan halaman error.
"""

import asyncio
import random
import re

from app.models.chat import (
    AgentReply,
    Bahasa,
    Citation,
    TokenUsage,
    ToolCallRecord,
)
from app.services.stub_replies import (
    DAFTAR,
    DI_LUAR_CAKUPAN,
    FALLBACK,
    KUNCI_DI_LUAR_CAKUPAN,
    JawabanContoh,
)
from app.utils.logger import setup_logger
from app.utils.usage import hitung_biaya_usd

logger = setup_logger(__name__)

# Ditiru supaya indikator mengetik dan keadaan pemuatan di UI benar-benar
# teruji; tanpa jeda, semua keadaan transisi tidak pernah terlihat.
_JEDA_MINIMAL = 0.6
_JEDA_MAKSIMAL = 1.4


class StubChatbotService:
    """Pengganti ChatbotService yang tidak pernah menyentuh Anthropic."""

    def __init__(self, jeda: bool = True) -> None:
        self.jeda = jeda

    async def answer(
        self,
        session_id: str,
        message: str,
        channel: str = "web",
        language: Bahasa = "id",
    ) -> AgentReply:
        """Layani satu pertanyaan dari daftar jawaban contoh.

        Args:
            session_id: Identifier sesi; hanya dicatat di log.
            message: Pesan dari pembeli.
            channel: Kanal asal percakapan.
            language: Bahasa jawaban yang diminta.

        Returns:
            Jawaban contoh lengkap dengan jejak tool, kutipan, dan biayanya.
        """
        if self.jeda:
            await asyncio.sleep(random.uniform(_JEDA_MINIMAL, _JEDA_MAKSIMAL))

        normal = _normalkan(message)
        logger.info(f"Mode contoh melayani sesi {session_id}: {message!r}")

        if any(kunci in normal for kunci in KUNCI_DI_LUAR_CAKUPAN):
            return _balasan_sederhana(DI_LUAR_CAKUPAN[language])

        cocok = _cari_kecocokan(normal)
        if cocok is None:
            return _balasan_sederhana(FALLBACK[language])

        return _balasan_lengkap(cocok, language)


def _normalkan(pesan: str) -> str:
    """Rapikan pesan supaya pencocokan kata kunci tidak terganggu tanda baca.

    Args:
        pesan: Pesan mentah dari pembeli.

    Returns:
        Pesan huruf kecil tanpa tanda baca berlebih.
    """
    return re.sub(r"[^a-z0-9\s-]", " ", pesan.lower())


def _cari_kecocokan(normal: str) -> JawabanContoh | None:
    """Cari jawaban contoh yang kata kuncinya muncul di pertanyaan.

    Args:
        normal: Pesan yang sudah dinormalkan.

    Returns:
        Jawaban contoh dengan kecocokan terbanyak, atau None.
    """
    terbaik: JawabanContoh | None = None
    skor_terbaik = 0

    for contoh in DAFTAR:
        skor = sum(1 for kunci in contoh["kunci"] if kunci in normal)
        if skor > skor_terbaik:
            terbaik, skor_terbaik = contoh, skor

    return terbaik


def _balasan_sederhana(teks: str) -> AgentReply:
    """Bangun balasan tanpa tool dan tanpa biaya.

    Args:
        teks: Isi jawaban.

    Returns:
        AgentReply bertanda stub.
    """
    return AgentReply(answer=teks, mode="tanpa_sumber", stub=True)


def _balasan_lengkap(contoh: JawabanContoh, language: Bahasa) -> AgentReply:
    """Susun balasan contoh beserta seluruh jejaknya.

    Args:
        contoh: Entri jawaban contoh yang cocok.
        language: Bahasa jawaban.

    Returns:
        AgentReply bertanda stub, lengkap dengan kutipan dan biaya taksiran.
    """
    usage = TokenUsage(
        input_tokens=contoh["input_tokens"],
        output_tokens=contoh["output_tokens"],
        llm_calls=contoh["llm_calls"],
    )
    return AgentReply(
        answer=contoh["jawaban"][language],
        tool_calls=[
            ToolCallRecord(
                tool_name=panggilan["tool_name"],
                arguments=panggilan["arguments"],
                latency_ms=panggilan["latency_ms"],
            )
            for panggilan in contoh["tool_calls"]
        ],
        citations=[
            Citation(
                file_name=kutipan["file_name"],
                page=kutipan["page"],
                score=kutipan["score"],
                match_percent=round(kutipan["score"] * 100),
                snippet=kutipan["snippet"],
            )
            for kutipan in contoh["citations"]
        ],
        usage=usage,
        cost_usd=hitung_biaya_usd(usage),
        mode=contoh["mode"],  # type: ignore[arg-type]
        stub=True,
    )
