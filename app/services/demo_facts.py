"""Menyusun data acuan halaman panduan dari database.

Satu sumber kebenaran untuk dua pemakai: endpoint /demo/facts dan ringkasan
yang dicetak scripts/seed_database.py di akhir seeding. Menyalin querynya ke
dua tempat berarti suatu saat panduan akan menampilkan SKU yang sudah tidak
ada -- kegagalan paling memalukan di depan orang yang sedang menilai.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.demo import DemoFacts, OrderFact, PromoFact, VariantFact
from app.repositories.demo import DemoRepository, status_promo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DemoFactsService:
    """Mengambil dan menyimpan sementara data acuan halaman panduan."""

    def __init__(
        self, repository: DemoRepository, ttl_seconds: int | None = None
    ) -> None:
        self.repository = repository
        self.ttl = ttl_seconds if ttl_seconds is not None else settings.demo_facts_ttl_seconds
        self._kunci = threading.Lock()
        self._tersimpan: DemoFacts | None = None
        self._diambil_pada = 0.0

    def collect(self, refresh: bool = False) -> DemoFacts:
        """Ambil data acuan, memakai cache selama masih segar.

        Data ini hanya berubah saat database di-seed ulang, sementara
        endpointnya dibaca setiap halaman panduan dibuka -- jadi menyimpannya
        sebentar menghemat query tanpa risiko menampilkan yang basi.

        Args:
            refresh: Paksa baca ulang dari database.

        Returns:
            Data acuan; available=False kalau database tidak bisa dibaca.
        """
        with self._kunci:
            if not refresh and self._masih_segar():
                return self._tersimpan  # type: ignore[return-value]

            fakta = self._baca()
            if fakta.available:
                self._tersimpan = fakta
                self._diambil_pada = time.monotonic()
            return fakta

    def _masih_segar(self) -> bool:
        return (
            self._tersimpan is not None
            and time.monotonic() - self._diambil_pada < self.ttl
        )

    def _baca(self) -> DemoFacts:
        """Baca seluruh data acuan dari repository.

        Kegagalan database sengaja tidak dilempar ke atas: halaman panduan
        adalah hal pertama yang dilihat pengunjung, dan kotak error merah di
        situ jauh lebih buruk daripada blok contoh yang disembunyikan.

        Returns:
            Data acuan, atau DemoFacts kosong dengan available=False.
        """
        try:
            ready = self.repository.variants_ready()
            restock = self.repository.variants_restock()
            orders = self.repository.orders_delivered()
            promos = self.repository.promotions()
        except (RuntimeError, ValueError) as exc:
            logger.error(f"Data acuan demo tidak bisa dibaca: {exc}", exc_info=True)
            return DemoFacts(available=False, generated_at=_sekarang())

        return DemoFacts(
            available=True,
            variants_ready=[_varian(baris) for baris in ready],
            variants_restock=[_varian(baris) for baris in restock],
            orders=[_pesanan(baris) for baris in orders],
            promotions=_promo_beragam(promos),
            generated_at=_sekarang(),
        )


def _sekarang() -> datetime:
    return datetime.now(timezone.utc)


def _varian(baris: dict[str, Any]) -> VariantFact:
    """Ubah satu baris view jadi VariantFact."""
    return VariantFact(
        variant_sku=str(baris.get("variant_sku", "")),
        product_sku=baris.get("product_sku"),
        product_name=str(baris.get("product_name", "")),
        size=baris.get("size"),
        color=baris.get("color"),
        available_quantity=baris.get("available_quantity"),
        next_restock_date=baris.get("next_restock_date"),
    )


def _pesanan(baris: dict[str, Any]) -> OrderFact:
    """Ubah satu baris view jadi OrderFact."""
    return OrderFact(
        order_number=str(baris.get("order_number", "")),
        phone_last4=str(baris.get("phone_last4", "")),
        order_status=str(baris.get("order_status", "")),
    )


def _promo_beragam(baris: list[dict[str, Any]]) -> list[PromoFact]:
    """Pilih promo yang statusnya berbeda-beda.

    Panduan sengaja menampilkan satu promo aktif, satu kedaluwarsa, dan satu
    yang belum mulai. Yang kedaluwarsa adalah yang paling menarik: menanyakannya
    memperlihatkan chatbot menolak menghormati promo, dan itu argumen kejujuran
    halaman panduan dalam satu klik.

    Args:
        baris: Baris promo mentah dari database.

    Returns:
        Sampai tiga promo dengan status berbeda.
    """
    per_status: dict[str, PromoFact] = {}

    for satu in baris:
        status = status_promo(satu.get("start_at"), satu.get("end_at"))
        if status in per_status:
            continue
        per_status[status] = PromoFact(
            code=str(satu.get("code", "")),
            name=str(satu.get("name", "")),
            status=status,  # type: ignore[arg-type]
            discount_label=_label_diskon(satu),
        )

    urutan = ["active", "expired", "scheduled"]
    return [per_status[status] for status in urutan if status in per_status]


def _label_diskon(baris: dict[str, Any]) -> str:
    """Susun label diskon yang bisa langsung ditampilkan.

    Args:
        baris: Baris promo mentah.

    Returns:
        Label singkat, mis. "25%" atau "Rp 50.000".
    """
    tipe = baris.get("discount_type")
    nilai = baris.get("discount_value")
    if nilai is None:
        return ""
    if tipe == "percentage":
        return f"{int(nilai)}%"
    return f"Rp {int(nilai):,}".replace(",", ".")
