"""Logika bisnis stok live dan rekomendasi ukuran.

Stok sengaja tidak pernah di-cache: satu transaksi bisa mengubahnya, dan
menyebut angka basi lebih merugikan daripada menjawab "tidak tahu".
"""

from app.models.inventory import SizeRecommendation, VariantAvailability
from app.repositories.inventory import InventoryRepository
from app.repositories.sizing import SizingRepository
from app.services.catalog import format_rupiah
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class InventoryService:
    """Pemeriksaan ketersediaan stok dan pencocokan ukuran."""

    def __init__(
        self,
        inventory_repository: InventoryRepository,
        sizing_repository: SizingRepository,
    ) -> None:
        self.inventory_repository = inventory_repository
        self.sizing_repository = sizing_repository

    def check_stock(
        self,
        sku: str,
        size: str | None = None,
        color: str | None = None,
    ) -> str:
        """Cek stok live dan format hasilnya untuk LLM.

        Args:
            sku: SKU produk induk atau variant_sku.
            size: Label ukuran; None berarti tampilkan semua ukuran.
            color: Nama warna; None berarti tampilkan semua warna.

        Returns:
            Status stok terformat, atau pesan eksplisit kalau varian tidak ada.
        """
        variants = self.inventory_repository.check(sku=sku, size=size, color=color)

        if not variants:
            filters = ", ".join(
                part
                for part in [
                    f"ukuran {size}" if size else "",
                    f"warna {color}" if color else "",
                ]
                if part
            )
            suffix = f" dengan {filters}" if filters else ""
            return (
                f"Varian untuk SKU '{sku}'{suffix} tidak ada di database. "
                "Kombinasi ini tidak dijual. Jangan mengarang ketersediaannya."
            )

        available = [item for item in variants if item.is_available]
        lines = [self._format_variant(item) for item in variants]

        if not available:
            header = f"SEMUA varian SKU '{sku}' yang dicek sedang HABIS:"
        else:
            header = f"Status stok SKU '{sku}' ({len(available)} varian tersedia):"

        return "\n".join([header, *lines])

    def recommend_size(
        self,
        sku: str,
        chest_cm: float,
        waist_cm: float | None = None,
    ) -> str:
        """Rekomendasikan ukuran berdasarkan ukuran badan pembeli.

        Args:
            sku: SKU produk induk.
            chest_cm: Lingkar dada pembeli dalam sentimeter.
            waist_cm: Lingkar pinggang dalam sentimeter; opsional.

        Returns:
            Rekomendasi ukuran terformat, atau pesan eksplisit kalau produk
            tidak punya size chart.
        """
        candidates = self.sizing_repository.recommend(
            sku=sku, chest_cm=chest_cm, waist_cm=waist_cm
        )

        if not candidates:
            return (
                f"Produk '{sku}' tidak punya size chart di database, "
                "jadi ukuran tidak bisa direkomendasikan. "
                "Sarankan pembeli menghubungi admin. Jangan menebak ukuran."
            )

        best = next((item for item in candidates if item.is_best_match), candidates[0])
        lines = [
            f"Size chart {best.product_name} (potongan {best.fit_type}), "
            f"untuk badan dada {chest_cm} cm"
            + (f" dan pinggang {waist_cm} cm:" if waist_cm else ":"),
            f"REKOMENDASI: ukuran {best.size} (selisih {best.fit_gap_cm} cm)",
            "Rincian semua ukuran:",
        ]
        lines.extend(self._format_size_row(item) for item in candidates)
        return "\n".join(lines)

    @staticmethod
    def _format_variant(item: VariantAvailability) -> str:
        if item.is_available:
            status = f"TERSEDIA {item.available_quantity} pcs"
        elif item.next_restock_date:
            status = f"HABIS, restock dijadwalkan {item.next_restock_date:%d %B %Y}"
        else:
            status = "HABIS, belum ada jadwal restock"

        return (
            f"- {item.size} / {item.color} (varian {item.variant_sku}) | "
            f"{format_rupiah(item.price)} | {status}"
        )

    @staticmethod
    def _format_size_row(item: SizeRecommendation) -> str:
        marker = " <-- paling pas" if item.is_best_match else ""
        return (
            f"- {item.size}: dada {item.chest_cm} cm, pinggang {item.waist_cm} cm, "
            f"panjang {item.length_cm} cm{marker}"
        )
