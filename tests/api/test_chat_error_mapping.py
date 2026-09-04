"""Test pemetaan kegagalan LLM lokal ke status HTTP.

Regresi yang dijaga: saat server Ollama mati atau model belum di-pull,
endpoint /chat mengembalikan HTTP 500 tanpa petunjuk apa pun. Operator tidak
punya cara tahu bahwa masalahnya ada di model lokal, bukan di aplikasi.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from ollama import ResponseError

from app.api.chat.service import get_chat_service
from app.api.main import create_app
from app.models.chat import AgentReply
from app.repositories.base import RepositoryError


class FailingChatbotService:
    """ChatbotService palsu yang selalu melempar error tertentu."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def answer(self, session_id: str, message: str, channel: str = "web") -> AgentReply:
        """Selalu gagal dengan error yang sudah disiapkan."""
        raise self.error


def client_for(error: Exception) -> TestClient:
    """Bangun TestClient dengan ChatbotService yang selalu gagal."""
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: FailingChatbotService(error)
    return TestClient(app, raise_server_exceptions=False)


def post_chat(client: TestClient) -> httpx.Response:
    """Kirim satu permintaan chat yang valid."""
    return client.post(
        "/api/v1/chat", json={"session_id": "sesi-1", "message": "halo"}
    )


def test_server_down_becomes_502_with_fix_instruction() -> None:
    response = post_chat(client_for(httpx.ConnectError("connection refused")))

    assert response.status_code == 502
    assert "ollama serve" in response.json()["detail"]


def test_model_not_pulled_becomes_502_with_pull_instruction() -> None:
    response = post_chat(client_for(ResponseError('model "qwen3:1.7b" not found')))

    assert response.status_code == 502
    assert "ollama pull" in response.json()["detail"]


def test_timeout_becomes_502_and_says_so() -> None:
    response = post_chat(client_for(httpx.ReadTimeout("terlalu lama")))

    assert response.status_code == 502
    assert "detik" in response.json()["detail"]


def test_database_failure_still_becomes_502() -> None:
    response = post_chat(client_for(RepositoryError("Query gagal dijalankan")))

    assert response.status_code == 502


def test_service_not_ready_still_becomes_503() -> None:
    response = post_chat(client_for(RuntimeError("Koleksi FAQ 'faq' kosong.")))

    assert response.status_code == 503


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("timeout saat connect"),
        httpx.ReadTimeout("timeout saat baca"),
        ResponseError("boom"),
        ConnectionError("socket putus"),
    ],
)
def test_no_llm_failure_leaks_as_500(error: Exception) -> None:
    # HTTP 500 berarti bug aplikasi. Kegagalan model lokal tidak boleh
    # menyamar sebagai bug kita.
    response = post_chat(client_for(error))

    assert response.status_code == 502
