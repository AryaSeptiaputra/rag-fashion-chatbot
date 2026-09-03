"""Logika bisnis pelacakan pesanan, termasuk gerbang verifikasi identitas."""

import re

from app.models.order import OrderTracking
from app.repositories.sales import SalesRepository
from app.services.catalog import format_rupiah
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PHONE_LAST4_PATTERN = re.compile(r"^\d{4}$")

_STATUS_LABELS = {
    "pending": "menunggu pembayaran",
    "paid": "sudah dibayar",
    "processing": "sedang disiapkan",
    "shipped": "sudah dikirim",
    "delivered": "sudah diterima",
    "cancelled": "dibatalkan",
    "refunded": "sudah direfund",
}

_SHIPMENT_LABELS = {
    "preparing": "sedang dikemas",
    "picked_up": "sudah dijemput kurir",
    "in_transit": "dalam perjalanan",
    "out_for_delivery": "sedang diantar ke alamat",
    "delivered": "sudah sampai",
    "failed": "gagal dikirim",
    "returned": "dikembalikan ke pengirim",
}


class OrderService:
    """Pelacakan pesanan dengan verifikasi identitas wajib.

    Verifikasi ditegakkan dua lapis: format 4 digit divalidasi di sini, dan
    kecocokannya diperiksa di RPC track_order. Tanpa keduanya, tidak ada data
    pesanan yang keluar.
    """

    def __init__(self, sales_repository: SalesRepository) -> None:
        self.sales_repository = sales_repository

    def track_order(self, order_number: str, phone_last4: str) -> str:
        """Lacak pesanan dan format hasilnya untuk LLM.

        Args:
            order_number: Nomor pesanan dari pembeli.
            phone_last4: Empat digit terakhir nomor HP pemesan.

        Returns:
            Status pesanan terformat, pesan permintaan verifikasi, atau pesan
            eksplisit kalau data tidak cocok.
        """
        cleaned_phone = (phone_last4 or "").strip()
        if not _PHONE_LAST4_PATTERN.match(cleaned_phone):
            return (
                "Verifikasi belum lengkap. Minta pembeli menyebutkan 4 digit "
                "TERAKHIR nomor HP yang dipakai saat memesan. "
                "Jangan tampilkan data pesanan apa pun sebelum itu diberikan."
            )

        tracking = self.sales_repository.track_order(
            order_number=order_number, phone_last4=cleaned_phone
        )

        if tracking is None:
            logger.info(f"Verifikasi pesanan gagal untuk nomor {order_number!r}")
            return (
                f"Tidak ada pesanan dengan nomor '{order_number}' yang cocok "
                "dengan 4 digit HP tersebut. Nomor pesanan atau digit HP salah. "
                "Jangan menebak status pesanan."
            )

        return self._format_tracking(tracking)

    def _format_tracking(self, tracking: OrderTracking) -> str:
        status = _STATUS_LABELS.get(tracking.order_status, tracking.order_status)
        lines = [
            f"Pesanan {tracking.order_number}",
            f"Status: {status}",
            f"Tanggal pesan: {tracking.ordered_at:%d %B %Y}",
            f"Total: {format_rupiah(tracking.total)}",
            f"Isi ({tracking.item_count} pcs): {', '.join(tracking.items) or '-'}",
        ]

        if tracking.shipment_status:
            shipment = _SHIPMENT_LABELS.get(
                tracking.shipment_status, tracking.shipment_status
            )
            lines.append(f"Pengiriman: {shipment} via {tracking.courier or '-'}")
            if tracking.tracking_number:
                lines.append(f"Nomor resi: {tracking.tracking_number}")
            if tracking.shipped_at:
                lines.append(f"Dikirim pada: {tracking.shipped_at:%d %B %Y}")
            if tracking.delivered_at:
                lines.append(f"Diterima pada: {tracking.delivered_at:%d %B %Y}")
        else:
            lines.append("Pengiriman: belum ada data pengiriman untuk pesanan ini")

        if tracking.return_status:
            lines.append(f"Pengajuan retur: status {tracking.return_status}")

        return "\n".join(lines)
