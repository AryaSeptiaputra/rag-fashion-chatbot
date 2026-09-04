"""Test jalur ekspor trace di scripts/run_eval.py.

Script dimuat lewat importlib karena scripts/ bukan package -- itu disengaja,
berkas di sana adalah entry point, bukan pustaka. Yang diuji di sini satu hal
yang tidak tertangkap unit test EvalTrace: bahwa run_case benar-benar merangkai
jawaban agent jadi trace, bukan membuangnya.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from app.config import PROJECT_ROOT
from app.evals.trace import load_traces, write_traces
from app.models.chat import AgentReply, ToolCallRecord

LONG_OUTPUT = "Daftar produk yang sangat panjang. " * 40


@pytest.fixture(scope="module")
def run_eval() -> ModuleType:
    """Muat scripts/run_eval.py sebagai modul."""
    path = PROJECT_ROOT / "scripts" / "run_eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubChatbotService:
    """ChatbotService palsu yang mengembalikan jawaban tetap."""

    def __init__(self, reply: AgentReply) -> None:
        self.reply = reply
        self.questions: list[str] = []

    async def answer(
        self, session_id: str, message: str, channel: str = "web"
    ) -> AgentReply:
        """Catat pertanyaan lalu balas dengan jawaban yang sudah disiapkan."""
        self.questions.append(message)
        return self.reply


def make_reply() -> AgentReply:
    """Jawaban agent dengan keluaran tool yang lebih panjang dari batas audit."""
    return AgentReply(
        answer="Ongkir luar Jawa 4-7 hari kerja kak.",
        tool_calls=[
            ToolCallRecord(
                tool_name="search_faq",
                arguments={"query": "ongkir"},
                result_summary=LONG_OUTPUT[:500],
            )
        ],
        tool_outputs=[LONG_OUTPUT],
        retrieved_contexts=["Estimasi luar Pulau Jawa 4-7 hari kerja."],
    )


async def test_run_case_returns_result_and_trace_together(
    run_eval: ModuleType,
) -> None:
    service = StubChatbotService(make_reply())
    case = {
        "id": "ret-01",
        "question": "Berapa lama kirim ke luar Jawa?",
        "expect_tools": ["search_faq"],
        "reference": "Luar Pulau Jawa 4-7 hari kerja.",
        "reference_sections": ["Pengiriman"],
    }

    result, trace = await run_eval.run_case(service, case)

    assert result.tool_ok is True
    assert trace.id == "ret-01"
    assert trace.called_tools == ["search_faq"]
    assert trace.reference_sections == ["Pengiriman"]


async def test_trace_carries_untruncated_tool_output(run_eval: ModuleType) -> None:
    # result_summary dipotong 500 karakter untuk audit. Kalau trace ikut memakai
    # nilai itu, juri melihat bukti lebih sedikit daripada composer dan akan
    # memvonis jawaban yang sah sebagai halusinasi.
    service = StubChatbotService(make_reply())

    _, trace = await run_eval.run_case(service, {"id": "faq-01", "question": "q"})

    assert trace.contexts == [LONG_OUTPUT]
    assert len(trace.contexts[0]) > 500


async def test_history_is_replayed_before_the_graded_question(
    run_eval: ModuleType,
) -> None:
    service = StubChatbotService(make_reply())
    case = {
        "id": "mixed-02",
        "question": "kalau yang itu gimana?",
        "history": ["KAO-0001 ready ga?"],
    }

    await run_eval.run_case(service, case)

    assert service.questions == ["KAO-0001 ready ga?", "kalau yang itu gimana?"]


async def test_exported_trace_survives_a_roundtrip(
    run_eval: ModuleType, tmp_path: Path
) -> None:
    service = StubChatbotService(make_reply())
    _, trace = await run_eval.run_case(service, {"id": "faq-01", "question": "q"})
    path = tmp_path / "trace.jsonl"

    write_traces(path, [trace])

    assert load_traces(path) == [trace]
