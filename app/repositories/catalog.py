"""Akses data katalog produk lewat view v_product_catalog dan RPC search_products."""

from app.models.catalog import ProductDetail, ProductSummary
from app.repositories.base import BaseRepository


class CatalogRepository(BaseRepository):
    """Pencarian dan pembacaan detail produk."""

    _SEARCH_RPC = "search_products"
    _CATALOG_VIEW = "v_product_catalog"

    def search(
        self,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        in_stock_only: bool = False,
        limit: int = 8,
    ) -> list[ProductSummary]:
        """Cari produk di katalog.

        Args:
            keyword: Kata kunci bebas; None berarti tanpa filter teks.
            category: Nama kategori, dicocokkan sebagian.
            max_price: Batas atas harga terendah produk.
            in_stock_only: Kalau True, hanya produk dengan stok tersedia.
            limit: Jumlah maksimum hasil.

        Returns:
            List ringkasan produk terurut relevansi.
        """
        rows = self.call_rpc(
            self._SEARCH_RPC,
            {
                "p_keyword": keyword,
                "p_category": category,
                "p_max_price": max_price,
                "p_in_stock_only": in_stock_only,
                "p_limit": limit,
            },
        )
        return [ProductSummary.model_validate(row) for row in rows]

    def get_detail(self, sku: str) -> ProductDetail | None:
        """Ambil detail satu produk berdasarkan SKU.

        Args:
            sku: SKU produk induk.

        Returns:
            Detail produk, atau None kalau SKU tidak ada.
        """
        rows = self.select_view(self._CATALOG_VIEW, filters={"sku": sku.strip()}, limit=1)
        if not rows:
            return None
        return ProductDetail.model_validate(rows[0])
