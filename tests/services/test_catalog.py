"""Test CatalogService: formatting katalog, promo aktif, dan penanganan hasil kosong."""

from app.repositories.catalog import CatalogRepository
from app.repositories.sales import SalesRepository
from app.services.catalog import CatalogService, format_rupiah
from tests.conftest import FakeSupabaseClient

PRODUCT_ROW = {
    "sku": "KAO-0001",
    "name": "Kaos Ashen",
    "category": "Kaos",
    "collection": "Urban Basics",
    "fit_type": "regular",
    "material": "Cotton Combed 30s",
    "min_price": 119000,
    "max_price": 129000,
    "available_colors": ["Hitam", "Navy"],
    "available_sizes": ["M", "L"],
    "total_available": 24,
    "relevance": 0.8,
}

DETAIL_ROW = {
    **PRODUCT_ROW,
    "description": "Kaos harian potongan regular.",
    "care_instructions": "Cuci terbalik, jemur di tempat teduh.",
    "gender": "unisex",
    "season": "all-season",
    "base_price": 119000,
    "variant_count": 8,
    "tags": ["bestseller"],
    "is_active": True,
}

ACTIVE_PROMO = {
    "promotion_id": "p1",
    "code": "HEMAT50K",
    "name": "Potongan 50 Ribu",
    "discount_type": "fixed",
    "discount_value": 50000,
    "min_purchase": 300000,
    "start_at": "2026-08-01T00:00:00+00:00",
    "end_at": "2026-09-30T00:00:00+00:00",
    "product_skus": [],
    "product_names": [],
    "applies_to_all": True,
}


def build_service(
    search_rows: list[dict[str, object]] | None = None,
    catalog_rows: list[dict[str, object]] | None = None,
    promo_rows: list[dict[str, object]] | None = None,
) -> CatalogService:
    """Rakit CatalogService di atas client Supabase palsu."""
    client = FakeSupabaseClient(
        table_rows={
            "v_product_catalog": catalog_rows or [],
            "v_active_promotions": promo_rows or [],
        },
        rpc_rows={"search_products": search_rows or []},
    )
    return CatalogService(
        CatalogRepository(client),  # type: ignore[arg-type]
        SalesRepository(client),  # type: ignore[arg-type]
    )


def test_format_rupiah_uses_indonesian_thousand_separator() -> None:
    assert format_rupiah(1_250_000) == "Rp1.250.000"


def test_search_products_lists_sku_price_and_stock() -> None:
    service = build_service(search_rows=[PRODUCT_ROW])

    result = service.search_products(keyword="kaos")

    assert "Ditemukan 1 produk" in result
    assert "KAO-0001" in result
    assert "Rp119.000-Rp129.000" in result
    assert "stok 24 pcs" in result


def test_search_products_states_not_found_explicitly() -> None:
    service = build_service(search_rows=[])

    result = service.search_products(keyword="jas hujan")

    assert "Tidak ditemukan produk" in result
    assert "Jangan mengarang produk lain" in result


def test_get_product_detail_includes_material_and_care() -> None:
    service = build_service(catalog_rows=[DETAIL_ROW])

    result = service.get_product_detail("KAO-0001")

    assert "Cotton Combed 30s" in result
    assert "jemur di tempat teduh" in result


def test_get_product_detail_rejects_unknown_sku() -> None:
    service = build_service(catalog_rows=[])

    result = service.get_product_detail("ZZZ-9999")

    assert "tidak ada di katalog" in result


def test_check_promotion_reports_active_promo() -> None:
    service = build_service(promo_rows=[ACTIVE_PROMO])

    result = service.check_promotion(code="HEMAT50K")

    assert "potongan Rp50.000" in result
    assert "minimum belanja Rp300.000" in result


def test_check_promotion_refuses_unknown_code() -> None:
    service = build_service(promo_rows=[])

    result = service.check_promotion(code="DISKON999")

    assert "tidak berlaku saat ini" in result
    assert "Jangan menjanjikan diskon" in result


def test_check_promotion_filters_by_sku() -> None:
    limited = {
        **ACTIVE_PROMO,
        "code": "KAOSHEMAT",
        "applies_to_all": False,
        "product_skus": ["KAO-0001"],
        "product_names": ["Kaos Ashen"],
    }
    service = build_service(promo_rows=[limited])

    covered = service.check_promotion(sku="KAO-0001")
    uncovered = service.check_promotion(sku="HOO-0006")

    assert "KAOSHEMAT" in covered
    assert "Tidak ada promo aktif" in uncovered
