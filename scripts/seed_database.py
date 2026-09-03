"""Isi Supabase dengan data katalog, inventori, dan penjualan yang realistis.

Seed dikunci (Faker.seed / random.seed) supaya hasilnya reproducible; eval
harness bergantung pada SKU dan nomor pesanan yang stabil antar-jalankan.

Beberapa kasus tepi ditanam sengaja agar bisa diuji:
  - satu produk habis total tapi punya jadwal restock
  - satu produk nonaktif (tidak dijual lagi)
  - satu varian yang hanya ada di satu gudang
  - promo kedaluwarsa, promo aktif, dan promo yang belum mulai

Jalankan: python scripts/seed_database.py
Prasyarat: migrasi 001-008 sudah dijalankan di Supabase SQL Editor.
"""

import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from faker import Faker
from postgrest.exceptions import APIError
from supabase import Client

from app.dependencies import get_supabase_client
from app.utils.console import configure_console_encoding
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SEED = 42
BATCH_SIZE = 500

fake = Faker("id_ID")

COLORS: list[tuple[str, str]] = [
    ("Hitam", "#111111"),
    ("Putih", "#FAFAFA"),
    ("Navy", "#1B2A4A"),
    ("Abu Misty", "#9AA0A6"),
    ("Krem", "#E8DCC8"),
    ("Olive", "#5B6236"),
    ("Maroon", "#5C1F2B"),
    ("Mocha", "#6F5646"),
    ("Sage", "#A3B18A"),
    ("Denim", "#3E5C76"),
    ("Terracotta", "#B4634A"),
    ("Charcoal", "#36393B"),
]

SIZES: list[tuple[str, int]] = [
    ("XS", 1),
    ("S", 2),
    ("M", 3),
    ("L", 4),
    ("XL", 5),
    ("XXL", 6),
]

# (nama, slug, nama induk atau None)
CATEGORIES: list[tuple[str, str, str | None]] = [
    ("Atasan", "atasan", None),
    ("Bawahan", "bawahan", None),
    ("Outerwear", "outerwear", None),
    ("Kaos", "kaos", "Atasan"),
    ("Kemeja", "kemeja", "Atasan"),
    ("Celana", "celana", "Bawahan"),
    ("Hoodie", "hoodie", "Outerwear"),
    ("Jaket", "jaket", "Outerwear"),
]

COLLECTIONS: list[tuple[str, str, str, int, str]] = [
    ("Urban Basics", "urban-basics", "all-season", 2025, "2025-03-01"),
    ("Monsoon Drop", "monsoon-drop", "fall", 2025, "2025-09-15"),
    ("Daylight 2026", "daylight-2026", "summer", 2026, "2026-04-01"),
]

TAGS: list[str] = [
    "bestseller", "new arrival", "unisex", "cotton", "oversize",
    "limited", "everyday", "premium", "streetwear", "minimalis",
]

MATERIALS: list[str] = [
    "Cotton Combed 24s",
    "Cotton Combed 30s",
    "Fleece Cotton 280gsm",
    "French Terry 260gsm",
    "Oxford Cotton",
    "Twill Stretch",
    "Linen Blend",
    "Rayon Viscose",
]

CARE_INSTRUCTIONS: list[str] = [
    "Cuci dengan air dingin, jangan gunakan pemutih, setrika suhu sedang.",
    "Cuci terbalik, jemur di tempat teduh, hindari pengering mesin.",
    "Dry clean disarankan. Kalau dicuci sendiri, gunakan deterjen lembut.",
    "Cuci tangan atau mesin siklus lembut, jangan diperas terlalu kuat.",
]

