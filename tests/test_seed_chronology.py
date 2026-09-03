"""Guard konsistensi kronologis data seed penjualan.

Regresi yang dijaga: tanggal pesanan, pengiriman, dan penerimaan pernah
dibangkitkan sendiri-sendiri, sehingga 15% pesanan tercatat dikirim sebelum
dipesan -- ada yang mundur 17 hari. Untuk project portofolio, data seperti itu
langsung terlihat oleh siapa pun yang membuka tabel pesanan.

Test ini menjalankan seed_sales sungguhan di atas client Supabase palsu, jadi
tidak butuh jaringan maupun kredensial.
"""

import importlib.util
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from faker import Faker

from app.config import PROJECT_ROOT

SEED = 42


def load_seed_module() -> ModuleType:
    """Muat scripts/seed_database.py sebagai module.

    Direktori scripts/ sengaja bukan package (isinya entry point, bukan
    library), jadi module-nya dimuat lewat path.

    Returns:
        Module seed_database yang sudah dieksekusi.
    """
    path = PROJECT_ROOT / "scripts" / "seed_database.py"
    spec = importlib.util.spec_from_file_location("seed_database_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingQuery:
    """Query builder palsu yang merekam insert dan mengembalikan baris ber-id."""

    def __init__(self, table: str, sink: dict[str, list[dict[str, Any]]]) -> None:
        self.table = table
        self.sink = sink
        self.rows: list[dict[str, Any]] = []

    def insert(self, payload: Any) -> "RecordingQuery":
        rows = payload if isinstance(payload, list) else [payload]
        self.rows = [{"id": str(uuid.uuid4()), **row} for row in rows]
        self.sink.setdefault(self.table, []).extend(self.rows)
        return self

    def select(self, *_args: Any, **_kwargs: Any) -> "RecordingQuery":
        return self

    def delete(self) -> "RecordingQuery":
        return self

    def neq(self, *_args: Any) -> "RecordingQuery":
        return self

    def eq(self, *_args: Any) -> "RecordingQuery":
        return self

    def gt(self, *_args: Any) -> "RecordingQuery":
        return self

    def limit(self, *_args: Any) -> "RecordingQuery":
        return self

    @property
    def not_(self) -> "RecordingQuery":
        return self

    def is_(self, *_args: Any) -> "RecordingQuery":
        return self

    def execute(self) -> Any:
        rows = self.rows

        class Response:
            data = rows

        return Response()


class RecordingClient:
    """Client Supabase palsu yang menyimpan seluruh baris hasil insert."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> RecordingQuery:
        return RecordingQuery(name, self.tables)


@pytest.fixture(scope="module")
def seeded() -> dict[str, list[dict[str, Any]]]:
    """Jalankan seed_sales sekali dan kembalikan seluruh baris yang dihasilkan."""
    seed_module = load_seed_module()

    Faker.seed(SEED)
    random.seed(SEED)
    client = RecordingClient()

    variants = [{"id": f"var-{index}"} for index in range(40)]
    promotions = [{"id": "promo-1", "code": "HEMAT50K"}]

    seed_module.seed_sales(
        client, variants, promotions, customer_count=10, order_count=120
    )
    return client.tables


def parse(value: str) -> datetime:
    """Ubah timestamp ISO jadi datetime."""
    return datetime.fromisoformat(value)


def order_dates_by_id(seeded: dict[str, list[dict[str, Any]]]) -> dict[str, datetime]:
    """Petakan id pesanan ke tanggal pemesanannya."""
    return {row["id"]: parse(row["created_at"]) for row in seeded["orders"]}


def test_orders_and_shipments_were_generated(seeded) -> None:
    assert len(seeded["orders"]) == 120
    assert seeded["shipments"], "tidak ada pengiriman yang dibuat"


def test_shipment_never_precedes_its_order(seeded) -> None:
    ordered_at = order_dates_by_id(seeded)

    offenders = [
        row["order_id"]
        for row in seeded["shipments"]
        if row.get("shipped_at") and parse(row["shipped_at"]) < ordered_at[row["order_id"]]
    ]

    assert not offenders, f"{len(offenders)} pengiriman mendahului tanggal pesanan"


def test_delivery_never_precedes_shipment(seeded) -> None:
    offenders = [
        row["order_id"]
        for row in seeded["shipments"]
        if row.get("delivered_at")
        and parse(row["delivered_at"]) < parse(row["shipped_at"])
    ]

    assert not offenders, f"{len(offenders)} penerimaan mendahului pengiriman"


def test_no_date_lands_in_the_future(seeded) -> None:
    now = datetime.now(timezone.utc)

    future = [
        (row["order_id"], field)
        for row in seeded["shipments"]
        for field in ("shipped_at", "delivered_at")
        if row.get(field) and parse(row[field]) > now
    ]
    future += [
        (row["id"], "created_at")
        for row in seeded["orders"]
        if parse(row["created_at"]) > now
    ]

    assert not future, f"tanggal di masa depan: {future[:5]}"


def test_status_matches_order_age(seeded) -> None:
    # Pesanan hari ini tidak boleh berstatus delivered, dan pesanan berumur
    # empat bulan tidak boleh masih menunggu pembayaran.
    seed_module = load_seed_module()
    now = datetime.now(timezone.utc)

    mismatches: list[str] = []
    for row in seeded["orders"]:
        age_days = (now - parse(row["created_at"])).days
        low, high = seed_module.STATUS_AGE_RANGE_DAYS[row["status"]]
        if not low <= age_days <= high + 1:
            mismatches.append(f"{row['order_number']} {row['status']} umur {age_days}h")

    assert not mismatches, f"status tidak cocok umur: {mismatches[:5]}"


def test_only_shipped_or_delivered_orders_have_tracking_number(seeded) -> None:
    status_by_id = {row["id"]: row["status"] for row in seeded["orders"]}

    wrong = [
        row["order_id"]
        for row in seeded["shipments"]
        if row.get("tracking_number") and status_by_id[row["order_id"]] not in {"shipped", "delivered"}
    ]

    assert not wrong, "ada nomor resi pada pesanan yang belum dikirim"
