"""Pengaman kuota dan anggaran untuk demo tanpa akun.

Tiga lapis, dan ketiganya harus lolos sebelum satu pertanyaan dilayani:

1. Kuota pengunjung, dikunci ke cookie bertanda tangan. Menahan kasus normal --
   membuka tab baru, memulai obrolan baru, me-refresh halaman.
2. Kuota IP, ambangnya lebih longgar. Menahan penghapus cookie dan jendela
   penyamaran, tanpa langsung mematikan kantor atau kampus yang berbagi IP.
3. Plafon anggaran harian. Satu-satunya lapis yang tidak bisa dielakkan, dan
   karena itulah ia ada: pengunjung gigih dengan VPN dan cookie bersih tetap
   lolos lapis 1 dan 2.

Seluruh hitungan disimpan di memori proses. Konsekuensinya harus dinyatakan
terbuka: hitungan hilang saat server restart, dan uvicorn dengan beberapa worker
menghasilkan beberapa anggaran independen. Jalankan demo dengan satu worker.
"""

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from app.api.chat.schemas import BudgetStatus, QuotaStatus
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Offset tetap, bukan zoneinfo: Indonesia tidak mengenal DST, dan zoneinfo di
# Windows tidak punya basis data tz sehingga akan memaksa paket tzdata masuk
# requirements tanpa manfaat apa pun.
WIB = timezone(timedelta(hours=7))


def sekarang_wib() -> datetime:
    """Waktu saat ini di zona WIB.

    Returns:
        Datetime beraware zona WIB.
    """
    return datetime.now(WIB)


def _tengah_malam_berikutnya(saat: datetime) -> datetime:
    """Hitung kapan hitungan harian direset.

    Args:
        saat: Waktu acuan.

    Returns:
        Tengah malam WIB berikutnya.
    """
    besok = saat.date() + timedelta(days=1)
    return datetime.combine(besok, datetime.min.time(), tzinfo=WIB)


class AnggaranHarian:
    """Plafon belanja Claude API per hari untuk seluruh pengunjung."""

    def __init__(
        self,
        limit_usd: float,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._limit = limit_usd
        self._now = now_fn or sekarang_wib
        self._kunci = threading.Lock()
        self._hari = self._now().date()
        self._terpakai = 0.0

    def status(self) -> BudgetStatus:
        """Ambil potret anggaran hari ini.

        Returns:
            Sisa dan pemakaian anggaran.
        """
        with self._kunci:
            self._reset_kalau_ganti_hari()
            saat = self._now()
            sisa = max(self._limit - self._terpakai, 0.0)
            persen = (
                min(round(self._terpakai / self._limit * 100), 100)
                if self._limit > 0
                else 100
            )
            return BudgetStatus(
                spent_usd=round(self._terpakai, 6),
                limit_usd=self._limit,
                remaining_usd=round(sisa, 6),
                percent_used=persen,
                resets_at=_tengah_malam_berikutnya(saat),
            )

    def pastikan_tersedia(self) -> None:
        """Tolak permintaan kalau plafon sudah tercapai.

        Raises:
            HTTPException: 429 dengan kode budget_harian_habis.
        """
        with self._kunci:
            self._reset_kalau_ganti_hari()
            if self._terpakai < self._limit:
                return
            reset = _tengah_malam_berikutnya(self._now())

        logger.warning(f"Plafon anggaran harian tercapai: {self._terpakai:.6f} USD")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "budget_harian_habis",
                "resets_at": reset.isoformat(),
            },
        )

    def catat(self, biaya_usd: float) -> None:
        """Bebankan biaya satu giliran yang sudah selesai.

        Biaya baru diketahui setelah panggilan selesai, jadi plafon bisa
        terlampaui paling banyak satu giliran. Itu disengaja: menahan giliran
        sampai biayanya pasti berarti tidak pernah bisa menjawab sama sekali.

        Args:
            biaya_usd: Biaya giliran dalam dolar.
        """
        with self._kunci:
            self._reset_kalau_ganti_hari()
            self._terpakai += max(biaya_usd, 0.0)

    def _reset_kalau_ganti_hari(self) -> None:
        hari_ini = self._now().date()
        if hari_ini != self._hari:
            self._hari = hari_ini
            self._terpakai = 0.0


class KuotaHarian:
    """Penghitung jatah pertanyaan per kunci, direset tiap tengah malam WIB."""

    def __init__(
        self,
        limit: int,
        kode_penolakan: str,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._limit = limit
        self._kode = kode_penolakan
        self._now = now_fn or sekarang_wib
        self._kunci = threading.Lock()
        self._hari = self._now().date()
        self._terpakai: dict[str, int] = {}

    def status(self, kunci: str) -> QuotaStatus:
        """Ambil sisa jatah satu kunci tanpa memakainya.

        Args:
            kunci: Identitas pengunjung atau alamat IP.

        Returns:
            Sisa jatah dan kapan direset.
        """
        with self._kunci:
            self._reset_kalau_ganti_hari()
            return self._status(kunci)

    def pakai(self, kunci: str) -> QuotaStatus:
        """Ambil satu jatah, atau tolak kalau sudah habis.

        Args:
            kunci: Identitas pengunjung atau alamat IP.

        Returns:
            Sisa jatah setelah dipakai.

        Raises:
            HTTPException: 429 dengan kode penolakan lapis ini.
        """
        with self._kunci:
            self._reset_kalau_ganti_hari()
            if self._terpakai.get(kunci, 0) >= self._limit:
                reset = _tengah_malam_berikutnya(self._now())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"code": self._kode, "resets_at": reset.isoformat()},
                )
            self._terpakai[kunci] = self._terpakai.get(kunci, 0) + 1
            return self._status(kunci)

    def _status(self, kunci: str) -> QuotaStatus:
        terpakai = self._terpakai.get(kunci, 0)
        return QuotaStatus(
            limit=self._limit,
            remaining=max(self._limit - terpakai, 0),
            resets_at=_tengah_malam_berikutnya(self._now()),
        )

    def _reset_kalau_ganti_hari(self) -> None:
        hari_ini = self._now().date()
        if hari_ini != self._hari:
            self._hari = hari_ini
            self._terpakai.clear()


def baca_ip_klien(request: Request) -> str:
    """Tentukan alamat IP pengunjung.

    X-Forwarded-For hanya dibaca kalau operator menyatakan berapa proxy yang
    berdiri di depan aplikasi. Tanpa itu header tersebut diabaikan sepenuhnya:
    siapa pun bisa mengirimnya, dan memercayainya membuat lapis kuota IP tidak
    ada gunanya.

    Args:
        request: Permintaan masuk.

    Returns:
        Alamat IP, atau "tidak-diketahui" kalau tidak bisa ditentukan.
    """
    langsung = request.client.host if request.client else None

    jumlah_proxy = settings.trusted_proxy_count
    if jumlah_proxy > 0:
        header = request.headers.get("x-forwarded-for", "")
        rantai = [bagian.strip() for bagian in header.split(",") if bagian.strip()]
        # Proxy menambahkan alamat di sebelah kanan; buang sebanyak yang
        # dinyatakan tepercaya, lalu ambil yang terakhir tersisa.
        tersisa = rantai[:-jumlah_proxy] if len(rantai) > jumlah_proxy else []
        if tersisa:
            return tersisa[-1]

    return langsung or "tidak-diketahui"
