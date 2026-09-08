"""Uji integrasi agent tanpa memanggil Claude API.

Ini pengganti verifikasi yang biasanya butuh panggilan berbayar. Yang dibuktikan
di sini justru lebih tegas daripada satu percakapan sungguhan, karena hasilnya
deterministik: jalur mana yang dipakai agent, berapa panggilan yang tercatat,
dan apakah kutipan sampai ke jawaban akhir.
"""

from typing import Any

from app.models.chat import Citation, ChatMessage
from app.services.chatbot import ChatbotService

from tests.support.fake_llm import buat_llm_palsu, pesan_teks, pesan_tool


class NodePalsu:
    """Node hasil retrieval dengan bentuk yang sama seperti NodeWithScore."""

    def __init__(self, file_name: str, page: str, score: float, isi: str) -> None:
        self.metadata = {"file_name": file_name, "page_label": page}
        self.score = score
        self._isi = isi

    def get_content(self) -> str:
        """Isi chunk."""
        return self._isi


class RetrieverPalsu:
    """FAQRetriever palsu yang mengembalikan node siap pakai."""

    def __init__(self) -> None:
        self.kueri: list[str] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[NodePalsu]:
        """Kembalikan dua node tetap dan catat kuerinya."""
        self.kueri.append(query)
        return [
            NodePalsu(
                "04_kebijakan_retur_dan_garansi.pdf",
                "2",
                0.81,
                "Ketentuan Biaya Ongkos Kirim Retur. Produk cacat pabrik "
                "ditanggung GAYA.ID.",
            ),
            NodePalsu(
                "04_kebijakan_retur_dan_garansi.pdf",
                "1",
                0.77,
                "Jenis Garansi Produk GAYA.ID. Garansi Ukuran berlaku 7 hari.",
            ),
        ]

    def format_for_llm(self, nodes: list[NodePalsu]) -> str:
        """Susun kutipan jadi teks untuk model."""
        return "\n\n".join(n.get_content() for n in nodes)


class MemoriPalsu:
    """ConversationMemory palsu yang mencatat apa yang dipanggil."""

    def __init__(self) -> None:
        self.giliran: list[dict[str, Any]] = []
        self.tak_terjawab: list[str] = []
        self.eskalasi: list[str] = []

    def start_session(self, session_id: str, channel: str) -> str:
        """Kembalikan id percakapan tetap."""
        return f"conv-{session_id}"

    def load_history(self, conversation_id: str) -> list[ChatMessage]:
        """Percakapan baru, tanpa riwayat."""
        return []

    def record_turn(self, **kwargs: Any) -> None:
        """Simpan giliran."""
        self.giliran.append(kwargs)

    def log_unanswered(self, conversation_id: str, message: str) -> None:
        """Catat pertanyaan tak terjawab."""
        self.tak_terjawab.append(message)

    def escalate(self, conversation_id: str, reason: str, contact: Any = None) -> None:
        """Catat eskalasi."""
        self.eskalasi.append(reason)


def build_service(balasan: list[Any]) -> tuple[ChatbotService, Any, MemoriPalsu]:
    """Rakit ChatbotService lengkap dengan LLM dan retriever palsu.

    Args:
        balasan: Balasan berurutan yang akan dilayani LLM palsu.

    Returns:
        Tuple berisi service, llm palsu, dan memori palsu.
    """
    llm = buat_llm_palsu(balasan)
    memori = MemoriPalsu()
    service = ChatbotService(
        llm=llm,
        faq_retriever=RetrieverPalsu(),  # type: ignore[arg-type]
        catalog_service=None,  # type: ignore[arg-type]
        inventory_service=None,  # type: ignore[arg-type]
        order_service=None,  # type: ignore[arg-type]
        memory=memori,  # type: ignore[arg-type]
    )
    return service, llm, memori


