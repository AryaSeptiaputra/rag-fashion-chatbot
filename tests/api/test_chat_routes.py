"""Test endpoint chat dengan ChatbotService yang di-override."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.chat.service import get_chat_service
from app.api.main import create_app
from app.models.chat import AgentReply, ToolCallRecord


class StubChatbotService:
    """ChatbotService palsu yang mencatat pemanggilan dan mengembalikan jawaban tetap."""

    def __init__(self, reply: AgentReply | None = None, error: Exception | None = None) -> None:
        self.reply = reply or AgentReply(answer="Halo kak", tool_calls=[])
        self.error = error
        self.received: list[dict[str, str]] = []

    async def answer(self, session_id: str, message: str, channel: str = "web") -> AgentReply:
        """Kembalikan jawaban tetap, atau lempar error yang sudah disiapkan."""
        self.received.append(
            {"session_id": session_id, "message": message, "channel": channel}
        )
        if self.error is not None:
            raise self.error
        return self.reply


@pytest.fixture
def client_factory() -> Iterator[object]:
    """Sediakan pabrik TestClient dengan service yang bisa di-override."""
    app = create_app()

    def build(service: StubChatbotService) -> TestClient:
        app.dependency_overrides[get_chat_service] = lambda: service
        return TestClient(app)

    yield build
    app.dependency_overrides.clear()


def test_chat_returns_answer_and_tool_trace(client_factory) -> None:
    service = StubChatbotService(
        AgentReply(
            answer="Size L masih ada 12 pcs kak.",
            tool_calls=[
                ToolCallRecord(
                    tool_name="check_stock",
                    arguments={"sku": "KAO-0001", "size": "L"},
                    latency_ms=87,
                )
            ],
        )
    )
    client = client_factory(service)

    response = client.post(
        "/api/v1/chat",
        json={"session_id": "sesi-1", "message": "KAO-0001 size L ready?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Size L masih ada 12 pcs kak."
    assert payload["tool_calls"][0]["tool_name"] == "check_stock"
    assert payload["tool_calls"][0]["latency_ms"] == 87
    assert service.received[0]["session_id"] == "sesi-1"


def test_chat_rejects_empty_message(client_factory) -> None:
    client = client_factory(StubChatbotService())

    response = client.post("/api/v1/chat", json={"session_id": "sesi-1", "message": ""})

    assert response.status_code == 422


def test_chat_rejects_unknown_channel(client_factory) -> None:
    client = client_factory(StubChatbotService())

    response = client.post(
        "/api/v1/chat",
        json={"session_id": "sesi-1", "message": "halo", "channel": "telegram"},
    )

    assert response.status_code == 422


def test_chat_reports_service_not_ready_as_503(client_factory) -> None:
    service = StubChatbotService(error=RuntimeError("Koleksi FAQ 'faq' kosong."))
    client = client_factory(service)

    response = client.post(
        "/api/v1/chat", json={"session_id": "sesi-1", "message": "halo"}
    )

    assert response.status_code == 503
    assert "kosong" in response.json()["detail"]
