"""Validasi migrasi SQL dengan parser Postgres asli (libpg_query lewat pglast).

Migrasi dijalankan manual di Supabase SQL Editor, jadi tanpa test ini kesalahan
sintaks baru ketahuan saat sudah di depan database. Test ini juga menjaga agar
kolom yang dikembalikan view/RPC tetap cocok dengan model Pydantic yang
memvalidasinya di runtime.
"""

import re
from pathlib import Path

import pytest
from pglast import parse_sql
from pglast.parser import ParseError

from app.config import PROJECT_ROOT
from app.models.catalog import ProductDetail, ProductSummary, Promotion
from app.models.inventory import SizeRecommendation, VariantAvailability
from app.models.order import OrderTracking

MIGRATION_DIR = PROJECT_ROOT / "supabase" / "migrations"
MIGRATION_FILES = sorted(MIGRATION_DIR.glob("*.sql"))

EXPECTED_MIGRATIONS = [
    "001_extensions.sql",
    "002_catalog.sql",
    "003_inventory.sql",
    "004_sales.sql",
    "005_chatbot.sql",
    "006_views.sql",
    "007_functions.sql",
    "008_indexes_rls.sql",
]


def read_functions_sql() -> str:
    """Baca isi migrasi RPC."""
    return (MIGRATION_DIR / "007_functions.sql").read_text(encoding="utf-8")


def read_views_sql() -> str:
    """Baca isi migrasi view."""
    return (MIGRATION_DIR / "006_views.sql").read_text(encoding="utf-8")


def rpc_output_columns(function_name: str) -> set[str]:
    """Ambil nama kolom yang dideklarasikan RETURNS TABLE sebuah RPC.

    Args:
        function_name: Nama fungsi di migrasi 007.

    Returns:
        Himpunan nama kolom keluaran.
    """
    block = re.search(
        rf"create or replace function\s+{function_name}\s*\(.*?returns table \((.*?)\)\s*language",
        read_functions_sql(),
        flags=re.S,
    )
    assert block is not None, f"RPC {function_name} tidak ditemukan di migrasi"
    return {line.strip().split()[0] for line in block.group(1).split(",\n") if line.strip()}


def view_output_columns(view_name: str) -> set[str]:
    """Ambil nama kolom keluaran sebuah view.

    Args:
        view_name: Nama view di migrasi 006.

    Returns:
        Himpunan nama kolom, baik yang beralias maupun yang tidak.
    """
    block = re.search(
        rf"create or replace view {view_name} as\s*select(.*?)\nfrom ",
        read_views_sql(),
        flags=re.S,
    )
    assert block is not None, f"View {view_name} tidak ditemukan di migrasi"
    body = block.group(1)

    columns = set(re.findall(r"as\s+([a-z_]+)\s*(?:,|$)", body, flags=re.M))
    columns.update(name for _, name in re.findall(r"^\s{4}([a-z_]+)\.([a-z_]+),?\s*$", body, flags=re.M))
    return columns


def test_all_migrations_present() -> None:
    assert [path.name for path in MIGRATION_FILES] == EXPECTED_MIGRATIONS


@pytest.mark.parametrize("path", MIGRATION_FILES, ids=lambda p: p.name)
def test_migration_parses(path: Path) -> None:
    try:
        statements = parse_sql(path.read_text(encoding="utf-8"))
    except ParseError as exc:
        pytest.fail(f"{path.name} tidak bisa diparse: {exc}")
    assert statements, f"{path.name} tidak berisi statement apa pun"


@pytest.mark.parametrize(
    "function_name", ["search_products", "check_availability", "recommend_size", "track_order"]
)
def test_rpc_body_parses(function_name: str) -> None:
    # Body di dalam $$...$$ hanyalah string bagi parser luar, jadi harus
    # divalidasi terpisah.
    body = re.search(
        rf"create or replace function\s+{function_name}\b.*?as \$\$(.*?)\$\$;",
        read_functions_sql(),
        flags=re.S,
    )
    assert body is not None, f"Body RPC {function_name} tidak ditemukan"
    try:
        parse_sql(body.group(1))
    except ParseError as exc:
        pytest.fail(f"Body {function_name} tidak bisa diparse: {exc}")


@pytest.mark.parametrize(
    ("source_columns", "model"),
    [
        (lambda: rpc_output_columns("search_products"), ProductSummary),
        (lambda: rpc_output_columns("check_availability"), VariantAvailability),
        (lambda: rpc_output_columns("recommend_size"), SizeRecommendation),
        (lambda: rpc_output_columns("track_order"), OrderTracking),
        (lambda: view_output_columns("v_product_catalog"), ProductDetail),
        (lambda: view_output_columns("v_active_promotions"), Promotion),
    ],
    ids=[
        "search_products", "check_availability", "recommend_size",
        "track_order", "v_product_catalog", "v_active_promotions",
    ],
)
def test_model_fields_are_provided_by_schema(source_columns, model) -> None:
    required = {name for name, field in model.model_fields.items() if field.is_required()}
    missing = required - source_columns()
    assert not missing, f"{model.__name__} butuh kolom yang tidak disediakan skema: {sorted(missing)}"


def test_stock_aggregation_excludes_inactive_warehouses() -> None:
    # Regresi: w.is_active pernah ditaruh di ON milik LEFT JOIN, yang hanya
    # membuat kolom w bernilai NULL sementara stoknya tetap ikut terjumlah.
    views = read_views_sql()

    assert "left join warehouses w   on w.id = inv.warehouse_id\n" in views
    assert "when w.is_active" in views


def test_order_tracking_view_hides_personal_data() -> None:
    views = read_views_sql()
    block = re.search(r"create or replace view v_order_tracking as(.*?);", views, flags=re.S)
    assert block is not None
    body = block.group(1)

    assert "cust.email" not in body
    assert "right(cust.phone, 4)" in body
    assert "line1" not in body