# (tipe produk, kategori, potongan, harga dasar)
PRODUCT_TYPES: list[tuple[str, str, str, int]] = [
    ("Kaos", "Kaos", "regular", 119_000),
    ("Kaos Oversize", "Kaos", "oversize", 149_000),
    ("Kaos Boxy", "Kaos", "boxy", 139_000),
    ("Kemeja Flanel", "Kemeja", "regular", 249_000),
    ("Kemeja Oxford", "Kemeja", "slim", 279_000),
    ("Hoodie", "Hoodie", "oversize", 329_000),
    ("Crewneck", "Hoodie", "regular", 289_000),
    ("Jaket Coach", "Jaket", "regular", 399_000),
    ("Jaket Bomber", "Jaket", "regular", 449_000),
    ("Celana Cargo", "Celana", "regular", 299_000),
    ("Celana Chino", "Celana", "slim", 259_000),
    ("Celana Jogger", "Celana", "regular", 229_000),
]

PRODUCT_NAMES: list[str] = [
    "Ashen", "Noir", "Halcyon", "Drift", "Ember", "Solace", "Vantage",
    "Meridian", "Halton", "Corvus", "Lumen", "Origin", "Terra", "Nimbus",
    "Alder", "Basalt", "Cinder", "Dune", "Eclipse", "Fathom",
]

WAREHOUSES: list[tuple[str, str, str]] = [
    ("JKT", "Gudang Jakarta", "Jakarta"),
    ("BDG", "Gudang Bandung", "Bandung"),
    ("SBY", "Gudang Surabaya", "Surabaya"),
]

COURIERS: list[str] = ["JNE", "J&T Express", "SiCepat", "Anteraja", "Ninja Xpress"]

# Rentang umur pesanan (hari) yang masuk akal untuk tiap status. Umur pesanan
# diturunkan DARI statusnya, lalu tanggal pengiriman diturunkan dari tanggal
# pesanan. Tanpa rantai itu, ketiganya dibangkitkan sendiri-sendiri dan data
# bisa memuat pesanan yang dikirim sebelum dipesan.
STATUS_AGE_RANGE_DAYS: dict[str, tuple[int, int]] = {
    "pending": (0, 0),
    "paid": (1, 2),
    "processing": (2, 4),
    "shipped": (4, 8),
    "delivered": (9, 120),
    "cancelled": (3, 60),
}

# Jeda pengiriman, dihitung dari tanggal pesanan.
SHIP_DELAY_DAYS = (1, 2)
DELIVERY_DELAY_DAYS = (2, 5)

# Ukuran badan acuan per potongan, dalam sentimeter untuk ukuran M.
FIT_BASELINE: dict[str, tuple[float, float, float]] = {
    "slim": (94.0, 78.0, 68.0),
    "regular": (100.0, 84.0, 70.0),
    "boxy": (106.0, 92.0, 68.0),
    "oversize": (112.0, 98.0, 74.0),
}


def parse_args() -> argparse.Namespace:
    """Baca argumen command line.

    Returns:
        Namespace berisi jumlah produk dan pesanan yang dibuat.
    """
    parser = argparse.ArgumentParser(description="Seed database Supabase")
    parser.add_argument("--products", type=int, default=60, help="Jumlah produk")
    parser.add_argument("--orders", type=int, default=200, help="Jumlah pesanan")
    parser.add_argument("--customers", type=int, default=40, help="Jumlah pelanggan")
    return parser.parse_args()


