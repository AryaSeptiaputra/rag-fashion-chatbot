"""Akses data contoh untuk halaman panduan demo.

Repository sendiri, bukan select_view(), karena query di sini butuh filter yang
belum didukung fondasi: lebih-besar-dari untuk stok tersedia, dan bukan-null
untuk jadwal restock. Menggeneralisasi select_view demi satu pemanggil akan
menambah permukaan yang harus dijaga di seluruh repository lain.
"""

from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError

from app.repositories.base import BaseRepository, RepositoryError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DemoRepository(BaseRepository):
    """Membaca contoh varian, pesanan, dan promo untuk halaman panduan."""

    def variants_ready(self, limit: int = 2) -> list[dict[str, Any]]:
        """Ambil varian yang stoknya masih ada.

        Args:
            limit: Jumlah baris terbanyak.

        Returns:
            Baris dari v_variant_availability.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        return self._jalankan(
            "varian tersedia",
            lambda: self.client.table("v_variant_availability")
            .select(
                "variant_sku, product_sku, product_name, size, color, "
                "available_quantity"
            )
            .gt("available_quantity", 0)
            .limit(limit)
            .execute(),
        )

    def variants_restock(self, limit: int = 1) -> list[dict[str, Any]]:
        """Ambil varian yang habis tapi punya jadwal restock.

        Varian ini yang paling berguna di panduan: pertanyaan tentangnya
        memperlihatkan chatbot menyebut tanggal restock alih-alih mengarang
        ketersediaan.

        Args:
            limit: Jumlah baris terbanyak.

        Returns:
            Baris dari v_variant_availability.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        return self._jalankan(
            "varian restock",
            lambda: self.client.table("v_variant_availability")
            .select("variant_sku, product_name, size, color, next_restock_date")
            .eq("available_quantity", 0)
            .not_.is_("next_restock_date", "null")
            .limit(limit)
            .execute(),
        )

    def orders_delivered(self, limit: int = 1) -> list[dict[str, Any]]:
        """Ambil pesanan yang sudah terkirim beserta 4 digit HP pemesannya.

        Args:
            limit: Jumlah baris terbanyak.

        Returns:
            Baris dari v_order_tracking.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        return self._jalankan(
            "pesanan terkirim",
            lambda: self.client.table("v_order_tracking")
            .select("order_number, phone_last4, order_status")
            .eq("order_status", "delivered")
            .limit(limit)
            .execute(),
        )

    def promotions(self, limit: int = 6) -> list[dict[str, Any]]:
        """Ambil promo beserta periodenya.

        Statusnya tidak dihitung di sini: repository mengembalikan tanggal apa
        adanya, dan service yang menyimpulkan aktif, kedaluwarsa, atau belum
        mulai.

        Args:
            limit: Jumlah baris terbanyak.

        Returns:
            Baris dari tabel promotions.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        return self._jalankan(
            "promo",
            lambda: self.client.table("promotions")
            .select("code, name, discount_type, discount_value, start_at, end_at")
            .eq("is_active", True)
            .limit(limit)
            .execute(),
        )

    def _jalankan(self, nama: str, kueri: Any) -> list[dict[str, Any]]:
        """Jalankan satu query dan seragamkan errornya.

        Args:
            nama: Nama operasi untuk log.
            kueri: Callable tanpa argumen yang mengeksekusi query.

        Returns:
            Baris hasil.

        Raises:
            RepositoryError: Kalau PostgREST mengembalikan error.
        """
        try:
            response = kueri()
        except APIError as exc:
            logger.error(f"Query {nama} gagal: {exc.message}", exc_info=True)
            raise RepositoryError(f"Query {nama} gagal dijalankan") from exc

        return self._as_rows(response.data)


def status_promo(start_at: Any, end_at: Any, sekarang: datetime | None = None) -> str:
    """Simpulkan status satu promo dari periodenya.

    Kode mesin, bukan prosa: frontend yang melokalkannya sesuai bahasa aktif.

    Args:
        start_at: Awal periode, string ISO atau datetime.
        end_at: Akhir periode, string ISO atau datetime.
        sekarang: Waktu acuan; default waktu sekarang UTC.

    Returns:
        "active", "expired", atau "scheduled".
    """
    saat = sekarang or datetime.now(timezone.utc)
    mulai = _sebagai_waktu(start_at)
    selesai = _sebagai_waktu(end_at)

    if selesai is not None and selesai < saat:
        return "expired"
    if mulai is not None and mulai > saat:
        return "scheduled"
    return "active"


def _sebagai_waktu(nilai: Any) -> datetime | None:
    """Ubah nilai tanggal apa pun jadi datetime beraware.

    Args:
        nilai: String ISO, datetime, atau None.

    Returns:
        Datetime dengan zona waktu, atau None kalau tidak bisa dibaca.
    """
    if nilai is None:
        return None
    if isinstance(nilai, datetime):
        waktu = nilai
    else:
        try:
            waktu = datetime.fromisoformat(str(nilai).replace("Z", "+00:00"))
        except ValueError:
            return None

    return waktu if waktu.tzinfo else waktu.replace(tzinfo=timezone.utc)
