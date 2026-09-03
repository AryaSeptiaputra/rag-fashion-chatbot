"""Akses data rekomendasi ukuran lewat RPC recommend_size."""

from app.models.inventory import SizeRecommendation
from app.repositories.base import BaseRepository


class SizingRepository(BaseRepository):
    """Pencocokan ukuran badan pembeli ke size chart produk."""

    _RECOMMEND_RPC = "recommend_size"

    def recommend(
        self,
        sku: str,
        chest_cm: float,
        waist_cm: float | None = None,
    ) -> list[SizeRecommendation]:
        """Cocokkan ukuran badan ke size chart produk.

        Args:
            sku: SKU produk induk.
            chest_cm: Lingkar dada pembeli dalam sentimeter.
            waist_cm: Lingkar pinggang dalam sentimeter; opsional.

        Returns:
            List kandidat ukuran terurut dari selisih terkecil.
        """
        rows = self.call_rpc(
            self._RECOMMEND_RPC,
            {
                "p_sku": sku.strip(),
                "p_chest_cm": chest_cm,
                "p_waist_cm": waist_cm,
            },
        )
        return [SizeRecommendation.model_validate(row) for row in rows]
