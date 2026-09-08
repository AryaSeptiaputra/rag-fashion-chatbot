"""Jawaban contoh untuk mode demo tanpa saldo API.

Isinya diambil dari dokumen GAYA.ID yang sungguhan diindeks, jadi angkanya
benar dan kutipannya menunjuk ke halaman yang memang memuatnya. Yang palsu di
sini hanya satu: jawabannya tidak disusun model, melainkan ditulis di muka.
Karena itu setiap balasan stub selalu ditandai di respons API dan diberi pita
di UI -- angka yang tidak diberi label justru kebohongan yang meter biaya ini
ada untuk menghindarinya.
"""

from typing import TypedDict


class KutipanContoh(TypedDict):
    """Satu kutipan dokumen dalam jawaban contoh."""

    file_name: str
    page: str
    score: float
    snippet: str


class PanggilanContoh(TypedDict):
    """Satu panggilan tool dalam jawaban contoh."""

    tool_name: str
    arguments: dict[str, object]
    latency_ms: int


class JawabanContoh(TypedDict):
    """Satu pasangan pertanyaan-jawaban lengkap dengan jejaknya."""

    kunci: list[str]
    mode: str
    tool_calls: list[PanggilanContoh]
    citations: list[KutipanContoh]
    input_tokens: int
    output_tokens: int
    llm_calls: int
    jawaban: dict[str, str]


