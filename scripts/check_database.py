"""Periksa kesiapan skema Supabase dari sisi aplikasi.

Berbeda dengan supabase/verify.sql yang dijalankan di SQL Editor, script ini
menguji lewat PostgREST -- jalur yang sama dengan yang dipakai aplikasi. Sebuah
objek bisa saja ada di database tapi belum terekspos ke PostgREST, dan hanya
pemeriksaan seperti ini yang menangkapnya.

Jalankan: python scripts/check_database.py
"""

import sys
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.dependencies import get_supabase_client
from app.utils.console import configure_console_encoding
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

TABLES: tuple[str, ...] = (
    "categories", "collections", "colors", "sizes", "size_charts",
    "size_chart_entries", "products", "product_variants", "product_images",
    "tags", "product_tags",
    "warehouses", "inventory", "inventory_movements", "restock_schedule",
    "customers", "addresses", "promotions", "promotion_products",
    "orders", "order_items", "shipments", "return_requests",
    "conversations", "messages", "message_tool_calls", "escalations",
    "unanswered_queries",
)

VIEWS: tuple[str, ...] = (
    "v_product_catalog",
    "v_variant_availability",
    "v_order_tracking",
    "v_active_promotions",
)

# Nama RPC beserta argumen aman yang tidak mengubah data.
RPCS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "search_products",
        {
            "p_keyword": "kaos",
            "p_category": None,
            "p_max_price": None,
            "p_in_stock_only": False,
            "p_limit": 1,
        },
    ),
    ("check_availability", {"p_sku": "KAO-0001", "p_size": None, "p_color": None}),
    ("recommend_size", {"p_sku": "KAO-0001", "p_chest_cm": 100, "p_waist_cm": None}),
    ("track_order", {"p_order_number": "INV-0000-000000", "p_phone_last4": "0000"}),
)


def count_rows(client: Client, relation: str) -> int | None:
    """Hitung baris sebuah tabel atau view.

    Args:
        client: Client Supabase.
        relation: Nama tabel atau view.

    Returns:
        Jumlah baris, atau None kalau relasi tidak terjangkau.
    """
    try:
        response = client.table(relation).select("*", count="exact").limit(1).execute()
    except APIError as exc:
        logger.error(f"{relation} tidak terjangkau: {exc.message}")
        return None
    return response.count if response.count is not None else len(response.data or [])


def call_rpc(client: Client, name: str, params: dict[str, Any]) -> int | None:
    """Panggil RPC dan kembalikan jumlah baris hasilnya.

    Args:
        client: Client Supabase.
        name: Nama fungsi.
        params: Argumen fungsi.

    Returns:
        Jumlah baris hasil, atau None kalau RPC gagal dipanggil.
    """
    try:
        response = client.rpc(name, params).execute()
    except APIError as exc:
        logger.error(f"RPC {name} gagal: {exc.message}")
        return None
    return len(response.data or [])


def check_tables(client: Client) -> tuple[int, list[str], dict[str, int]]:
    """Periksa keterjangkauan seluruh tabel.

    Args:
        client: Client Supabase.

    Returns:
        Tuple (jumlah tabel siap, daftar tabel bermasalah, jumlah baris per tabel).
    """
    ready = 0
    missing: list[str] = []
    counts: dict[str, int] = {}

    for table in TABLES:
        total = count_rows(client, table)
        if total is None:
            missing.append(table)
            continue
        ready += 1
        counts[table] = total

    return ready, missing, counts


def main() -> int:
    """Jalankan seluruh pemeriksaan dan cetak ringkasannya.

    Returns:
        0 kalau skema siap, 1 kalau ada yang belum terbentuk.
    """
    configure_console_encoding()

    try:
        client = get_supabase_client()
    except ValueError as exc:
        logger.error(f"Konfigurasi Supabase belum lengkap: {exc}")
        return 1

    print("Memeriksa skema lewat PostgREST...\n")

    tables_ready, tables_missing, counts = check_tables(client)
    print(f"Tabel   : {tables_ready}/{len(TABLES)} terjangkau")
    if tables_missing:
        print(f"          BELUM ADA: {', '.join(tables_missing)}")

    views_missing = [view for view in VIEWS if count_rows(client, view) is None]
    print(f"View    : {len(VIEWS) - len(views_missing)}/{len(VIEWS)} terjangkau")
    if views_missing:
        print(f"          BELUM ADA: {', '.join(views_missing)}")

    rpc_missing = [name for name, params in RPCS if call_rpc(client, name, params) is None]
    print(f"RPC     : {len(RPCS) - len(rpc_missing)}/{len(RPCS)} bisa dipanggil")
    if rpc_missing:
        print(f"          GAGAL: {', '.join(rpc_missing)}")

    schema_ready = not tables_missing and not views_missing and not rpc_missing

    total_rows = sum(counts.values())
    print(f"\nTotal baris data: {total_rows}")
    if total_rows == 0:
        print("Database masih kosong. Langkah berikutnya: python scripts/seed_database.py")
    else:
        print(
            f"  produk={counts.get('products', 0)} "
            f"varian={counts.get('product_variants', 0)} "
            f"pesanan={counts.get('orders', 0)} "
            f"percakapan={counts.get('conversations', 0)}"
        )

    if schema_ready:
        print("\nSKEMA SIAP.")
        return 0

    print("\nSKEMA BELUM LENGKAP. Jalankan ulang migrasi yang objeknya belum terbentuk.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
