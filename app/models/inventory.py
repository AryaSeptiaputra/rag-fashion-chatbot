"""Schema data ketersediaan stok dan rekomendasi ukuran."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class VariantAvailability(BaseModel):
    """Ketersediaan stok live untuk satu varian produk."""

    variant_sku: str
    product_sku: str
    product_name: str
    size: str
    color: str
    price: Decimal
    available_quantity: int
    is_available: bool
    next_restock_date: date | None = None


class SizeRecommendation(BaseModel):
    """Satu baris kandidat ukuran hasil pencocokan size chart."""

    product_sku: str
    product_name: str
    fit_type: str
    size: str
    chest_cm: Decimal
    waist_cm: Decimal
    length_cm: Decimal
    fit_gap_cm: Decimal
    is_best_match: bool