DAFTAR: list[JawabanContoh] = [
    {
        "kunci": ["gratis ongkir", "ongkir minimal", "free shipping", "minimum"],
        "mode": "dokumen",
        "tool_calls": [
            {
                "tool_name": "search_faq",
                "arguments": {"query": "gratis ongkir minimal belanja"},
                "latency_ms": 214,
            }
        ],
        "citations": [
            {
                "file_name": "03_kebijakan_pengiriman.pdf",
                "page": "1",
                "score": 0.81,
                "snippet": (
                    "GRATIS ONGKIR ke seluruh Indonesia untuk pembelian minimal "
                    "Rp 300.000 (berlaku untuk JNE REG, J&T Reguler, dan SiCepat REG)."
                ),
            }
        ],
        "input_tokens": 3480,
        "output_tokens": 96,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Minimalnya beda-beda per kurir, Kak. **Rp 300.000** untuk JNE REG "
                "dan SiCepat REG, tapi khusus J&T Reguler cukup **Rp 250.000**. "
                "Berlaku ke seluruh Indonesia ya."
            ),
            "en": (
                "The minimum differs per courier. It is **Rp 300,000** for JNE REG "
                "and SiCepat REG, but for J&T Reguler it is only **Rp 250,000**. "
                "This applies nationwide across Indonesia."
            ),
        },
    },
    {
        "kunci": ["ongkir retur", "retur siapa", "return shipping", "who pays"],
        "mode": "dokumen",
        "tool_calls": [
            {
                "tool_name": "search_faq",
                "arguments": {"query": "ongkir retur ditanggung siapa"},
                "latency_ms": 231,
            }
        ],
        "citations": [
            {
                "file_name": "04_kebijakan_retur_dan_garansi.pdf",
                "page": "2",
                "score": 0.83,
                "snippet": (
                    "Ketentuan Biaya Ongkos Kirim Retur. Produk cacat pabrik: "
                    "ditanggung GAYA.ID. Salah ukuran saat memesan: ditanggung pelanggan."
                ),
            },
            {
                "file_name": "04_kebijakan_retur_dan_garansi.pdf",
                "page": "1",
                "score": 0.76,
                "snippet": (
                    "Garansi Ukuran, 7 hari: ukuran yang diterima berbeda lebih dari "
                    "3 cm dari ukuran yang dipesan."
                ),
            },
        ],
        "input_tokens": 4180,
        "output_tokens": 148,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Tergantung penyebabnya, Kak. Kalau ukuran yang Kakak terima meleset "
                "lebih dari 3 cm dari yang dipesan, itu masuk Garansi Ukuran — ongkir "
                "retur dan ongkir kiriman penggantinya **ditanggung GAYA.ID**. Tapi "
                "kalau memang salah pilih ukuran waktu memesan, ongkir dua arah "
                "ditanggung pembeli. Klaimnya maksimal 7 hari setelah barang diterima ya."
            ),
            "en": (
                "It depends on the cause. If the size you received is more than 3 cm "
                "off from what you ordered, that falls under the Size Warranty — both "
                "the return shipping and the replacement shipping are **covered by "
                "GAYA.ID**. But if the wrong size was chosen at checkout, shipping both "
                "ways is on the buyer. Claims must be filed within 7 days of delivery."
            ),
        },
    },
    {
        "kunci": ["garansi sablon", "sablon", "bordir", "print warranty"],
        "mode": "dokumen",
        "tool_calls": [
            {
                "tool_name": "search_faq",
                "arguments": {"query": "garansi sablon bordir berapa lama"},
                "latency_ms": 198,
            }
        ],
        "citations": [
            {
                "file_name": "04_kebijakan_retur_dan_garansi.pdf",
                "page": "1",
                "score": 0.86,
                "snippet": (
                    "Garansi Sablon/Bordir, 30 hari: mengelupas pada pemakaian dan "
                    "pencucian normal sesuai panduan label."
                ),
            }
        ],
        "input_tokens": 3390,
        "output_tokens": 88,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Garansi sablon dan bordir berlaku **30 hari**, Kak — paling panjang "
                "di antara semua garansi kami. Cakupannya kalau sablonnya mengelupas "
                "pada pemakaian dan pencucian normal sesuai panduan label."
            ),
            "en": (
                "The print and embroidery warranty runs for **30 days** — the longest "
                "of all our warranties. It covers peeling under normal wear and washing "
                "according to the care label."
            ),
        },
    },
    {
        "kunci": ["dada", "lingkar", "size apa", "chest", "what size"],
        "mode": "dokumen",
        "tool_calls": [
            {
                "tool_name": "search_faq",
                "arguments": {"query": "tabel ukuran kaos pria lingkar dada"},
                "latency_ms": 206,
            }
        ],
        "citations": [
            {
                "file_name": "02_panduan_ukuran.pdf",
                "page": "1",
                "score": 0.79,
                "snippet": (
                    "Tabel Ukuran Kaos Pria (Cotton Combed 30s). L: lingkar dada "
                    "96-100 cm, panjang badan 71-73 cm, BB ideal 70-80 kg."
                ),
            }
        ],
        "input_tokens": 3610,
        "output_tokens": 112,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Lingkar dada 98 cm masuk **size L** untuk kaos pria, Kak — rentangnya "
                "96–100 cm. Kalau Kakak suka potongan yang agak longgar, ambil XL saja "
                "karena semua produk kami sudah punya kelonggaran 2–4 cm."
            ),
            "en": (
                "A 98 cm chest falls into **size L** for our men's tees — the range is "
                "96–100 cm. If you prefer a looser fit, go one size up to XL; all our "
                "products already include 2–4 cm of ease."
            ),
        },
    },
    {
        "kunci": ["bahan", "cotton", "combed", "material", "fabric"],
        "mode": "dokumen",
        "tool_calls": [
            {
                "tool_name": "search_faq",
                "arguments": {"query": "bahan produk kaos kemeja"},
                "latency_ms": 189,
            }
        ],
        "citations": [
            {
                "file_name": "01_faq_pelanggan.pdf",
                "page": "1",
                "score": 0.78,
                "snippet": (
                    "Kaos kami menggunakan bahan Cotton Combed 30s dan 24s yang lembut, "
                    "menyerap keringat, dan tahan lama."
                ),
            }
        ],
        "input_tokens": 3320,
        "output_tokens": 104,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Kaos kami pakai **Cotton Combed 30s dan 24s** — lembut, menyerap "
                "keringat, dan tahan lama. Untuk kemeja, bahannya Oxford, Rayon, atau "
                "Katun Poplin. Semuanya lewat quality control dulu sebelum dikirim."
            ),
            "en": (
                "Our tees use **Cotton Combed 30s and 24s** — soft, sweat-absorbent, "
                "and durable. Our shirts use Oxford, Rayon, or Cotton Poplin. Every "
                "batch passes quality control before shipping."
            ),
        },
    },
    {
        "kunci": ["kao-0002", "ready", "stok", "stock", "tersedia"],
        "mode": "database",
        "tool_calls": [
            {
                "tool_name": "check_stock",
                "arguments": {"sku": "KAO-0002", "size": "L"},
                "latency_ms": 341,
            }
        ],
        "citations": [],
        "input_tokens": 3560,
        "output_tokens": 92,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Ready, Kak! Kaos Oversize Ashen size L warna Navy sisa **12 pcs** di "
                "Gudang Jakarta. Mau sekalian aku cekkan warna lainnya?"
            ),
            "en": (
                "In stock! The Oversize Ashen Tee in size L, Navy, has **12 pcs** left "
                "at our Jakarta warehouse. Want me to check the other colours too?"
            ),
        },
    },
    {
        "kunci": ["hoodie", "olive", "warna"],
        "mode": "database",
        "tool_calls": [
            {
                "tool_name": "search_products",
                "arguments": {"keyword": "hoodie", "color": "Olive"},
                "latency_ms": 388,
            }
        ],
        "citations": [],
        "input_tokens": 3720,
        "output_tokens": 126,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Ada, Kak. **Hoodie Halcyon** warna Olive, Rp 329.000, bahan fleece "
                "tebal. Sisa 4 pcs untuk size M di Gudang Bandung; size S dan L lagi "
                "kosong. Mau aku cekkan warna lain?"
            ),
            "en": (
                "Yes! The **Halcyon Hoodie** in Olive, Rp 329,000, heavyweight fleece. "
                "Four pieces left in size M at our Bandung warehouse; S and L are out "
                "of stock. Want me to check other colours?"
            ),
        },
    },
    {
        "kunci": ["inv-2026", "lacak", "pesanan", "track", "order"],
        "mode": "database",
        "tool_calls": [
            {
                "tool_name": "track_order",
                "arguments": {"order_number": "INV-2026-000012", "phone_last4": "4417"},
                "latency_ms": 412,
            }
        ],
        "citations": [],
        "input_tokens": 3640,
        "output_tokens": 118,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Pesanan **INV-2026-000012** sudah **terkirim**, Kak, lewat JNE. "
                "Kalau paketnya belum Kakak terima padahal statusnya sudah terkirim, "
                "laporkan ke kami maksimal 2x24 jam ya, nanti kami koordinasikan "
                "dengan kurirnya."
            ),
            "en": (
                "Order **INV-2026-000012** has been **delivered** via JNE. If the "
                "package has not actually reached you despite that status, please "
                "report it within 2x24 hours and we will coordinate with the courier."
            ),
        },
    },
    {
        "kunci": ["gratisongkir", "promo", "kode", "voucher", "discount"],
        "mode": "database",
        "tool_calls": [
            {
                "tool_name": "check_promotion",
                "arguments": {"code": "GRATISONGKIR"},
                "latency_ms": 297,
            }
        ],
        "citations": [],
        "input_tokens": 3510,
        "output_tokens": 108,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Masih aktif, Kak. **GRATISONGKIR** memberi potongan ongkir "
                "Rp 25.000 untuk belanja minimal Rp 150.000. Tinggal dimasukkan "
                "waktu checkout ya."
            ),
            "en": (
                "Still active. **GRATISONGKIR** gives a Rp 25,000 shipping discount "
                "for orders over Rp 150,000. Just enter it at checkout."
            ),
        },
    },
    {
        "kunci": ["ramadan26", "ramadan"],
        "mode": "database",
        "tool_calls": [
            {
                "tool_name": "check_promotion",
                "arguments": {"code": "RAMADAN26"},
                "latency_ms": 284,
            }
        ],
        "citations": [],
        "input_tokens": 3490,
        "output_tokens": 102,
        "llm_calls": 2,
        "jawaban": {
            "id": (
                "Belum bisa dipakai, Kak. Promo Ramadan baru mulai berlaku "
                "**7 Oktober 2026**. Yang aktif sekarang GRATISONGKIR — potongan "
                "ongkir Rp 25.000 untuk belanja di atas Rp 150.000."
            ),
            "en": (
                "Not yet. The Ramadan promo only starts on **7 October 2026**. What is "
                "active right now is GRATISONGKIR — a Rp 25,000 shipping discount for "
                "orders above Rp 150,000."
            ),
        },
    },
    {
        "kunci": ["tukar ukuran", "kekecilan", "exchange", "too small"],
        "mode": "campuran",
        "tool_calls": [
            {
                "tool_name": "check_stock",
                "arguments": {"sku": "KAO-0002", "size": "XL"},
                "latency_ms": 336,
            },
            {
                "tool_name": "search_faq",
                "arguments": {"query": "prosedur tukar ukuran"},
                "latency_ms": 224,
            },
        ],
        "citations": [
            {
                "file_name": "04_kebijakan_retur_dan_garansi.pdf",
                "page": "2",
                "score": 0.80,
                "snippet": (
                    "Pilihan Resolusi Retur. Tukar Ukuran: ditukar dengan ukuran yang "
                    "tepat (stok tersedia), 3-5 hari kerja."
                ),
            }
        ],
        "input_tokens": 5240,
        "output_tokens": 164,
        "llm_calls": 3,
        "jawaban": {
            "id": (
                "Size XL-nya ready kok, Kak — sisa 7 pcs. Untuk tukar ukuran, "
                "ajukan maksimal **7 hari** setelah barang diterima, syaratnya belum "
                "dicuci dan label masih menempel. Prosesnya 3–5 hari kerja setelah "
                "barangnya sampai di gudang kami."
            ),
            "en": (
                "Size XL is available — 7 pieces left. For a size exchange, submit the "
                "request within **7 days** of delivery, with the item unwashed and tags "
                "still attached. Processing takes 3–5 business days once it reaches our "
                "warehouse."
            ),
        },
    },
]

