"""Data acuan yang ditampilkan di halaman panduan demo.

Statusnya memakai kode mesin, bukan prosa Indonesia, karena halaman panduannya
dwibahasa dan frontend yang melokalkannya.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

StatusPromo = Literal["active", "expired", "scheduled"]


class VariantFact(BaseModel):
    """Satu varian produk yang bisa dicoba ditanyakan pengunjung."""

    variant_sku: str
    product_sku: str | None = None
    product_name: str
    size: str | None = None
    color: str | None = None
    available_quantity: int | None = None
    next_restock_date: date | None = None


class OrderFact(BaseModel):
    """Satu pesanan yang bisa dilacak pengunjung.

    Nomor pesanan dan empat digit HP dikirim berpasangan karena tool track_order
    memang menuntut keduanya; memberi salah satunya saja akan membuat percobaan
    pertama pengunjung gagal.
    """

    order_number: str
    phone_last4: str
    order_status: str


class PromoFact(BaseModel):
    """Satu kode promo beserta statusnya."""

    code: str
    name: str
    status: StatusPromo
    discount_label: str


class DemoFacts(BaseModel):
    """Seluruh data acuan untuk satu kali render halaman panduan."""

    available: bool = True
    variants_ready: list[VariantFact] = Field(default_factory=list)
    variants_restock: list[VariantFact] = Field(default_factory=list)
    orders: list[OrderFact] = Field(default_factory=list)
    promotions: list[PromoFact] = Field(default_factory=list)
    generated_at: datetime | None = None
