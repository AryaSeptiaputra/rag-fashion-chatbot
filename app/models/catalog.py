"""Schema data katalog produk dan promosi."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductSummary(BaseModel):
    """Ringkasan produk hasil pencarian katalog."""

    sku: str
    name: str
    category: str | None = None
    collection: str | None = None
    fit_type: str | None = None
    material: str | None = None
    min_price: Decimal
    max_price: Decimal
    available_colors: list[str] = Field(default_factory=list)
    available_sizes: list[str] = Field(default_factory=list)
    total_available: int = 0
    relevance: float | None = None


class ProductDetail(BaseModel):
    """Detail lengkap satu produk dari v_product_catalog."""

    sku: str
    name: str
    description: str = ""
    material: str = ""
    care_instructions: str = ""
    fit_type: str | None = None
    gender: str | None = None
    category: str | None = None
    collection: str | None = None
    season: str | None = None
    base_price: Decimal
    min_price: Decimal
    max_price: Decimal
    available_colors: list[str] = Field(default_factory=list)
    available_sizes: list[str] = Field(default_factory=list)
    total_available: int = 0
    variant_count: int = 0
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class Promotion(BaseModel):
    """Promo yang sedang berlaku."""

    code: str
    name: str
    discount_type: str
    discount_value: Decimal
    min_purchase: Decimal = Decimal(0)
    start_at: datetime
    end_at: datetime
    applies_to_all: bool = False
    product_skus: list[str] = Field(default_factory=list)
    product_names: list[str] = Field(default_factory=list)
