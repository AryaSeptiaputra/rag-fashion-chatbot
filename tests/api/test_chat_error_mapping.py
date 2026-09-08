"""Test pemetaan error Claude API ke status HTTP.

Regresi yang dijaga: saat saldo kredit Anthropic habis, endpoint /chat
mengembalikan HTTP 500 tanpa petunjuk apa pun. Operator tidak punya cara tahu
bahwa masalahnya ada di tagihan, bukan di aplikasi.
"""

import anthropic
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.api.chat.service import get_chat_service
from app.api.main import create_app
from app.models.chat import AgentReply
from app.repositories.base import RepositoryError

from tests.api.conftest import buka_sesi


def build_api_error(status_code: int, message: str) -> anthropic.APIStatusError:
    """Bangun APIStatusError seperti yang dilempar SDK anthropic."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(
        status_code,
        request=request,
        json={"type": "error", "error": {"type": "invalid_request_error", "message": message}},
    )
    return anthropic.APIStatusError(message, response=response, body=None)


class FailingChatbotService:
    """ChatbotService palsu yang selalu melempar error tertentu."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def answer(
        self,
        session_id: str,
        message: str,
        channel: str = "web",
        language: str = "id",
    ) -> AgentReply:
        """Selalu gagal dengan error yang sudah disiapkan."""
        raise self.error


def client_for(error: Exception) -> TestClient:
    """Bangun TestClient dengan ChatbotService yang selalu gagal."""
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: FailingChatbotService(error)
    return TestClient(app, raise_server_exceptions=False)


def post_chat(client: TestClient) -> httpx.Response:
    """Kirim satu permintaan chat yang valid, memakai sesi terbitan server."""
    sesi = buka_sesi(client)
    return client.post(
        "/api/v1/chat", json={"session_id": sesi, "message": "halo"}
    )


def test_credit_exhausted_becomes_502_with_reason() -> None:
    error = build_api_error(
        400, "Your credit balance is too low to access the Anthropic API."
    )

    response = post_chat(client_for(error))

    assert response.status_code == 502
    assert "credit balance" in response.json()["detail"]


def test_rate_limit_becomes_429() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    http_response = httpx.Response(429, request=request, json={"error": {"message": "slow down"}})
    error = anthropic.RateLimitError("rate limited", response=http_response, body=None)

    response = post_chat(client_for(error))

    assert response.status_code == 429


def test_upstream_outage_becomes_502() -> None:
    error = build_api_error(529, "Overloaded")

    response = post_chat(client_for(error))

    assert response.status_code == 502


def test_connection_failure_becomes_502() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)

    response = post_chat(client_for(error))

    assert response.status_code == 502


def test_database_failure_still_becomes_502() -> None:
    response = post_chat(client_for(RepositoryError("Query gagal dijalankan")))

    assert response.status_code == 502


def test_service_not_ready_still_becomes_503() -> None:
    response = post_chat(client_for(RuntimeError("Koleksi FAQ 'faq' kosong.")))

    assert response.status_code == 503


@pytest.mark.parametrize("status_code", [400, 404, 500, 529])
def test_no_anthropic_error_leaks_as_500(status_code: int) -> None:
    # HTTP 500 berarti bug aplikasi. Kegagalan pihak ketiga tidak boleh
    # menyamar sebagai bug kita.
    response = post_chat(client_for(build_api_error(status_code, "boom")))

    assert response.status_code != 500
