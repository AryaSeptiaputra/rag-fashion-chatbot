"""Test ChatRepository: pembuatan sesi, riwayat, dan audit tool call."""

from app.models.chat import ToolCallRecord
from app.repositories.chat import ChatRepository
from tests.conftest import FakeSupabaseClient


def test_get_or_create_conversation_reuses_existing_session() -> None:
    client = FakeSupabaseClient(table_rows={"conversations": [{"id": "conv-1"}]})
    repository = ChatRepository(client)  # type: ignore[arg-type]

    conversation_id = repository.get_or_create_conversation("sesi-a")

    assert conversation_id == "conv-1"
    assert "inserts" not in client.calls


def test_get_or_create_conversation_inserts_when_missing() -> None:
    client = FakeSupabaseClient(table_rows={"conversations": []})
    repository = ChatRepository(client)  # type: ignore[arg-type]

    conversation_id = repository.get_or_create_conversation("sesi-baru", channel="whatsapp")

    assert conversation_id == "generated-0"
    assert client.calls["inserts"][0]["session_id"] == "sesi-baru"
    assert client.calls["inserts"][0]["channel"] == "whatsapp"


def test_get_history_returns_chronological_order() -> None:
    # Query aslinya mengurutkan menurun, jadi repository harus membalik hasilnya.
    client = FakeSupabaseClient(
        table_rows={
            "messages": [
                {"role": "assistant", "content": "pesan kedua", "created_at": None},
                {"role": "user", "content": "pesan pertama", "created_at": None},
            ]
        }
    )
    repository = ChatRepository(client)  # type: ignore[arg-type]

    history = repository.get_history("conv-1")

    assert [message.content for message in history] == ["pesan pertama", "pesan kedua"]


def test_save_tool_calls_persists_every_record() -> None:
    client = FakeSupabaseClient()
    repository = ChatRepository(client)  # type: ignore[arg-type]

    repository.save_tool_calls(
        "msg-1",
        [
            ToolCallRecord(
                tool_name="check_stock",
                arguments={"sku": "KAO-0001"},
                result_summary="TERSEDIA 12 pcs",
                latency_ms=42,
            )
        ],
    )

    payload = client.calls["inserts"][0]
    assert payload[0]["tool_name"] == "check_stock"
    assert payload[0]["latency_ms"] == 42


def test_save_tool_calls_skips_empty_list() -> None:
    client = FakeSupabaseClient()
    repository = ChatRepository(client)  # type: ignore[arg-type]

    repository.save_tool_calls("msg-1", [])

    assert "inserts" not in client.calls
