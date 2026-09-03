"""Test OrderService: gerbang verifikasi identitas dan formatting status pesanan."""

from app.repositories.sales import SalesRepository
from app.services.order import OrderService
from tests.conftest import FakeSupabaseClient

DELIVERED_ORDER = {
    "order_number": "INV-2026-000006",
    "order_status": "delivered",
    "ordered_at": "2026-08-01T10:00:00+00:00",
    "total": 268000,
    "items": ["Kaos Ashen (L/Hitam) x1"],
    "item_count": 1,
    "courier": "JNE",
    "tracking_number": "123456789012",
    "shipment_status": "delivered",
    "shipped_at": "2026-08-02T09:00:00+00:00",
    "delivered_at": "2026-08-05T14:00:00+00:00",
    "return_status": None,
}


def build_service(rows: list[dict[str, object]] | None = None) -> OrderService:
    """Rakit OrderService di atas client Supabase palsu."""
    client = FakeSupabaseClient(rpc_rows={"track_order": rows or []})
    return OrderService(SalesRepository(client))  # type: ignore[arg-type]


def test_track_order_requires_four_digit_verification() -> None:
    service = build_service(rows=[DELIVERED_ORDER])

    result = service.track_order("INV-2026-000006", phone_last4="")

    assert "Verifikasi belum lengkap" in result
    assert "INV-2026-000006" not in result


def test_track_order_rejects_malformed_phone_digits() -> None:
    service = build_service(rows=[DELIVERED_ORDER])

    result = service.track_order("INV-2026-000006", phone_last4="12ab")

    assert "Verifikasi belum lengkap" in result


def test_track_order_returns_status_after_successful_verification() -> None:
    service = build_service(rows=[DELIVERED_ORDER])

    result = service.track_order("INV-2026-000006", phone_last4="1234")

    assert "sudah diterima" in result
    assert "123456789012" in result
    assert "Rp268.000" in result


def test_track_order_reports_no_match_without_guessing() -> None:
    service = build_service(rows=[])

    result = service.track_order("INV-2026-999999", phone_last4="0000")

    assert "Tidak ada pesanan" in result
    assert "Jangan menebak" in result


def test_track_order_states_missing_shipment_data() -> None:
    pending = {**DELIVERED_ORDER, "order_status": "paid", "shipment_status": None}
    service = build_service(rows=[pending])

    result = service.track_order("INV-2026-000006", phone_last4="1234")

    assert "belum ada data pengiriman" in result
