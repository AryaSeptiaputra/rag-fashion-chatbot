"""Test kuota berlapis dan plafon anggaran.

Yang dijaga di sini adalah sifat yang membuat pembatasan ini ada gunanya sama
sekali: jatah melekat pada pengunjung, bukan pada percakapan. Kalau ia menempel
pada sesi, membuka obrolan baru sudah cukup untuk mendapat jatah baru, dan
seluruh pembatasan hanya jadi hiasan.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.chat.service import get_chat_service
from app.api.guards import WIB, AnggaranHarian, KuotaHarian, baca_ip_klien
from app.api.identity import NAMA_COOKIE, tanda_tangani
from app.api.main import create_app
from app.config import settings
from app.models.chat import AgentReply, TokenUsage


class LayananContoh:
    """Layanan chat palsu dengan biaya per giliran yang bisa diatur."""

    def __init__(self, cost_usd: float = 0.001) -> None:
        self.cost_usd = cost_usd

    async def answer(
        self,
        session_id: str,
        message: str,
        channel: str = "web",
        language: str = "id",
    ) -> AgentReply:
        """Kembalikan jawaban tetap dengan biaya yang sudah ditentukan."""
        return AgentReply(
            answer="Halo kak",
            usage=TokenUsage(input_tokens=1000, output_tokens=100, llm_calls=2),
            cost_usd=self.cost_usd,
        )


@pytest.fixture
def buat_klien(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    """Sediakan pabrik TestClient dengan ambang kuota yang bisa diatur."""
    dibuat: list[object] = []

    def build(
        kuota_pengunjung: int = 8,
        kuota_ip: int = 24,
        anggaran: float = 1.0,
        biaya_per_giliran: float = 0.001,
    ) -> TestClient:
        monkeypatch.setattr(settings, "demo_visitor_daily_quota", kuota_pengunjung)
        monkeypatch.setattr(settings, "demo_ip_daily_quota", kuota_ip)
        monkeypatch.setattr(settings, "demo_daily_budget_usd", anggaran)
        app = create_app()
        app.dependency_overrides[get_chat_service] = lambda: LayananContoh(
            biaya_per_giliran
        )
        dibuat.append(app)
        return TestClient(app)

    yield build
    for app in dibuat:
        app.dependency_overrides.clear()  # type: ignore[attr-defined]


def kirim(client: TestClient, session_id: str) -> object:
    """Kirim satu pertanyaan ke endpoint chat."""
    return client.post(
        "/api/v1/chat", json={"session_id": session_id, "message": "halo"}
    )


def habiskan(client: TestClient, session_id: str, jumlah: int) -> None:
    """Pakai sejumlah jatah sampai habis."""
    for _ in range(jumlah):
        assert kirim(client, session_id).status_code == 200


class TestKuotaMelekatPadaPengunjung:
    """Inti permintaannya: satu orang hanya boleh memakai jatahnya sendiri."""

    def test_obrolan_baru_tidak_mereset_jatah(self, buat_klien) -> None:
        """Kalau ini gagal, seluruh pembatasan bisa dielakkan satu klik."""
        client = buat_klien(kuota_pengunjung=2)
        sesi = client.post("/api/v1/session").json()["session_id"]
        habiskan(client, sesi, 2)

        # Pengunjung menekan "Mulai obrolan baru": sesi baru, cookie sama.
        sesi_baru = client.post("/api/v1/session").json()["session_id"]
        assert sesi_baru != sesi

        respons = kirim(client, sesi_baru)

        assert respons.status_code == 429
        assert respons.json()["detail"]["code"] == "kuota_pengunjung_habis"

    def test_cookie_yang_sama_tetap_habis_di_permintaan_berikutnya(
        self, buat_klien
    ) -> None:
        """Membuka tab baru memakai cookie yang sama, jadi jatahnya sama."""
        client = buat_klien(kuota_pengunjung=1)
        sesi = client.post("/api/v1/session").json()["session_id"]
        habiskan(client, sesi, 1)

        assert kirim(client, sesi).status_code == 429

    def test_pengunjung_lain_punya_jatah_sendiri(self, buat_klien) -> None:
        client = buat_klien(kuota_pengunjung=1)
        sesi = client.post("/api/v1/session").json()["session_id"]
        habiskan(client, sesi, 1)

        # Cookie dibuang, seperti membuka jendela penyamaran.
        client.cookies.clear()
        sesi_lain = client.post("/api/v1/session").json()["session_id"]

        assert kirim(client, sesi_lain).status_code == 200

    def test_lapis_ip_menahan_penghapus_cookie(self, buat_klien) -> None:
        """Lapis kedua ada justru untuk kasus cookie dibuang berulang kali."""
        client = buat_klien(kuota_pengunjung=1, kuota_ip=2)

        for _ in range(2):
            client.cookies.clear()
            sesi = client.post("/api/v1/session").json()["session_id"]
            assert kirim(client, sesi).status_code == 200

        client.cookies.clear()
        sesi = client.post("/api/v1/session").json()["session_id"]
        respons = kirim(client, sesi)

        assert respons.status_code == 429
        assert respons.json()["detail"]["code"] == "kuota_ip_habis"


class TestKepemilikanSesi:
    """Sesi orang lain tidak boleh bisa dilanjutkan."""

    def test_sesi_karangan_ditolak(self, buat_klien) -> None:
        client = buat_klien()
        client.post("/api/v1/session")

        respons = kirim(client, "demo-karangan")

        assert respons.status_code == 403
        assert respons.json()["detail"]["code"] == "sesi_tidak_dikenali"

    def test_sesi_pengunjung_lain_ditolak(self, buat_klien) -> None:
        client = buat_klien()
        sesi_korban = client.post("/api/v1/session").json()["session_id"]

        # Penyerang datang dengan cookie sendiri tapi membawa session_id korban.
        client.cookies.clear()
        client.post("/api/v1/session")

        respons = kirim(client, sesi_korban)

        assert respons.status_code == 403

    def test_cookie_dengan_tanda_tangan_palsu_tidak_dipercaya(
        self, buat_klien
    ) -> None:
        """Menyunting cookie tidak memberi identitas pilihan sendiri.

        Server menerbitkan identitas baru alih-alih memakai nilai yang dikirim,
        sehingga penyerang tidak bisa menebak identitas orang lain lalu memakai
        jatahnya. Efek sampingnya: klien yang bersikeras mengirim cookie ngawur
        mendapat identitas baru tiap permintaan dan tidak pernah bisa memegang
        sesi -- konsekuensi yang memang pantas.
        """
        client = buat_klien(kuota_pengunjung=1)
        client.cookies.clear()
        client.cookies.set(NAMA_COOKIE, "v-palsu.tandatanganngawur")

        respons = client.post("/api/v1/session")

        assert respons.status_code == 200
        # Jatah penuh membuktikan identitas palsunya tidak diadopsi.
        assert respons.json()["quota"]["remaining"] == 1
        assert respons.cookies.get(NAMA_COOKIE) is not None

    def test_verifikasi_menolak_tanda_tangan_palsu(self) -> None:
        from app.api.identity import verifikasi

        assert verifikasi("v-uji.tandatanganngawur") is None
        assert verifikasi(tanda_tangani("v-uji")) == "v-uji"
        assert verifikasi(None) is None
        assert verifikasi("tanpa-titik") is None

    def test_cookie_yang_ditandatangani_benar_diterima(self, buat_klien) -> None:
        client = buat_klien()
        client.cookies.set(NAMA_COOKIE, tanda_tangani("v-uji"))

        respons = client.post("/api/v1/session")

        assert respons.status_code == 200


class TestPlafonAnggaran:
    """Lapis terakhir yang tidak bisa dielakkan cookie maupun VPN."""

    def test_permintaan_ditolak_setelah_plafon_tercapai(self, buat_klien) -> None:
        client = buat_klien(anggaran=0.0025, biaya_per_giliran=0.001)
        sesi = client.post("/api/v1/session").json()["session_id"]
        habiskan(client, sesi, 3)

        respons = kirim(client, sesi)

        assert respons.status_code == 429
        assert respons.json()["detail"]["code"] == "budget_harian_habis"
        assert "resets_at" in respons.json()["detail"]

    def test_anggaran_dilaporkan_di_tiap_jawaban(self, buat_klien) -> None:
        client = buat_klien(anggaran=1.0, biaya_per_giliran=0.002)
        sesi = client.post("/api/v1/session").json()["session_id"]

        pertama = kirim(client, sesi).json()
        kedua = kirim(client, sesi).json()

        assert pertama["budget"]["spent_usd"] == 0.002
        assert kedua["budget"]["spent_usd"] == 0.004
        assert kedua["quota"]["remaining"] < pertama["quota"]["remaining"]

    def test_plafon_habis_tidak_memakan_jatah_pengunjung(self, buat_klien) -> None:
        """Permintaan yang pasti ditolak tidak boleh membebani pengunjung."""
        client = buat_klien(kuota_pengunjung=5, anggaran=0.0015, biaya_per_giliran=0.001)
        sesi = client.post("/api/v1/session").json()["session_id"]
        habiskan(client, sesi, 2)

        assert kirim(client, sesi).status_code == 429
        assert kirim(client, sesi).status_code == 429


class TestPergantianHari:
    """Hitungan direset tengah malam WIB, bukan UTC."""

    def test_anggaran_direset(self) -> None:
        saat = [datetime(2026, 9, 8, 23, 0, tzinfo=WIB)]
        anggaran = AnggaranHarian(0.01, now_fn=lambda: saat[0])
        anggaran.catat(0.02)

        with pytest.raises(Exception):
            anggaran.pastikan_tersedia()

        saat[0] = saat[0] + timedelta(hours=2)
        anggaran.pastikan_tersedia()
        assert anggaran.status().spent_usd == 0.0

    def test_kuota_direset(self) -> None:
        saat = [datetime(2026, 9, 8, 23, 0, tzinfo=WIB)]
        kuota = KuotaHarian(1, "habis", now_fn=lambda: saat[0])
        kuota.pakai("v-1")

        with pytest.raises(Exception):
            kuota.pakai("v-1")

        saat[0] = saat[0] + timedelta(hours=2)
        assert kuota.pakai("v-1").remaining == 0

    def test_reset_ditunjukkan_ke_klien(self) -> None:
        saat = datetime(2026, 9, 8, 10, 0, tzinfo=WIB)
        anggaran = AnggaranHarian(1.0, now_fn=lambda: saat)

        reset = anggaran.status().resets_at

        assert reset.date() == saat.date() + timedelta(days=1)
        assert reset.hour == 0
        assert reset.utcoffset() == timedelta(hours=7)


class TestAlamatIp:
    """Header proxy tidak boleh dipercaya tanpa dinyatakan."""

    def test_forwarded_for_diabaikan_secara_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "trusted_proxy_count", 0)

        class PermintaanPalsu:
            headers = {"x-forwarded-for": "1.2.3.4"}

            class client:
                host = "10.0.0.9"

        assert baca_ip_klien(PermintaanPalsu()) == "10.0.0.9"  # type: ignore[arg-type]

    def test_forwarded_for_dipakai_saat_proxy_dinyatakan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "trusted_proxy_count", 1)

        class PermintaanPalsu:
            headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}

            class client:
                host = "10.0.0.1"

        assert baca_ip_klien(PermintaanPalsu()) == "1.2.3.4"  # type: ignore[arg-type]
