"""Test dependency get_chat_service: kegagalan perakitan jadi 503, bukan 500."""

import pytest
from fastapi import HTTPException

from app.api.chat import service as service_module


@pytest.fixture(autouse=True)
def clear_service_cache() -> None:
    """Kosongkan cache supaya tiap test merakit ulang."""
    service_module._cached_chatbot_service.cache_clear()


def test_missing_credentials_become_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise ValueError("SUPABASE_URL dan SUPABASE_SERVICE_KEY wajib diisi di .env")

    monkeypatch.setattr(service_module, "build_chatbot_service", broken)

    with pytest.raises(HTTPException) as excinfo:
        service_module.get_chat_service()

    assert excinfo.value.status_code == 503
    assert "SUPABASE_URL" in excinfo.value.detail


def test_missing_faq_index_becomes_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise RuntimeError("Koleksi FAQ 'faq' kosong.")

    monkeypatch.setattr(service_module, "build_chatbot_service", broken)

    with pytest.raises(HTTPException) as excinfo:
        service_module.get_chat_service()

    assert excinfo.value.status_code == 503


def test_failure_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    # lru_cache tidak menyimpan exception, jadi request berikutnya harus
    # berhasil begitu konfigurasi diperbaiki tanpa perlu restart proses.
    attempts: list[int] = []

    def flaky() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("belum siap")
        return "service-siap"

    monkeypatch.setattr(service_module, "build_chatbot_service", flaky)

    with pytest.raises(HTTPException):
        service_module.get_chat_service()

    assert service_module.get_chat_service() == "service-siap"
    assert len(attempts) == 2
