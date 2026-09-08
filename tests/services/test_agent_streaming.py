"""Penjaga satu baris untuk setelan yang paling mudah hilang tanpa disadari.

FunctionAgent mewarisi streaming=True dari BaseWorkflowAgent. Pada jalur
streaming, agent memakai astream_chat yang TIDAK melewati override pencatat
pemakaian di CompatAnthropic. Akibatnya biaya tiap giliran tercatat nol
sementara saldo Anthropic tetap terpakai -- gagal tanpa satu pun error, jenis
kegagalan yang paling lama tidak ketahuan.

Upgrade llama-index atau refaktor yang menghapus argumen itu akan gagal di sini
lebih dulu, sebelum meter biaya diam-diam berbohong.
"""

from app.services.chatbot import ChatbotService
from app.tools.registry import ToolCallRecorder

from tests.support.fake_llm import buat_llm_palsu, pesan_teks


def test_agent_dibangun_non_streaming() -> None:
    # LLM tidak boleh None: FunctionAgent akan mencoba meresolusi LLM default
    # dan gagal karena integrasi OpenAI tidak dipasang di project ini.
    service = ChatbotService(
        llm=buat_llm_palsu([pesan_teks("halo")]),
        faq_retriever=None,  # type: ignore[arg-type]
        catalog_service=None,  # type: ignore[arg-type]
        inventory_service=None,  # type: ignore[arg-type]
        order_service=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
    )

    agent = service._build_agent("conv-uji", ToolCallRecorder())

    assert agent.streaming is False, (
        "streaming harus False; kalau True, seluruh pemakaian token "
        "tidak tercatat dan meter biaya menampilkan nol"
    )
