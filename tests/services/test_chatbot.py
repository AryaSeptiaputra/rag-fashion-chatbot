"""Test ChatbotService: persistensi giliran dan deteksi pertanyaan tak terjawab."""

from app.models.chat import ToolCallRecord
from app.services.chatbot import ChatbotService


def build_service() -> ChatbotService:
    """Rakit ChatbotService kosong; hanya method statis yang diuji di sini."""
    return ChatbotService(
        llm=None,  # type: ignore[arg-type]
        faq_retriever=None,  # type: ignore[arg-type]
        catalog_service=None,  # type: ignore[arg-type]
        inventory_service=None,  # type: ignore[arg-type]
        order_service=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
    )


def make_call(tool_name: str, summary: str, is_error: bool = False) -> ToolCallRecord:
    """Buat satu jejak tool call untuk pengujian."""
    return ToolCallRecord(
        tool_name=tool_name, result_summary=summary, is_error=is_error
    )


def test_turn_with_data_is_not_flagged_unanswered() -> None:
    calls = [make_call("check_stock", "TERSEDIA 12 pcs")]

    assert ChatbotService._is_unanswered(calls) is False


def test_turn_where_every_tool_found_nothing_is_flagged() -> None:
    calls = [
        make_call("search_products", "Tidak ditemukan produk yang cocok"),
        make_call("check_stock", "Varian untuk SKU 'ZZZ' tidak ada di database"),
    ]

    assert ChatbotService._is_unanswered(calls) is True


def test_partial_success_is_not_flagged() -> None:
    calls = [
        make_call("search_products", "Tidak ditemukan produk yang cocok"),
        make_call("search_faq", "kutipan kebijakan retur"),
    ]

    assert ChatbotService._is_unanswered(calls) is False


def test_escalation_only_turn_is_flagged() -> None:
    calls = [make_call("escalate_to_human", "diteruskan ke admin")]

    assert ChatbotService._is_unanswered(calls) is True


def test_turn_without_any_tool_is_not_flagged() -> None:
    # Sapaan atau basa-basi tidak butuh tool dan bukan kegagalan.
    assert ChatbotService._is_unanswered([]) is False


def test_failed_tool_counts_as_unanswered() -> None:
    calls = [make_call("check_stock", "Tool check_stock gagal", is_error=True)]

    assert ChatbotService._is_unanswered(calls) is True
