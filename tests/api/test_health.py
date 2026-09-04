"""Test endpoint health, terutama pelaporan kesiapan LLM lokal.

Regresi yang dijaga: penyebab gagal paling sering varian lokal adalah server
Ollama belum jalan atau model belum di-pull. Kalau itu tidak terlihat di
/health, operator baru tahu setelah pembeli mengirim pesan dan dapat 502.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.chat import routes
from app.api.main import create_app


class StubCollection:
    """Koleksi Chroma palsu dengan jumlah chunk tetap."""

    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        """Kembalikan jumlah chunk."""
        return self._count


class StubChromaClient:
    """Client Chroma palsu yang tidak menyentuh disk."""

    def __init__(self, count: int) -> None:
        self._count = count

    def get_collection(self, name: str) -> StubCollection:
        """Kembalikan koleksi palsu."""
        return StubCollection(self._count)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient dengan seluruh dependensi eksternal dipalsukan."""
    monkeypatch.setattr(routes, "get_chroma_client", lambda: StubChromaClient(42))
    monkeypatch.setattr(routes, "get_supabase_client", lambda: object())
    yield TestClient(create_app(), raise_server_exceptions=False)


def test_all_components_ready_reports_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "probe_llm_ready", lambda: (True, "Ollama siap"))

    payload = client.get("/api/v1/health").json()

    assert payload["status"] == "ok"
    assert payload["llm_ready"] is True
    assert payload["faq_chunks"] == 42


def test_unreachable_ollama_degrades_status_and_says_why(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routes, "probe_llm_ready", lambda: (False, "Jalankan: ollama serve")
    )

    payload = client.get("/api/v1/health").json()

    assert payload["status"] == "degraded"
    assert payload["llm_ready"] is False
    assert "ollama serve" in payload["llm_detail"]


def test_missing_faq_index_still_degrades(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "probe_llm_ready", lambda: (True, "Ollama siap"))
    monkeypatch.setattr(routes, "get_chroma_client", lambda: StubChromaClient(0))

    payload = client.get("/api/v1/health").json()

    assert payload["status"] == "degraded"
    assert payload["llm_ready"] is True
