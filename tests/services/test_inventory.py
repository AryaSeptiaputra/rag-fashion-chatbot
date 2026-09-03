"""Test InventoryService: formatting stok, kasus habis, dan rekomendasi ukuran."""

from app.repositories.inventory import InventoryRepository
from app.repositories.sizing import SizingRepository
from app.services.inventory import InventoryService
from tests.conftest import FakeSupabaseClient

READY_VARIANT = {
    "variant_sku": "KAO-0001-L-HIT",
    "product_sku": "KAO-0001",
    "product_name": "Kaos Ashen",
    "size": "L",
    "color": "Hitam",
    "price": 119000,
    "available_quantity": 12,
    "is_available": True,
    "next_restock_date": None,
}

EMPTY_VARIANT_WITH_RESTOCK = {
    "variant_sku": "KAO-0001-M-HIT",
    "product_sku": "KAO-0001",
    "product_name": "Kaos Ashen",
    "size": "M",
    "color": "Hitam",
    "price": 119000,
    "available_quantity": 0,
    "is_available": False,
    "next_restock_date": "2026-10-15",
}


def build_service(
    availability_rows: list[dict[str, object]] | None = None,
    sizing_rows: list[dict[str, object]] | None = None,
) -> InventoryService:
    """Rakit InventoryService di atas client Supabase palsu."""
    client = FakeSupabaseClient(
        rpc_rows={
            "check_availability": availability_rows or [],
            "recommend_size": sizing_rows or [],
        }
    )
    return InventoryService(
        InventoryRepository(client),  # type: ignore[arg-type]
        SizingRepository(client),  # type: ignore[arg-type]
    )


def test_check_stock_reports_quantity_for_available_variant() -> None:
    service = build_service(availability_rows=[READY_VARIANT])

    result = service.check_stock("KAO-0001", size="L")

    assert "TERSEDIA 12 pcs" in result
    assert "KAO-0001-L-HIT" in result
    assert "Rp119.000" in result


def test_check_stock_surfaces_restock_date_when_sold_out() -> None:
    service = build_service(availability_rows=[EMPTY_VARIANT_WITH_RESTOCK])

    result = service.check_stock("KAO-0001", size="M")

    assert "HABIS" in result
    assert "15 October 2026" in result


def test_check_stock_states_not_found_explicitly() -> None:
    service = build_service(availability_rows=[])

    result = service.check_stock("ZZZ-9999", size="XL", color="Emas")

    assert "tidak ada di database" in result
    assert "Jangan mengarang" in result


def test_check_stock_marks_all_variants_sold_out() -> None:
    service = build_service(
        availability_rows=[EMPTY_VARIANT_WITH_RESTOCK, {**EMPTY_VARIANT_WITH_RESTOCK, "size": "L"}]
    )

    result = service.check_stock("KAO-0001")

    assert result.startswith("SEMUA varian")


def test_recommend_size_picks_best_match() -> None:
    rows = [
        {
            "product_sku": "KAO-0001",
            "product_name": "Kaos Ashen",
            "fit_type": "regular",
            "size": "L",
            "chest_cm": 104,
            "waist_cm": 88,
            "length_cm": 72,
            "fit_gap_cm": 4,
            "is_best_match": True,
        },
        {
            "product_sku": "KAO-0001",
            "product_name": "Kaos Ashen",
            "fit_type": "regular",
            "size": "M",
            "chest_cm": 100,
            "waist_cm": 84,
            "length_cm": 70,
            "fit_gap_cm": 8,
            "is_best_match": False,
        },
    ]
    service = build_service(sizing_rows=rows)

    result = service.recommend_size("KAO-0001", chest_cm=100.0, waist_cm=90.0)

    assert "REKOMENDASI: ukuran L" in result
    assert "paling pas" in result


def test_recommend_size_refuses_to_guess_without_chart() -> None:
    service = build_service(sizing_rows=[])

    result = service.recommend_size("KAO-0001", chest_cm=96.0)

    assert "tidak punya size chart" in result
    assert "Jangan menebak ukuran" in result
