"""Akses data penjualan: pelacakan pesanan dan promo aktif."""

from app.models.catalog import Promotion
from app.models.order import OrderTracking
from app.repositories.base import BaseRepository


class SalesRepository(BaseRepository):
    """Pembacaan status pesanan dan promo yang sedang berlaku."""

    _TRACK_RPC = "track_order"
    _PROMOTION_VIEW = "v_active_promotions"

    def track_order(self, order_number: str, phone_last4: str) -> OrderTracking | None:
        """Lacak pesanan setelah verifikasi identitas.

        RPC di database mensyaratkan nomor pesanan dan 4 digit terakhir nomor HP
        cocok; kombinasi yang salah mengembalikan nol baris.

        Args:
            order_number: Nomor pesanan yang diberikan pembeli.
            phone_last4: Empat digit terakhir nomor HP pemesan.

        Returns:
            Status pesanan, atau None kalau verifikasi gagal atau pesanan tidak ada.
        """
        rows = self.call_rpc(
            self._TRACK_RPC,
            {
                "p_order_number": order_number.strip(),
                "p_phone_last4": phone_last4.strip(),
            },
        )
        if not rows:
            return None
        return OrderTracking.model_validate(rows[0])

    def list_active_promotions(self, product_sku: str | None = None) -> list[Promotion]:
        """Ambil promo yang berlaku saat ini.

        Args:
            product_sku: Kalau diisi, hanya promo yang mencakup SKU tersebut
                (termasuk promo yang berlaku untuk seluruh katalog).

        Returns:
            List promo aktif.
        """
        rows = self.select_view(self._PROMOTION_VIEW)
        promotions = [Promotion.model_validate(row) for row in rows]

        if product_sku is None:
            return promotions

        target = product_sku.strip().upper()
        return [
            promo
            for promo in promotions
            if promo.applies_to_all
            or target in {sku.upper() for sku in promo.product_skus}
        ]

    def find_promotion_by_code(self, code: str) -> Promotion | None:
        """Cari promo aktif berdasarkan kode.

        Args:
            code: Kode promo yang disebut pembeli.

        Returns:
            Promo aktif dengan kode tersebut, atau None kalau tidak berlaku.
        """
        rows = self.select_view(
            self._PROMOTION_VIEW, filters={"code": code.strip().upper()}, limit=1
        )
        if not rows:
            return None
        return Promotion.model_validate(rows[0])