class TestJalurNonStreaming:
    """Agent harus memakai achat, bukan astream_chat."""

    async def test_agent_memakai_jalur_yang_tercatat_biayanya(self) -> None:
        """Bukti pengganti verifikasi berbayar.

        Kalau streaming=False hilang dari _build_agent, agent beralih ke
        astream_chat yang tidak melewati pencatat pemakaian, dan seluruh biaya
        tercatat nol tanpa satu pun error. Uji ini gagal lebih dulu.
        """
        service, llm, _ = build_service(
            [
                pesan_tool("search_faq", {"query": "ongkir retur"}),
                pesan_teks("Ongkir retur ditanggung GAYA.ID, Kak."),
            ]
        )

        await service.answer(session_id="demo-1", message="ongkir retur siapa?")

        assert "achat" in llm.jalur
        assert "astream_chat" not in llm.jalur


class TestPencatatanBiaya:
    """Seluruh panggilan dalam satu giliran harus terhitung, bukan yang terakhir."""

    async def test_giliran_bertool_mencatat_lebih_dari_satu_panggilan(self) -> None:
        service, _, _ = build_service(
            [
                pesan_tool("search_faq", {"query": "ongkir retur"}),
                pesan_teks("Ongkir retur ditanggung GAYA.ID, Kak."),
            ]
        )

        reply = await service.answer(session_id="demo-1", message="ongkir retur siapa?")

        # Satu panggilan untuk memilih tool, satu lagi untuk menulis jawaban.
        # llm_calls == 1 adalah gejala persis dari hanya menangkap yang terakhir.
        assert reply.usage.llm_calls == 2
        assert reply.usage.input_tokens == 5500
        assert reply.usage.output_tokens == 100
        assert reply.cost_usd > 0

    async def test_biaya_cocok_dengan_tarif_yang_dikonfigurasi(self) -> None:
        service, _, _ = build_service([pesan_teks("Halo, Kak!", 1000, 200)])

        reply = await service.answer(session_id="demo-1", message="halo")

        # 1000/1e6 * 1.00 + 200/1e6 * 5.00
        assert reply.cost_usd == 0.002

    async def test_giliran_tanpa_tool_tetap_berbiaya(self) -> None:
        service, _, _ = build_service([pesan_teks("Halo, Kak!")])

        reply = await service.answer(session_id="demo-1", message="halo")

        assert reply.usage.llm_calls == 1
        assert reply.tool_calls == []
        assert reply.mode == "tanpa_sumber"


class TestKutipan:
    """Kutipan harus lolos dari batas tool sampai ke jawaban akhir."""

    async def test_jawaban_dokumen_membawa_kutipan(self) -> None:
        service, _, _ = build_service(
            [
                pesan_tool("search_faq", {"query": "ongkir retur"}),
                pesan_teks("Ongkir retur ditanggung GAYA.ID, Kak."),
            ]
        )

        reply = await service.answer(session_id="demo-1", message="ongkir retur siapa?")

        assert reply.mode == "dokumen"
        assert len(reply.citations) == 2
        pertama = reply.citations[0]
        assert isinstance(pertama, Citation)
        assert pertama.file_name == "04_kebijakan_retur_dan_garansi.pdf"
        assert pertama.page == "2"
        assert pertama.match_percent == 81
        assert "Ongkos Kirim Retur" in pertama.snippet

    async def test_kutipan_terurut_dari_paling_mirip(self) -> None:
        service, _, _ = build_service(
            [
                pesan_tool("search_faq", {"query": "garansi"}),
                pesan_teks("Garansi ukuran 7 hari, Kak."),
            ]
        )

        reply = await service.answer(session_id="demo-1", message="garansi berapa lama?")

        persen = [c.match_percent for c in reply.citations]
        assert persen == sorted(persen, reverse=True)

    async def test_jawaban_tanpa_tool_tidak_punya_kutipan(self) -> None:
        service, _, _ = build_service([pesan_teks("Halo, Kak!")])

        reply = await service.answer(session_id="demo-1", message="halo")

        assert reply.citations == []
