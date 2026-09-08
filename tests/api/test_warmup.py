"""Test endpoint pemanasan.

Yang paling penting dijaga di sini: /warmup tidak boleh memanggil Anthropic.
Endpoint ini dipicu otomatis setiap halaman panduan dibuka, jadi satu panggilan
berbayar yang menyelinap masuk akan menghabiskan saldo demo hanya karena orang
melihat-lihat.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import chat as paket_chat
from app.api.chat import routes as modul_routes
from app.api.main import create_app


class LlmPengintai:
    """LLM palsu yang meledak begitu ada yang mencoba memanggilnya."""

    def __init__(self) -> None:
        self.dipanggil = False

    def chat(self, *args: object, **kwargs: object) -> None:
        """Tidak boleh pernah dijalankan."""
        self.dipanggil = True
        raise AssertionError("warmup memanggil Anthropic")

    async def achat(self, *args: object, **kwargs: object) -> None:
        """Tidak boleh pernah dijalankan."""
        self.dipanggil = True
        raise AssertionError("warmup memanggil Anthropic")


@pytest.fixture
def komponen_palsu(monkeypatch: pytest.MonkeyPatch) -> LlmPengintai:
    """Ganti seluruh komponen berat dengan pengganti murah."""
    pengintai = LlmPengintai()

    class KoleksiPalsu:
        def count(self) -> int:
            return 35

    class ChromaPalsu:
        def get_collection(self, nama: str) -> KoleksiPalsu:
            return KoleksiPalsu()

    monkeypatch.setattr(modul_routes, "get_embedding_model", lambda: object())
    monkeypatch.setattr(modul_routes, "get_chroma_client", lambda: ChromaPalsu())
    monkeypatch.setattr(modul_routes, "get_supabase_client", lambda: object())
    monkeypatch.setattr(modul_routes, "_cached_chatbot_service", lambda: object())
    monkeypatch.setattr(paket_chat.service, "get_llm", lambda: pengintai)
    return pengintai


def test_warmup_melaporkan_setiap_langkah(komponen_palsu) -> None:
    client = TestClient(create_app())

    respons = client.post("/api/v1/warmup")

    assert respons.status_code == 200
    isi = respons.json()
    assert isi["ready"] is True
    assert isi["faq_chunks"] == 35
    assert [langkah["name"] for langkah in isi["steps"]] == [
        "embedding_model",
        "chroma",
        "supabase",
        "chatbot_service",
    ]
    assert all(langkah["ok"] for langkah in isi["steps"])


def test_warmup_tidak_pernah_memanggil_anthropic(komponen_palsu) -> None:
    client = TestClient(create_app())

    client.post("/api/v1/warmup")

    assert komponen_palsu.dipanggil is False


def test_satu_langkah_gagal_tidak_menutupi_yang_lain(
    komponen_palsu, monkeypatch: pytest.MonkeyPatch
) -> None:
    def supabase_rusak() -> None:
        raise ValueError("SUPABASE_URL wajib diisi")

    monkeypatch.setattr(modul_routes, "get_supabase_client", supabase_rusak)
    client = TestClient(create_app())

    isi = client.post("/api/v1/warmup").json()
    langkah = {satu["name"]: satu for satu in isi["steps"]}

    assert isi["ready"] is False
    assert langkah["supabase"]["ok"] is False
    assert "SUPABASE_URL" in langkah["supabase"]["detail"]
    # Langkah lain tetap dilaporkan apa adanya, bukan ikut gugur.
    assert langkah["embedding_model"]["ok"] is True
    assert langkah["chroma"]["ok"] is True


def test_warmup_mengembalikan_anggaran_untuk_meter(komponen_palsu) -> None:
    client = TestClient(create_app())

    isi = client.post("/api/v1/warmup").json()

    # Supaya meter di sidebar punya nilai saat pertama render, tanpa perlu
    # endpoint kelima.
    assert isi["budget"]["limit_usd"] > 0
    assert isi["budget"]["spent_usd"] == 0
