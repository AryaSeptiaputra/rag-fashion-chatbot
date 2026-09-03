"""Definisi tool yang dipegang agent, plus instrumentasi audit.

Delapan tool di sini adalah satu-satunya jalan agent menyentuh data. Deskripsi
tiap tool sengaja menyebutkan kapan tool TIDAK boleh dipakai, bukan hanya kapan
dipakai: dengan permukaan tool selebar ini, batas negatif jauh lebih efektif
menekan salah pilih tool daripada deskripsi positif saja.
"""

import functools
import inspect
import time
from collections.abc import Callable
from typing import Any

from llama_index.core.tools import FunctionTool

from app.models.chat import ToolCallRecord
from app.repositories.base import RepositoryError
from app.services.catalog import CatalogService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.services.retrieval import FAQRetriever
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_MAX_SUMMARY_CHARS = 500


class ToolCallRecorder:
    """Mengumpulkan jejak tool call selama satu giliran percakapan.

    Instance dibuat baru tiap request supaya jejak antar percakapan tidak
    tercampur.
    """

    def __init__(self) -> None:
        self.records: list[ToolCallRecord] = []

    def wrap(self, func: Callable[..., str], tool_name: str) -> Callable[..., str]:
        """Bungkus fungsi tool supaya argumen, hasil, dan latensinya tercatat.

        functools.wraps dipertahankan karena LlamaIndex membangun schema
        parameter tool dari inspect.signature; tanpa itu LLM tidak akan tahu
        argumen apa yang bisa dikirim.

        Args:
            func: Fungsi tool asli.
            tool_name: Nama tool yang dilihat LLM.

        Returns:
            Fungsi dengan signature dan perilaku sama, hasilnya terekam ke recorder.
        """
        signature = inspect.signature(func)

        @functools.wraps(func)
        def _wrapped(*args: Any, **kwargs: Any) -> str:
            started = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                is_error = False
            except (ValueError, RuntimeError, KeyError, RepositoryError) as exc:
                logger.error(f"Tool {tool_name} gagal: {exc}", exc_info=True)
                result = (
                    f"Tool {tool_name} gagal dijalankan: {exc}. "
                    "Sampaikan ke pembeli bahwa data tidak bisa diambil saat ini."
                )
                is_error = True

            latency_ms = int((time.perf_counter() - started) * 1000)
            self.records.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=self._bind_arguments(signature, args, kwargs),
                    result_summary=result[:_MAX_SUMMARY_CHARS],
                    is_error=is_error,
                    latency_ms=latency_ms,
                )
            )
            logger.info(f"Tool {tool_name} selesai dalam {latency_ms} ms")
            return result

        return _wrapped

    @staticmethod
    def _bind_arguments(
        signature: inspect.Signature,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError:
            return dict(kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)

    def reset(self) -> None:
        """Kosongkan jejak yang sudah terkumpul."""
        self.records.clear()


def build_tools(
    faq_retriever: FAQRetriever,
    catalog_service: CatalogService,
    inventory_service: InventoryService,
    order_service: OrderService,
    escalate_handler: Callable[[str, str | None], str],
    recorder: ToolCallRecorder,
) -> list[FunctionTool]:
    """Rakit delapan tool agent lengkap dengan instrumentasi audit.

    Args:
        faq_retriever: Retriever dokumen FAQ dari ChromaDB.
        catalog_service: Service katalog produk dan promo.
        inventory_service: Service stok live dan rekomendasi ukuran.
        order_service: Service pelacakan pesanan.
        escalate_handler: Callback yang mencatat eskalasi ke admin.
        recorder: Perekam jejak tool untuk giliran percakapan ini.

    Returns:
        List FunctionTool siap diberikan ke agent.
    """

    def search_faq(query: str) -> str:
        """Cari jawaban di dokumen FAQ resmi brand.

        PAKAI untuk pertanyaan kebijakan dan prosedur: cara retur, tukar ukuran,
        garansi, lama pengiriman, ongkir, metode pembayaran, cara merawat bahan,
        jam operasional, dan kebijakan lain yang tertulis di FAQ.

        JANGAN PAKAI untuk mengecek stok, harga, atau data produk tertentu -
        data itu ada di database, bukan di FAQ.

        Args:
            query: Pertanyaan pembeli, tulis apa adanya dalam Bahasa Indonesia.

        Returns:
            Kutipan FAQ yang relevan beserta nama file dan halaman sumbernya.
        """
        nodes = faq_retriever.retrieve(query)
        return faq_retriever.format_for_llm(nodes)

    def search_products(
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        in_stock_only: bool = False,
    ) -> str:
        """Cari produk di katalog berdasarkan kata kunci, kategori, atau harga.

        PAKAI saat pembeli belum menyebut SKU: minta rekomendasi, bertanya
        "ada kaos apa aja", mencari berdasarkan warna/model/bahan, atau
        membatasi anggaran.

        Pertanyaan yang terasa terlalu luas ("ada produk apa aja?", "yang ready
        apa?") tetap dijawab dengan tool ini, bukan dengan pertanyaan balik:
        kosongkan keyword dan set in_stock_only=True untuk mendapat gambaran
        umum, tunjukkan hasilnya, baru tawarkan mempersempit pilihan.

        JANGAN PAKAI untuk mengecek sisa stok satu varian - itu tugas
        check_stock. Tool ini hanya memberi gambaran ketersediaan kasar.

        Args:
            keyword: Kata kunci bebas, mis. "hoodie oversize hitam".
                Kosongkan kalau pembeli belum menyebut kriteria apa pun.
            category: Nama kategori kalau pembeli menyebutnya, mis. "Kaos".
            max_price: Batas atas harga dalam rupiah kalau pembeli menyebut anggaran.
            in_stock_only: Set True kalau pembeli hanya mau produk yang stoknya ada.

        Returns:
            Daftar produk beserta SKU, rentang harga, warna, dan ukuran tersedia.
        """
        return catalog_service.search_products(
            keyword=keyword,
            category=category,
            max_price=max_price,
            in_stock_only=in_stock_only,
        )

    def get_product_detail(sku: str) -> str:
        """Ambil detail lengkap satu produk berdasarkan SKU.

        PAKAI setelah SKU diketahui, saat pembeli bertanya soal bahan, cara
        perawatan, potongan, koleksi, atau deskripsi produk.

        JANGAN PAKAI kalau SKU belum diketahui - cari dulu dengan search_products.

        Args:
            sku: SKU produk induk, mis. "TSH-0012". Bukan variant_sku.

        Returns:
            Detail produk: bahan, perawatan, potongan, harga, warna, ukuran, tag.
        """
        return catalog_service.get_product_detail(sku)

    def check_stock(sku: str, size: str | None = None, color: str | None = None) -> str:
        """Cek sisa stok LIVE sebuah produk atau varian.

        PAKAI setiap kali pembeli bertanya "ready ga", "masih ada", "sisa berapa",
        atau menanyakan ketersediaan ukuran/warna tertentu. WAJIB dipanggil ulang
        setiap kali ditanya, walaupun produk yang sama baru saja dicek di pesan
        sebelumnya, karena stok berubah tiap ada transaksi.

        JANGAN PAKAI untuk mencari produk baru - pakai search_products dulu.

        Args:
            sku: SKU produk induk atau variant_sku.
            size: Label ukuran kalau pembeli menyebutnya, mis. "L".
            color: Nama warna kalau pembeli menyebutnya, mis. "Hitam".

        Returns:
            Status stok per varian, termasuk jadwal restock kalau sedang habis.
        """
        return inventory_service.check_stock(sku=sku, size=size, color=color)

    def recommend_size(sku: str, chest_cm: float, waist_cm: float | None = None) -> str:
        """Rekomendasikan ukuran dari size chart berdasarkan ukuran badan pembeli.

        PAKAI hanya kalau pembeli menyebutkan ukuran badan dalam sentimeter
        (lingkar dada, dan opsional pinggang).

        JANGAN PAKAI kalau pembeli hanya menyebut berat badan atau tinggi tanpa
        lingkar dada - minta dulu lingkar dadanya. Jangan menebak konversinya.

        Args:
            sku: SKU produk induk yang ingin dibeli.
            chest_cm: Lingkar dada pembeli dalam sentimeter.
            waist_cm: Lingkar pinggang dalam sentimeter kalau disebutkan.

        Returns:
            Ukuran yang paling pas beserta rincian seluruh size chart produk.
        """
        return inventory_service.recommend_size(
            sku=sku, chest_cm=chest_cm, waist_cm=waist_cm
        )

    def track_order(order_number: str, phone_last4: str) -> str:
        """Lacak status pesanan setelah verifikasi identitas.

        PAKAI kalau pembeli menanyakan status pesanan atau nomor resi, DAN sudah
        memberikan nomor pesanan sekaligus 4 digit terakhir nomor HP-nya.

        JANGAN PAKAI kalau salah satu dari keduanya belum diberikan - minta dulu
        ke pembeli. Jangan pernah menebak atau mengarang nomor pesanan.

        Args:
            order_number: Nomor pesanan, mis. "INV-2026-000123".
            phone_last4: Tepat 4 digit terakhir nomor HP pemesan.

        Returns:
            Status pesanan, isi pesanan, kurir, dan nomor resi kalau sudah dikirim.
        """
        return order_service.track_order(
            order_number=order_number, phone_last4=phone_last4
        )

    def check_promotion(code: str | None = None, sku: str | None = None) -> str:
        """Cek promo yang benar-benar berlaku hari ini.

        PAKAI kalau pembeli bertanya "ada diskon?", menyebut kode promo, atau
        menanyakan promo untuk produk tertentu.

        JANGAN PAKAI untuk menghitung total belanja - tool ini hanya melaporkan
        promo yang aktif. Promo yang tidak muncul di hasil berarti tidak berlaku.

        Args:
            code: Kode promo yang disebut pembeli, mis. "NEWYEAR25".
            sku: SKU produk yang ingin dicek promonya.

        Returns:
            Daftar promo aktif beserta besaran diskon dan masa berlakunya.
        """
        return catalog_service.check_promotion(code=code, sku=sku)

    def escalate_to_human(reason: str, contact: str | None = None) -> str:
        """Teruskan percakapan ke admin manusia dan catat permintaannya.

        PAKAI SEKARANG JUGA, di giliran yang sama, kalau pembeli minta bicara
        dengan manusia atau admin, menyampaikan komplain serius, meminta
        pembatalan atau perubahan pesanan, atau bertanya hal di luar jangkauan
        tool lain (mis. lowongan kerja, kerja sama, keluhan layanan).

        JANGAN menanyakan detail tambahan ke pembeli sebelum memanggil tool ini.
        Isi 'reason' dengan kalimat pembeli apa adanya kalau kamu belum punya
        ringkasan yang lebih baik -- admin bisa membaca sisanya dari riwayat chat.
        Menunda pemanggilan demi mengumpulkan detail membuat permintaan pembeli
        TIDAK PERNAH tercatat.

        JANGAN PAKAI untuk pertanyaan yang jelas bisa dijawab tool lain, seperti
        stok, harga, ukuran, promo, atau status pesanan.

        Args:
            reason: Kebutuhan pembeli. Boleh kalimat aslinya apa adanya.
            contact: Kontak yang ditinggalkan pembeli kalau ada; boleh dikosongkan.

        Returns:
            Konfirmasi bahwa permintaan sudah tercatat dan diteruskan ke admin.
        """
        return escalate_handler(reason, contact)

    functions: list[Callable[..., str]] = [
        search_faq,
        search_products,
        get_product_detail,
        check_stock,
        recommend_size,
        track_order,
        check_promotion,
        escalate_to_human,
    ]

    return [
        FunctionTool.from_defaults(
            fn=recorder.wrap(func, func.__name__),
            name=func.__name__,
            description=func.__doc__ or "",
        )
        for func in functions
    ]
