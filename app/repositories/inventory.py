"""Akses data stok live lewat RPC check_availability."""

from app.models.inventory import VariantAvailability
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository):
    """Pembacaan ketersediaan stok per varian."""

    _AVAILABILITY_RPC = "check_availability"

    def check(
        self,
        sku: str,
        size: str | None = None,
        color: str | None = None,
    ) -> list[VariantAvailability]:
        """Ambil stok live untuk SKU produk atau varian.

        Args:
            sku: SKU produk induk atau variant_sku.
            size: Label ukuran; None berarti semua ukuran.
            color: Nama warna; None berarti semua warna.

        Returns:
            List ketersediaan per varian yang cocok.
        """
        rows = self.call_rpc(
            self._AVAILABILITY_RPC,
            {
                "p_sku": sku.strip(),
                "p_size": size.strip() if size else None,
                "p_color": color.strip() if color else None,
            },
        )
        return [VariantAvailability.model_validate(row) for row in rows]
