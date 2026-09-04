"""Test penyusun jawaban akhir: isi blok bukti dan perilaku saat gagal."""

import httpx
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole

from app.config import settings
from app.models.chat import ToolObservation
from app.services.composer import (
    _MAX_CHARS_PER_OBSERVATION,
    _TRUNCATION_MARKER,
    AnswerComposer,
)


class StubLLM:
    """LLM palsu yang merekam prompt dan mengembalikan jawaban tetap."""

    def __init__(self, reply: str = "Halo Kak, stoknya masih ada.") -> None:
        self.reply = reply
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []

    async def achat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Rekam prompt lalu balas, atau lempar error yang sudah disiapkan."""
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=self.reply)
        )

    @property
    def last_user_prompt(self) -> str:
        """Isi pesan user pada panggilan terakhir."""
        return str(self.calls[-1][-1].content)


def make_observation(
    tool_name: str = "check_stock",
    result: str = "KAO-0001 ukuran L: sisa 5 pcs.",
    **arguments: object,
) -> ToolObservation:
    """Buat satu observasi tool untuk pengujian."""
    return ToolObservation(
        tool_name=tool_name, arguments=arguments or {"sku": "KAO-0001"}, result=result
    )


async def test_system_prompt_comes_first() -> None:
    llm = StubLLM()
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    await composer.compose("stok L ada?", [make_observation()])

    messages = llm.calls[-1]
    assert messages[0].role == MessageRole.SYSTEM
    assert "BUKTI" in str(messages[0].content)
    assert messages[-1].role == MessageRole.USER


async def test_evidence_carries_full_tool_result_and_arguments() -> None:
    llm = StubLLM()
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    await composer.compose(
        "stok L ada?",
        [make_observation(result="KAO-0001 ukuran L: sisa 5 pcs.", sku="KAO-0001")],
    )

    prompt = llm.last_user_prompt
    assert "KAO-0001 ukuran L: sisa 5 pcs." in prompt
    assert "check_stock(sku='KAO-0001')" in prompt


async def test_empty_observations_still_produce_a_valid_prompt() -> None:
    # Sapaan dan pertanyaan yang belum lengkap tidak memanggil tool apa pun.
    # Composer tetap harus dipanggil, tapi dengan penanda bahwa dia tidak punya
    # fakta apa pun untuk disampaikan.
    llm = StubLLM(reply="Halo Kak, ada yang bisa dibantu?")
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    answer = await composer.compose("halo", [])

    assert answer == "Halo Kak, ada yang bisa dibantu?"
    assert "tidak ada hasil tool" in llm.last_user_prompt


async def test_long_observation_is_truncated_with_marker() -> None:
    llm = StubLLM()
    composer = AnswerComposer(llm)  # type: ignore[arg-type]
    long_result = "Produk A, Produk B, " * 200

    await composer.compose("ada baju apa aja?", [make_observation(result=long_result)])

    prompt = llm.last_user_prompt
    assert _TRUNCATION_MARKER.strip() in prompt
    assert len(prompt) < len(long_result)


async def test_evidence_stays_within_total_budget() -> None:
    llm = StubLLM()
    composer = AnswerComposer(llm)  # type: ignore[arg-type]
    observations = [
        make_observation(result="x" * _MAX_CHARS_PER_OBSERVATION) for _ in range(10)
    ]

    await composer.compose("banyak tool", observations)

    # num_ctx yang jebol membuat Ollama memotong prompt dari kiri, yang justru
    # membuang system prompt beserta aturan groundedness-nya.
    assert len(llm.last_user_prompt) < 10 * _MAX_CHARS_PER_OBSERVATION


async def test_recent_history_is_included_but_bounded() -> None:
    llm = StubLLM()
    composer = AnswerComposer(llm)  # type: ignore[arg-type]
    history = [
        ChatMessage(role=MessageRole.USER, content=f"pesan lama {index}")
        for index in range(20)
    ]

    await composer.compose("yang tadi ready ga?", [make_observation()], history)

    prompt = llm.last_user_prompt
    assert "pesan lama 19" in prompt
    assert "pesan lama 0" not in prompt
    assert prompt.count("Pembeli:") <= settings.composer_history_turns * 2


async def test_thinking_block_never_reaches_the_answer() -> None:
    llm = StubLLM(reply="<think>hitung dulu</think>Halo Kak, sisa 5 pcs.")
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    answer = await composer.compose("stok?", [make_observation()])

    assert answer == "Halo Kak, sisa 5 pcs."


async def test_unreachable_llm_returns_empty_instead_of_raising() -> None:
    # Kegagalan pass kedua tidak boleh mematikan endpoint; pemanggil jatuh
    # balik ke jawaban tahap agent.
    llm = StubLLM()
    llm.error = httpx.ConnectError("connection refused")
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    assert await composer.compose("stok?", [make_observation()]) == ""


async def test_empty_model_output_returns_empty() -> None:
    llm = StubLLM(reply="   ")
    composer = AnswerComposer(llm)  # type: ignore[arg-type]

    assert await composer.compose("stok?", [make_observation()]) == ""
