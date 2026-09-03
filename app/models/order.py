"""Schema data pelacakan pesanan."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderTracking(BaseModel):
    """Status pesanan yang boleh disampaikan ke pembeli.

    Sengaja tidak memuat email, alamat, atau nomor HP utuh.
    """

    order_number: str
    order_status: str
    ordered_at: datetime
    total: Decimal
    items: list[str] = Field(default_factory=list)
    item_count: int = 0
    courier: str | None = None
    tracking_number: str | None = None
    shipment_status: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    return_status: str | None = None