# Ditampilkan saat pertanyaan tidak cocok dengan satu pun contoh di atas.
FALLBACK: dict[str, str] = {
    "id": (
        "Di mode contoh ini aku baru punya jawaban untuk pertanyaan-pertanyaan di "
        "halaman panduan, Kak. Coba salah satu contoh di sana ya — kalau demo sudah "
        "pakai AI sungguhan, pertanyaan bebas seperti ini bisa aku jawab."
    ),
    "en": (
        "In this sample mode I only have answers for the questions listed on the guide "
        "page. Try one of those — once the demo runs on the real model, open-ended "
        "questions like this will work too."
    ),
}

# Ditampilkan untuk pertanyaan yang memang di luar cakupan, bahkan saat AI aktif.
DI_LUAR_CAKUPAN: dict[str, str] = {
    "id": (
        "Maaf ya Kak, itu di luar yang aku tahu. Aku cuma bisa bantu soal produk, "
        "stok, ukuran, ongkir, pesanan, dan kebijakan toko. Angka penjualan dan "
        "margin tidak ada di data yang aku baca."
    ),
    "en": (
        "Sorry, that is outside what I know. I can only help with products, stock, "
        "sizing, shipping, orders, and store policy. Sales figures and margins are not "
        "part of the data I read."
    ),
}

KUNCI_DI_LUAR_CAKUPAN: list[str] = [
    "omzet",
    "margin",
    "revenue",
    "profit",
    "penjualan bulan",
    "laba",
    "keuntungan",
]
