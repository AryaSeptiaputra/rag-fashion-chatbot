"""Test jaring pengaman eskalasi yang dijanjikan tapi tidak tercatat.

Regresi yang dijaga: eval mengukur model sesekali menulis "saya teruskan ke
admin" tanpa memanggil escalate_to_human, sehingga permintaan pembeli hilang
tanpa jejak dan pembeli menunggu balasan yang tidak akan pernah datang.
"""

import pytest

from app.models.chat import ToolCallRecord
from app.services.chatbot import _ESCALATION_CLAIM_PATTERNS, ChatbotService


class SpyMemory:
    """ConversationMemory palsu yang mencatat pemanggilan escalate()."""

    def __init__(self) -> None:
        self.escalations: list[tuple[str, str]] = []

    def escalate(
        self, conversation_id: str, reason: str, contact: str | None = None
    ) -> str:
        """Rekam permintaan eskalasi."""
        self.escalations.append((conversation_id, reason))
        return "esc-1"


def build_service(memory: SpyMemory) -> ChatbotService:
    """Rakit ChatbotService dengan hanya memory yang berfungsi."""
    return ChatbotService(
        llm=None,  # type: ignore[arg-type]
        faq_retriever=None,  # type: ignore[arg-type]
        catalog_service=None,  # type: ignore[arg-type]
        inventory_service=None,  # type: ignore[arg-type]
        order_service=None,  # type: ignore[arg-type]
        memory=memory,  # type: ignore[arg-type]
    )


CLAIMS = [
    "Baik kak, saya teruskan ke admin untuk kamu.",
    "Permintaan sudah saya teruskan ke admin ya kak.",
    "Aku sampaikan ke admin sekarang ya kak.",
    "Saya akan hubungkan kakak dengan admin kami.",
]

NOT_CLAIMS = [
    "Kalau mau, saya bisa teruskan ke admin.",
    "Mau saya teruskan ke admin?",
    "Boleh saya sampaikan ke admin kak?",
    "Stok size L masih ada 12 pcs kak.",
    "Kak, pesanan sudah diterima pada 6 Juli 2026.",
]


@pytest.mark.parametrize("answer", CLAIMS)
def test_pattern_detects_promise(answer: str) -> None:
    assert _ESCALATION_CLAIM_PATTERNS["id"].search(answer)


@pytest.mark.parametrize("answer", NOT_CLAIMS)
def test_pattern_ignores_offers_and_unrelated_text(answer: str) -> None:
    # Menawarkan bukan menjanjikan; kalau ini ikut cocok, tabel escalations
    # akan penuh eskalasi palsu.
    assert not _ESCALATION_CLAIM_PATTERNS["id"].search(answer)


def test_guard_records_escalation_when_model_only_promised() -> None:
    memory = SpyMemory()
    service = build_service(memory)

    service._guard_unrecorded_escalation(
        conversation_id="conv-1",
        user_message="Aku mau ngomong sama adminnya langsung dong",
        answer="Baik kak, saya teruskan ke admin untuk kamu.",
        tool_calls=[],
    )

    assert len(memory.escalations) == 1
    conversation_id, reason = memory.escalations[0]
    assert conversation_id == "conv-1"
    assert reason.startswith("[otomatis]")
    assert "ngomong sama adminnya" in reason


def test_guard_stays_quiet_when_tool_was_actually_called() -> None:
    memory = SpyMemory()
    service = build_service(memory)

    service._guard_unrecorded_escalation(
        conversation_id="conv-1",
        user_message="Aku mau ngomong sama admin",
        answer="Baik kak, saya teruskan ke admin untuk kamu.",
        tool_calls=[ToolCallRecord(tool_name="escalate_to_human")],
    )

    assert memory.escalations == []


def test_guard_stays_quiet_on_ordinary_answers() -> None:
    memory = SpyMemory()
    service = build_service(memory)

    service._guard_unrecorded_escalation(
        conversation_id="conv-1",
        user_message="KAO-0001 size L ready?",
        answer="Masih ada kak, tersedia 47 pcs dengan harga Rp119.000.",
        tool_calls=[ToolCallRecord(tool_name="check_stock")],
    )

    assert memory.escalations == []


def test_guard_does_not_hide_model_failure_from_eval() -> None:
    # tool_calls sengaja tidak ditambahi entri palsu: eval harus tetap
    # melaporkan bahwa model gagal memanggil tool.
    memory = SpyMemory()
    service = build_service(memory)
    tool_calls: list[ToolCallRecord] = []

    service._guard_unrecorded_escalation(
        conversation_id="conv-1",
        user_message="Aku mau ngomong sama admin",
        answer="Baik kak, saya teruskan ke admin.",
        tool_calls=tool_calls,
    )

    assert tool_calls == []
    assert len(memory.escalations) == 1


# ---- Bahasa Inggris ----
# Tanpa pola versi Inggris, menyalakan bahasa kedua sama dengan mematikan
# guardrail ini: klaim "I've forwarded this to our admin" tidak akan cocok
# dengan pola Indonesia, eskalasinya tidak tercatat, dan permintaan pembeli
# hilang tanpa jejak.

CLAIMS_EN = [
    "I have forwarded this to our admin.",
    "I've already passed your request to the admin team.",
    "I will connect you with an admin right away.",
    "I'm escalating this to an admin now.",
]

NOT_CLAIMS_EN = [
    "Can I forward this to an admin for you?",
    "Shall I connect you with an admin?",
    "Would you like me to escalate this to an admin?",
    "Size L still has 12 pieces in stock.",
]


@pytest.mark.parametrize("answer", CLAIMS_EN)
def test_english_pattern_detects_promise(answer: str) -> None:
    assert _ESCALATION_CLAIM_PATTERNS["en"].search(answer)


@pytest.mark.parametrize("answer", NOT_CLAIMS_EN)
def test_english_pattern_ignores_offers(answer: str) -> None:
    assert not _ESCALATION_CLAIM_PATTERNS["en"].search(answer)


def test_guard_records_english_promise() -> None:
    memory = SpyMemory()
    service = build_service(memory)

    service._guard_unrecorded_escalation(
        conversation_id="conv-1",
        user_message="please connect me to an admin",
        answer="I have forwarded this to our admin.",
        tool_calls=[],
        language="en",
    )

    assert len(memory.escalations) == 1
    assert memory.escalations[0][1].startswith("[otomatis]")


def test_indonesian_pattern_would_miss_english_promise() -> None:
    """Merekam kenapa pola kedua harus ada, bukan sekadar boleh ada."""
    assert not _ESCALATION_CLAIM_PATTERNS["id"].search(
        "I have forwarded this to our admin."
    )
