"""Perkakas bersama untuk test endpoint HTTP."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.fixture(autouse=True)
def jalur_asli() -> Iterator[None]:
    """Matikan mode contoh supaya test menguji perakitan layanan sungguhan.

    Berkas .env pengembangan menyalakan DEMO_STUB_LLM, dan kalau itu ikut aktif
    di test, get_chat_service() akan mengembalikan layanan contoh dan
    percabangan kesiapan yang justru diuji tidak pernah dijalankan.
    """
    sebelumnya = settings.demo_stub_llm
    settings.demo_stub_llm = False
    yield
    settings.demo_stub_llm = sebelumnya


def buka_sesi(client: TestClient) -> str:
    """Terbitkan sesi yang sah lewat endpoint resmi.

    Sejak kuota melekat pada pengunjung, /chat menolak session_id yang tidak
    terdaftar sebagai milik pemegang cookie. TestClient menyimpan cookie antar
    permintaan, jadi memanggil ini sekali sudah cukup untuk seluruh percakapan
    dalam satu test.

    Args:
        client: Klien test yang akan dipakai mengirim chat.

    Returns:
        session_id yang sah untuk klien tersebut.
    """
    respons = client.post("/api/v1/session")
    assert respons.status_code == 200, respons.text
    return respons.json()["session_id"]