def insert_rows(
    client: Client, table: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Sisipkan baris ke tabel secara berbatch dan kembalikan hasilnya.

    Args:
        client: Client Supabase.
        table: Nama tabel tujuan.
        rows: Baris yang akan disisipkan.

    Returns:
        Baris hasil insert lengkap dengan id yang di-generate database.

    Raises:
        RuntimeError: Kalau PostgREST menolak salah satu batch.
    """
    if not rows:
        return []

    inserted: list[dict[str, Any]] = []
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        try:
            response = client.table(table).insert(batch).execute()
        except APIError as exc:
            logger.error(f"Insert ke {table} gagal: {exc.message}", exc_info=True)
            raise RuntimeError(f"Seeding tabel {table} gagal") from exc
        inserted.extend(response.data or [])

    logger.info(f"Tabel {table}: {len(inserted)} baris")
    return inserted


def truncate_all(client: Client) -> None:
    """Kosongkan seluruh tabel data sebelum seeding ulang.

    Urutan penghapusan mengikuti arah foreign key supaya tidak melanggar
    constraint.

    Args:
        client: Client Supabase.
    """
    # PostgREST menolak DELETE tanpa filter, jadi tiap tabel butuh satu kolom
    # yang pasti ada. Tabel relasi many-to-many tidak punya kolom id.
    tables: list[tuple[str, str]] = [
        ("message_tool_calls", "id"),
        ("messages", "id"),
        ("unanswered_queries", "id"),
        ("escalations", "id"),
        ("conversations", "id"),
        ("return_requests", "id"),
        ("shipments", "id"),
        ("order_items", "id"),
        ("orders", "id"),
        ("addresses", "id"),
        ("customers", "id"),
        ("promotion_products", "promotion_id"),
        ("promotions", "id"),
        ("inventory_movements", "id"),
        ("restock_schedule", "id"),
        ("inventory", "id"),
        ("warehouses", "id"),
        ("product_tags", "product_id"),
        ("tags", "id"),
        ("product_images", "id"),
        ("product_variants", "id"),
        ("products", "id"),
        ("size_chart_entries", "id"),
        ("size_charts", "id"),
        ("sizes", "id"),
        ("colors", "id"),
        ("collections", "id"),
        ("categories", "id"),
    ]
    sentinel = "00000000-0000-0000-0000-000000000000"

    for table, key_column in tables:
        try:
            client.table(table).delete().neq(key_column, sentinel).execute()
        except APIError as exc:
            logger.warning(f"Gagal mengosongkan {table}: {exc.message}")
    logger.info("Seluruh tabel data dikosongkan")


def seed_reference_data(client: Client) -> dict[str, Any]:
    """Isi tabel referensi: warna, ukuran, kategori, koleksi, size chart, tag.

    Args:
        client: Client Supabase.

    Returns:
        Dict berisi hasil insert tiap tabel referensi.
    """
    colors = insert_rows(
        client,
        "colors",
        [{"name": name, "hex_code": hex_code} for name, hex_code in COLORS],
    )
    sizes = insert_rows(
        client,
        "sizes",
        [{"label": label, "sort_order": order} for label, order in SIZES],
    )

    parents = insert_rows(
        client,
        "categories",
        [
            {"name": name, "slug": slug, "sort_order": index}
            for index, (name, slug, parent) in enumerate(CATEGORIES)
            if parent is None
        ],
    )
    parent_by_name = {row["name"]: row["id"] for row in parents}
    children = insert_rows(
        client,
        "categories",
        [
            {
                "name": name,
                "slug": slug,
                "parent_id": parent_by_name[parent],
                "sort_order": index,
            }
            for index, (name, slug, parent) in enumerate(CATEGORIES)
            if parent is not None
        ],
    )
    categories = {row["name"]: row["id"] for row in parents + children}

    collections = insert_rows(
        client,
        "collections",
        [
            {
                "name": name,
                "slug": slug,
                "season": season,
                "year": year,
                "launch_date": launch,
                "is_active": True,
            }
            for name, slug, season, year, launch in COLLECTIONS
        ],
    )

    charts = insert_rows(
        client,
        "size_charts",
        [
            {"name": f"{fit.title()} Fit Unisex", "fit_type": fit, "gender": "unisex"}
            for fit in FIT_BASELINE
        ],
    )

    entries: list[dict[str, Any]] = []
    for chart in charts:
        chest_base, waist_base, length_base = FIT_BASELINE[chart["fit_type"]]
        for size in sizes:
            step = size["sort_order"] - 3  # M dijadikan titik nol
            entries.append(
                {
                    "size_chart_id": chart["id"],
                    "size_id": size["id"],
                    "chest_cm": round(chest_base + step * 4, 1),
                    "waist_cm": round(waist_base + step * 4, 1),
                    "length_cm": round(length_base + step * 2, 1),
                    "shoulder_cm": round(chest_base / 2.4 + step * 1.5, 1),
                }
            )
    insert_rows(client, "size_chart_entries", entries)

    tags = insert_rows(
        client,
        "tags",
        [{"name": name, "slug": name.replace(" ", "-")} for name in TAGS],
    )

    return {
        "colors": colors,
        "sizes": sizes,
        "categories": categories,
        "collections": collections,
        "charts": {chart["fit_type"]: chart["id"] for chart in charts},
        "tags": tags,
    }


def seed_products(
    client: Client, reference: dict[str, Any], product_count: int
) -> list[dict[str, Any]]:
    """Isi tabel products beserta tag-nya.

    Args:
        client: Client Supabase.
        reference: Hasil seed_reference_data.
        product_count: Jumlah produk yang dibuat.

    Returns:
        Baris produk hasil insert.
    """
    rows: list[dict[str, Any]] = []
    for index in range(product_count):
        type_name, category, fit, base_price = PRODUCT_TYPES[index % len(PRODUCT_TYPES)]
        label = PRODUCT_NAMES[index % len(PRODUCT_NAMES)]
        suffix = index // len(PRODUCT_NAMES)
        name = f"{type_name} {label}" + (f" {suffix + 1}" if suffix else "")
        collection = reference["collections"][index % len(reference["collections"])]

        # Produk terakhir sengaja dinonaktifkan sebagai kasus tepi.
        is_active = index != product_count - 1

        rows.append(
            {
                "sku": f"{type_name[:3].upper()}-{index + 1:04d}",
                "name": name,
                "description": (
                    f"{name} dengan potongan {fit} yang nyaman dipakai harian. "
                    f"Dibuat dari {MATERIALS[index % len(MATERIALS)]} "
                    "dengan jahitan rapi dan warna yang tidak mudah pudar."
                ),
                "category_id": reference["categories"][category],
                "collection_id": collection["id"],
                "size_chart_id": reference["charts"][fit],
                "base_price": base_price + (index % 5) * 10_000,
                "material": MATERIALS[index % len(MATERIALS)],
                "care_instructions": CARE_INSTRUCTIONS[index % len(CARE_INSTRUCTIONS)],
                "fit_type": fit,
                "gender": "unisex",
                "is_active": is_active,
            }
        )

    products = insert_rows(client, "products", rows)

    tag_links: list[dict[str, Any]] = []
    for product in products:
        for tag in random.sample(reference["tags"], k=random.randint(1, 3)):
            tag_links.append({"product_id": product["id"], "tag_id": tag["id"]})
    insert_rows(client, "product_tags", tag_links)

    images = [
        {
            "product_id": product["id"],
            "url": f"https://cdn.brand.example/products/{product['sku'].lower()}.jpg",
            "is_primary": True,
            "sort_order": 0,
        }
        for product in products
    ]
    insert_rows(client, "product_images", images)

    return products


def seed_variants(
    client: Client, products: list[dict[str, Any]], reference: dict[str, Any]
) -> list[dict[str, Any]]:
    """Isi tabel product_variants: kombinasi ukuran dan warna per produk.

    Args:
        client: Client Supabase.
        products: Produk hasil seed_products.
        reference: Hasil seed_reference_data.

    Returns:
        Baris varian hasil insert.
    """
    size_by_label = {size["label"]: size for size in reference["sizes"]}
    rows: list[dict[str, Any]] = []

    for product in products:
        chosen_sizes = ["S", "M", "L", "XL"]
        chosen_colors = random.sample(reference["colors"], k=random.randint(2, 3))
        for size_label in chosen_sizes:
            size = size_by_label[size_label]
            for color in chosen_colors:
                rows.append(
                    {
                        "product_id": product["id"],
                        "size_id": size["id"],
                        "color_id": color["id"],
                        "variant_sku": (
                            f"{product['sku']}-{size_label}-"
                            f"{color['name'][:3].upper()}"
                        ),
                        "weight_grams": random.choice([250, 300, 350, 450, 600]),
                        "is_active": True,
                    }
                )

    return insert_rows(client, "product_variants", rows)


def seed_inventory(
    client: Client, variants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Isi gudang, stok per varian, jadwal restock, dan mutasi stok.

    Args:
        client: Client Supabase.
        variants: Varian hasil seed_variants.

    Returns:
        Baris gudang hasil insert.
    """
    warehouses = insert_rows(
        client,
        "warehouses",
        [
            {"code": code, "name": name, "city": city, "is_active": True}
            for code, name, city in WAREHOUSES
        ],
    )

    inventory_rows: list[dict[str, Any]] = []
    movement_rows: list[dict[str, Any]] = []
    out_of_stock: list[dict[str, Any]] = []

    for index, variant in enumerate(variants):
        # 12% varian sengaja dibuat habis total supaya jalur "stok habis +
        # jadwal restock" bisa diuji. Varian ke-7 hanya ada di satu gudang.
        is_out_of_stock = index % 8 == 3
        single_warehouse = index % 37 == 7

        targets = warehouses[:1] if single_warehouse else warehouses
        total_stock = 0

        for warehouse in targets:
            quantity = 0 if is_out_of_stock else random.randint(0, 24)
            reserved = random.randint(0, min(2, quantity)) if quantity else 0
            total_stock += quantity - reserved

            inventory_rows.append(
                {
                    "variant_id": variant["id"],
                    "warehouse_id": warehouse["id"],
                    "quantity_on_hand": quantity,
                    "quantity_reserved": reserved,
                }
            )
            if quantity:
                movement_rows.append(
                    {
                        "variant_id": variant["id"],
                        "warehouse_id": warehouse["id"],
                        "movement_type": "restock",
                        "quantity": quantity,
                        "reference": "seed-initial",
                    }
                )

        if total_stock <= 0:
            out_of_stock.append(variant)

    insert_rows(client, "inventory", inventory_rows)
    insert_rows(client, "inventory_movements", movement_rows)

    restock_rows = [
        {
            "variant_id": variant["id"],
            "expected_date": (date.today() + timedelta(days=7 + (index % 21))).isoformat(),
            "expected_quantity": random.choice([20, 30, 50]),
            "status": "scheduled",
            "note": "Restock batch produksi berikutnya",
        }
        for index, variant in enumerate(out_of_stock)
    ]
    insert_rows(client, "restock_schedule", restock_rows)

    return warehouses


def seed_promotions(
    client: Client, products: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Isi promo: satu kedaluwarsa, tiga aktif, satu belum mulai.

    Args:
        client: Client Supabase.
        products: Produk hasil seed_products.

    Returns:
        Baris promo hasil insert.
    """
    now = datetime.now(timezone.utc)
    definitions = [
        ("NEWYEAR25", "Diskon Tahun Baru", "percentage", 25, 0, -90, -60),
        ("HEMAT50K", "Potongan 50 Ribu", "fixed", 50_000, 300_000, -10, 20),
        ("KAOSHEMAT", "Diskon Kaos Pilihan", "percentage", 15, 0, -5, 25),
        ("GRATISONGKIR", "Gratis Ongkir Nasional", "fixed", 25_000, 150_000, -30, 45),
        ("RAMADAN26", "Promo Ramadan", "percentage", 30, 200_000, 30, 75),
    ]

    rows = [
        {
            "code": code,
            "name": name,
            "discount_type": discount_type,
            "discount_value": value,
            "min_purchase": minimum,
            "start_at": (now + timedelta(days=start)).isoformat(),
            "end_at": (now + timedelta(days=end)).isoformat(),
            "is_active": True,
        }
        for code, name, discount_type, value, minimum, start, end in definitions
    ]
    promotions = insert_rows(client, "promotions", rows)

    # Hanya KAOSHEMAT yang dibatasi ke produk tertentu; sisanya berlaku umum.
    limited = next(promo for promo in promotions if promo["code"] == "KAOSHEMAT")
    kaos_products = [p for p in products if p["sku"].startswith("KAO")][:8]
    insert_rows(
        client,
        "promotion_products",
        [
            {"promotion_id": limited["id"], "product_id": product["id"]}
            for product in kaos_products
        ],
    )

    return promotions


def seed_sales(
    client: Client,
    variants: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    customer_count: int,
    order_count: int,
) -> None:
    """Isi pelanggan, alamat, pesanan, item, pengiriman, dan retur.

    Args:
        client: Client Supabase.
        variants: Varian hasil seed_variants.
        promotions: Promo hasil seed_promotions.
        customer_count: Jumlah pelanggan.
        order_count: Jumlah pesanan.
    """
    customers = insert_rows(
        client,
        "customers",
        [
            {
                "full_name": fake.name(),
                "email": f"pembeli{index + 1}@example.com",
                "phone": f"08{random.randint(1000000000, 9999999999)}",
            }
            for index in range(customer_count)
        ],
    )

    addresses = insert_rows(
        client,
        "addresses",
        [
            {
                "customer_id": customer["id"],
                "recipient": customer["full_name"],
                "phone": customer["phone"],
                "line1": fake.street_address(),
                "city": fake.city(),
                "province": fake.administrative_unit(),
                "postal_code": fake.postcode(),
                "is_default": True,
            }
            for customer in customers
        ],
    )
    address_by_customer = {row["customer_id"]: row["id"] for row in addresses}

    statuses = [
        "pending", "paid", "processing", "shipped", "shipped",
        "delivered", "delivered", "delivered", "cancelled",
    ]
    now = datetime.now(timezone.utc)

    order_rows: list[dict[str, Any]] = []
    order_plans: list[dict[str, Any]] = []

    for index in range(order_count):
        customer = customers[index % len(customers)]
        status = statuses[index % len(statuses)]
        age_min, age_max = STATUS_AGE_RANGE_DAYS[status]
        ordered_at = now - timedelta(
            days=random.randint(age_min, age_max), hours=random.randint(0, 23)
        )
        picked = random.sample(variants, k=random.randint(1, 3))

        items = [
            {"variant": variant, "quantity": random.randint(1, 2)}
            for variant in picked
        ]
        subtotal = sum(
            item["quantity"] * random.choice([119_000, 149_000, 249_000, 329_000])
            for item in items
        )
        promotion = random.choice(promotions) if index % 4 == 0 else None
        discount = int(subtotal * 0.15) if promotion else 0
        shipping = random.choice([0, 15_000, 22_000, 30_000])

        order_rows.append(
            {
                "order_number": f"INV-2026-{index + 1:06d}",
                "customer_id": customer["id"],
                "address_id": address_by_customer[customer["id"]],
                "promotion_id": promotion["id"] if promotion else None,
                "status": status,
                "subtotal": subtotal,
                "discount_amount": discount,
                "shipping_cost": shipping,
                "total": subtotal - discount + shipping,
                "created_at": ordered_at.isoformat(),
            }
        )
        order_plans.append(
            {"status": status, "items": items, "ordered_at": ordered_at}
        )

    orders = insert_rows(client, "orders", order_rows)

    item_rows: list[dict[str, Any]] = []
    shipment_rows: list[dict[str, Any]] = []
    return_rows: list[dict[str, Any]] = []

    for order, plan in zip(orders, order_plans, strict=True):
        for item in plan["items"]:
            item_rows.append(
                {
                    "order_id": order["id"],
                    "variant_id": item["variant"]["id"],
                    "quantity": item["quantity"],
                    "unit_price": random.choice([119_000, 149_000, 249_000, 329_000]),
                }
            )

        if plan["status"] in {"shipped", "delivered"}:
            shipped_at = plan["ordered_at"] + timedelta(
                days=random.randint(*SHIP_DELAY_DAYS), hours=random.randint(1, 20)
            )
            is_delivered = plan["status"] == "delivered"
            delivered_at = (
                shipped_at + timedelta(days=random.randint(*DELIVERY_DELAY_DAYS))
                if is_delivered
                else None
            )
            shipment_rows.append(
                {
                    "order_id": order["id"],
                    "courier": random.choice(COURIERS),
                    "tracking_number": f"{random.randint(10**11, 10**12 - 1)}",
                    "status": "delivered" if is_delivered else "in_transit",
                    "shipped_at": shipped_at.isoformat(),
                    "delivered_at": delivered_at.isoformat() if delivered_at else None,
                }
            )
        elif plan["status"] == "processing":
            shipment_rows.append(
                {
                    "order_id": order["id"],
                    "courier": random.choice(COURIERS),
                    "status": "preparing",
                }
            )

        if plan["status"] == "delivered" and random.random() < 0.08:
            return_rows.append(
                {
                    "order_id": order["id"],
                    "reason": random.choice(
                        ["size_mismatch", "defective", "wrong_item", "changed_mind"]
                    ),
                    "description": "Diajukan lewat form retur.",
                    "status": random.choice(["requested", "approved", "refunded"]),
                }
            )

    insert_rows(client, "order_items", item_rows)
    insert_rows(client, "shipments", shipment_rows)
    insert_rows(client, "return_requests", return_rows)


def print_sample_facts(client: Client) -> None:
    """Cetak beberapa data acuan supaya eval dan uji manual punya pegangan.

    Args:
        client: Client Supabase.
    """
    try:
        in_stock = (
            client.table("v_variant_availability")
            .select("variant_sku, product_sku, product_name, size, color, available_quantity")
            .gt("available_quantity", 0)
            .limit(3)
            .execute()
        )
        out_of_stock = (
            client.table("v_variant_availability")
            .select("variant_sku, product_name, size, color, next_restock_date")
            .eq("available_quantity", 0)
            .not_.is_("next_restock_date", "null")
            .limit(2)
            .execute()
        )
        order = (
            client.table("v_order_tracking")
            .select("order_number, phone_last4, order_status")
            .eq("order_status", "delivered")
            .limit(2)
            .execute()
        )
    except APIError as exc:
        logger.warning(f"Gagal membaca data contoh: {exc.message}")
        return

    print("\nData acuan untuk pengujian:")
    for row in in_stock.data or []:
        print(
            f"  READY  {row['product_name']} | varian {row['variant_sku']} | "
            f"{row['size']}/{row['color']} | sisa {row['available_quantity']}"
        )
    for row in out_of_stock.data or []:
        print(
            f"  HABIS  {row['product_name']} | varian {row['variant_sku']} | "
            f"restock {row['next_restock_date']}"
        )
    for row in order.data or []:
        print(
            f"  ORDER  {row['order_number']} | 4 digit HP: {row['phone_last4']} | "
            f"status {row['order_status']}"
        )


def main() -> int:
    """Jalankan seluruh proses seeding.

    Returns:
        0 kalau berhasil, 1 kalau gagal.
    """
    configure_console_encoding()
    args = parse_args()

    Faker.seed(SEED)
    random.seed(SEED)

    try:
        client = get_supabase_client()
    except ValueError as exc:
        logger.error(f"Konfigurasi Supabase belum lengkap: {exc}")
        return 1

    try:
        truncate_all(client)
        reference = seed_reference_data(client)
        products = seed_products(client, reference, args.products)
        variants = seed_variants(client, products, reference)
        seed_inventory(client, variants)
        promotions = seed_promotions(client, products)
        seed_sales(client, variants, promotions, args.customers, args.orders)
    except RuntimeError as exc:
        logger.error(f"Seeding dihentikan: {exc}")
        logger.error("Pastikan migrasi 001-008 sudah dijalankan di Supabase.")
        return 1

    print(
        f"\nSeeded {len(products)} products, {len(variants)} variants, "
        f"{args.orders} orders, {len(promotions)} promotions"
    )
    print_sample_facts(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
