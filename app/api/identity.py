"""Identitas pengunjung tanpa akun, plus kepemilikan sesi percakapan.

Demo ini tidak punya login, tapi kuotanya harus melekat pada orang -- bukan
pada percakapan. Kalau jatah menempel pada sesi, membuka tab baru sudah cukup
untuk mendapat jatah baru, dan pembatasan apa pun jadi hiasan.

Dua mekanisme di sini:

1. Cookie bertanda tangan HMAC yang HttpOnly. JavaScript tidak bisa membacanya,
   apalagi memalsukannya -- itu bedanya dengan sessionStorage yang sepenuhnya
   dikendalikan klien.
2. Registri yang mengikat session_id ke pemiliknya. Tanpa ini, siapa pun yang
   tahu session_id orang lain bisa melanjutkan percakapan orang itu, karena
   ConversationMemory menerima id apa pun yang dikirim.
"""

import hashlib
import hmac
import secrets
import threading
import time
import uuid

from fastapi import Request, Response

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

NAMA_COOKIE = "gaya_visitor"
UMUR_COOKIE_DETIK = 30 * 24 * 60 * 60

# Sesi yang tidak dipakai dilupakan setelah sehari; pengunjung yang kembali
# mendapat sesi baru, sementara kuotanya tetap menempel pada cookie.
TTL_SESI_DETIK = 24 * 60 * 60

# Dipakai kalau DEMO_SIGNING_KEY tidak diisi. Tanda tangannya tetap tidak bisa
# dipalsukan, hanya saja cookie lama kehilangan keabsahannya setiap restart --
# sama seperti hitungan kuota yang memang sudah per-proses.
_kunci_sementara = secrets.token_hex(32)
_sudah_memperingatkan_kunci = False


def _kunci_penanda() -> bytes:
    """Ambil kunci HMAC untuk cookie pengunjung.

    Returns:
        Kunci dalam bentuk bytes.
    """
    global _sudah_memperingatkan_kunci

    kunci = settings.demo_signing_key
    if kunci:
        return kunci.encode("utf-8")

    if not _sudah_memperingatkan_kunci:
        _sudah_memperingatkan_kunci = True
        logger.warning(
            "DEMO_SIGNING_KEY kosong; memakai kunci acak per-proses. "
            "Kuota pengunjung akan direset setiap server restart."
        )
    return _kunci_sementara.encode("utf-8")


def tanda_tangani(visitor_id: str) -> str:
    """Bubuhkan tanda tangan pada identitas pengunjung.

    Args:
        visitor_id: Identitas pengunjung.

    Returns:
        Nilai cookie berbentuk "<id>.<tanda tangan>".
    """
    tanda = hmac.new(
        _kunci_penanda(), visitor_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{visitor_id}.{tanda}"


def verifikasi(nilai: str | None) -> str | None:
    """Baca identitas dari nilai cookie kalau tanda tangannya sah.

    Args:
        nilai: Isi cookie apa adanya.

    Returns:
        Identitas pengunjung, atau None kalau tidak sah.
    """
    if not nilai or "." not in nilai:
        return None

    visitor_id, _, tanda = nilai.rpartition(".")
    if not visitor_id:
        return None

    harapan = hmac.new(
        _kunci_penanda(), visitor_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    # compare_digest, bukan ==, supaya lama pembandingan tidak membocorkan
    # seberapa jauh tebakan penyerang benar.
    return visitor_id if hmac.compare_digest(harapan, tanda) else None


def baca_atau_terbitkan(request: Request, response: Response) -> str:
    """Ambil identitas pengunjung dari cookie, terbitkan baru kalau perlu.

    Cookie yang tanda tangannya tidak sah diperlakukan seperti tidak ada:
    identitas baru diterbitkan, bukan nilainya dipercaya.

    Args:
        request: Permintaan masuk.
        response: Respons yang akan dikirim; cookie dipasang di sini.

    Returns:
        Identitas pengunjung.
    """
    visitor_id = verifikasi(request.cookies.get(NAMA_COOKIE))
    if visitor_id:
        return visitor_id

    visitor_id = f"v-{uuid.uuid4().hex[:16]}"
    pasang_cookie(request, response, visitor_id)
    return visitor_id


def pasang_cookie(request: Request, response: Response, visitor_id: str) -> None:
    """Pasang cookie identitas pada respons.

    Args:
        request: Permintaan masuk, dipakai mendeteksi https.
        response: Respons yang akan dikirim.
        visitor_id: Identitas yang dipasang.
    """
    response.set_cookie(
        key=NAMA_COOKIE,
        value=tanda_tangani(visitor_id),
        max_age=UMUR_COOKIE_DETIK,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


class RegistriSesi:
    """Peta session_id ke pemiliknya, dengan masa berlaku.

    Disimpan di memori proses dan hilang saat restart. Konsekuensinya: sesi lama
    tidak bisa dilanjutkan setelah server restart, dan pengunjung akan diberi
    sesi baru. Memindahkannya ke Supabase adalah pekerjaan berikutnya.
    """

    def __init__(self, ttl_detik: int = TTL_SESI_DETIK) -> None:
        self._ttl = ttl_detik
        self._kunci = threading.Lock()
        self._pemilik: dict[str, tuple[str, float]] = {}

    def terbitkan(self, visitor_id: str) -> str:
        """Buat session_id baru milik satu pengunjung.

        Args:
            visitor_id: Pemilik sesi.

        Returns:
            Identifier sesi yang baru diterbitkan.
        """
        session_id = f"demo-{uuid.uuid4().hex[:12]}"
        with self._kunci:
            self._bersihkan()
            self._pemilik[session_id] = (visitor_id, time.monotonic())
        return session_id

    def dimiliki_oleh(self, session_id: str, visitor_id: str) -> bool:
        """Periksa apakah satu sesi memang milik pengunjung ini.

        Args:
            session_id: Sesi yang diklaim.
            visitor_id: Pengunjung yang mengklaim.

        Returns:
            True kalau cocok; False kalau milik orang lain atau sudah kedaluwarsa.
        """
        with self._kunci:
            self._bersihkan()
            tercatat = self._pemilik.get(session_id)
            return tercatat is not None and tercatat[0] == visitor_id

    def _bersihkan(self) -> None:
        batas = time.monotonic() - self._ttl
        kedaluwarsa = [
            sesi for sesi, (_, dibuat) in self._pemilik.items() if dibuat < batas
        ]
        for sesi in kedaluwarsa:
            del self._pemilik[sesi]
