"""Logika bisnis katalog produk dan promo, beserta formatting untuk LLM.

Semua method publik mengembalikan string, bukan struktur bersarang. Alasannya:
LLM kecil sering salah menafsirkan dict/list bertingkat, sementara kalimat
terformat memaksa interpretasi yang seragam. Hasil kosong selalu dinyatakan
eksplisit supaya model tidak mengisi kekosongan dengan karangan.
"""

from decimal import Decimal

from app.models.catalog import ProductDetail, ProductSummary, Promotion
from app.repositories.catalog import CatalogRepository
from app.repositories.sales import SalesRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def format_rupiah(amount: Decimal) -> str:
    """Format angka jadi rupiah dengan pemisah ribuan.

    Args:
        amount: Nominal dalam rupiah.

    Returns:
        String seperti "Rp149.000".
    """
    return f"Rp{int(amount):,}".replace(",", ".")


class CatalogService:
    """Pencarian produk, detail produk, dan promo yang berlaku."""

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        sales_repository: SalesRepository,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.sales_repository = sales_repository

    def search_products(
        self,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        in_stock_only: bool = False,
    ) -> str:
        """Cari produk di katalog dan format hasilnya untuk LLM.

        Args:
            keyword: Kata kunci bebas dari pembeli.
            category: Nama kategori, dicocokkan sebagian.
            max_price: Batas atas harga.
            in_stock_only: Kalau True, hanya produk yang stoknya masih ada.

        Returns:
            Daftar produk terformat, atau pesan eksplisit kalau tidak ada hasil.
        """
        products = self.catalog_repository.search(
            keyword=keyword,
            category=category,
            max_price=max_price,
            in_stock_only=in_stock_only,
        )

        if not products:
            return (
                f"Tidak ditemukan produk yang cocok dengan pencarian "
                f"(keyword={keyword!r}, kategori={category!r}, "
                f"harga maks={max_price!r}). "
                "Produk ini tidak ada di katalog. Jangan mengarang produk lain."
            )

        lines = [f"Ditemukan {len(products)} produk:"]
        lines.extend(self._format_summary(product) for product in products)
        return "\n".join(lines)

    def get_product_detail(self, sku: str) -> str:
        """Ambil detail satu produk dan format untuk LLM.

        Args:
            sku: SKU produk induk.

        Returns:
            Detail produk terformat, atau pesan eksplisit kalau SKU tidak ada.
        """
        product = self.catalog_repository.get_detail(sku)
        if product is None:
            return (
                f"SKU '{sku}' tidak ada di katalog. "
                "Gunakan search_products untuk mencari SKU yang benar."
            )
        return self._format_detail(product)

    def check_promotion(
        self, code: str | None = None, sku: str | None = None
    ) -> str:
        """Cek promo yang sedang berlaku.

        Args:
            code: Kode promo yang disebut pembeli.
            sku: SKU produk yang ingin dicek promonya.

        Returns:
            Deskripsi promo terformat, atau pesan eksplisit kalau tidak ada
            promo yang berlaku.
        """
        if code:
            promotion = self.sales_repository.find_promotion_by_code(code)
            if promotion is None:
                return (
                    f"Kode promo '{code}' tidak berlaku saat ini. "
                    "Kode salah, sudah kedaluwarsa, atau belum dimulai. "
                    "Jangan menjanjikan diskon apa pun."
                )
            return self._format_promotion(promotion)

        promotions = self.sales_repository.list_active_promotions(product_sku=sku)
        if not promotions:
            target = f" untuk produk {sku}" if sku else ""
            return (
                f"Tidak ada promo aktif{target} saat ini. "
                "Jangan menjanjikan diskon apa pun."
            )

        lines = [f"Ada {len(promotions)} promo aktif:"]
        lines.extend(self._format_promotion(promo) for promo in promotions)
        return "\n".join(lines)

    def _format_summary(self, product: ProductSummary) -> str:
        price = (
            format_rupiah(product.min_price)
            if product.min_price == product.max_price
            else f"{format_rupiah(product.min_price)}-{format_rupiah(product.max_price)}"
        )
        stock = (
            f"stok {product.total_available} pcs"
            if product.total_available > 0
            else "STOK HABIS"
        )
        colors = ", ".join(product.available_colors) or "-"
        sizes = ", ".join(product.available_sizes) or "-"
        return (
            f"- {product.name} (SKU: {product.sku}) | {price} | {stock}\n"
            f"  Kategori: {product.category or '-'} | Potongan: {product.fit_type or '-'}\n"
            f"  Warna tersedia: {colors} | Ukuran tersedia: {sizes}"
        )

    def _format_detail(self, product: ProductDetail) -> str:
        price = (
            format_rupiah(product.min_price)
            if product.min_price == product.max_price
            else f"{format_rupiah(product.min_price)}-{format_rupiah(product.max_price)}"
        )
        status = "aktif dijual" if product.is_active else "TIDAK DIJUAL LAGI"
        stock = (
            f"{product.total_available} pcs tersedia"
            if product.total_available > 0
            else "STOK HABIS di semua varian"
        )
        return "\n".join(
            [
                f"Produk: {product.name} (SKU: {product.sku})",
                f"Status: {status}",
                f"Harga: {price}",
                f"Kategori: {product.category or '-'} | Koleksi: {product.collection or '-'}",
                f"Potongan: {product.fit_type or '-'} | Gender: {product.gender or '-'}",
                f"Bahan: {product.material or '-'}",
                f"Perawatan: {product.care_instructions or '-'}",
                f"Deskripsi: {product.description or '-'}",
                f"Warna tersedia: {', '.join(product.available_colors) or '-'}",
                f"Ukuran tersedia: {', '.join(product.available_sizes) or '-'}",
                f"Total stok: {stock} dari {product.variant_count} varian",
                f"Tag: {', '.join(product.tags) or '-'}",
            ]
        )

    def _format_promotion(self, promotion: Promotion) -> str:
        if promotion.discount_type == "percentage":
            value = f"diskon {int(promotion.discount_value)}%"
        else:
            value = f"potongan {format_rupiah(promotion.discount_value)}"

        scope = (
            "berlaku untuk semua produk"
            if promotion.applies_to_all
            else f"berlaku untuk: {', '.join(promotion.product_names)}"
        )
        minimum = (
            f", minimum belanja {format_rupiah(promotion.min_purchase)}"
            if promotion.min_purchase > 0
            else ""
        )
        expiry = promotion.end_at.strftime("%d %B %Y")
        return (
            f"- {promotion.name} (kode: {promotion.code}) | {value}{minimum}\n"
            f"  {scope} | berlaku sampai {expiry}"
        )
