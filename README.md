# RAG Fashion Chatbot

Customer service AI untuk clothing brand kecil. Menjawab pertanyaan pembeli soal
FAQ, ketersediaan stok, detail produk, ukuran, promo, dan status pesanan —
dengan jawaban yang selalu bersumber dari data, bukan karangan model.

## Masalah yang diselesaikan

Skema database di project ini berskala e-commerce nyata: **28 tabel**. Itu
menghadirkan masalah yang tidak muncul di skema kecil:

> Permukaan skema terlalu lebar untuk LLM. Model kecil seperti Haiku 4.5 yang
> dihadapkan pada puluhan tabel mentah akan salah pilih join, mengarang nama
> kolom, dan salah memilih tool.

Solusinya berlapis — **LLM tidak pernah menyentuh tabel mentah:**

```
28 tabel  ──►  4 view + 4 RPC Postgres  ──►  8 tool berdeskripsi tegas  ──►  Claude Haiku 4.5
   raw            peredam kompleksitas         permukaan yang dilihat LLM
```

Ditambah aturan kedua: **data yang berubah tiap transaksi tidak boleh di-embed.**
FAQ dari PDF masuk ke vector store; stok dan pesanan selalu di-query live.
Chatbot yang menyebut stok basi lebih merugikan daripada chatbot yang bilang
tidak tahu.

## Tech stack

| Komponen | Pilihan | Alasan |
|---|---|---|
| Framework chatbot | LlamaIndex (`FunctionAgent`) | Agentic tool-calling, bukan router |
| LLM | Claude **Haiku 4.5** (`claude-haiku-4-5`) | Murah & cepat untuk alur CS bervolume tinggi |
| Database | Supabase (Postgres) | Katalog, inventori, penjualan, riwayat chat |
| Vector DB | ChromaDB (persisten lokal) | Index FAQ dari PDF |
| Embedding | `intfloat/multilingual-e5-base` (HuggingFace lokal) | Claude API tidak menyediakan embedding; model ini kuat di Bahasa Indonesia dan gratis |
| API | FastAPI | `POST /api/v1/chat`, `GET /api/v1/health` |
| Demo UI | Streamlit | Peragaan ke klien |

## Arsitektur

```
                  ┌──────────────┐        ┌─────────────────┐
   Pembeli ──────►│  FastAPI     │───────►│ ChatbotService  │
                  │  /api/v1/chat│        │ (FunctionAgent) │
                  └──────────────┘        └────────┬────────┘
                                                   │ 8 tool
                    ┌──────────────────────────────┼──────────────────────────┐
                    ▼                              ▼                          ▼
            ┌───────────────┐            ┌──────────────────┐        ┌────────────────┐
            │  search_faq   │            │ search_products  │        │  track_order   │
            │               │            │ get_product_detail│       │ check_promotion│
            │               │            │ check_stock      │        │ escalate_to_.. │
            │               │            │ recommend_size   │        │                │
            └───────┬───────┘            └────────┬─────────┘        └───────┬────────┘
                    ▼                             ▼                          ▼
            ┌───────────────┐            ┌─────────────────────────────────────────┐
            │   ChromaDB    │            │  View & RPC Postgres (peredam)          │
            │  (FAQ PDF)    │            │  v_product_catalog · v_variant_avail…   │
            └───────────────┘            │  v_order_tracking  · v_active_promotions│
                                         │  search_products() · check_availability()│
                                         │  recommend_size()  · track_order()       │
                                         └────────────────┬────────────────────────┘
                                                          ▼
                                                 ┌──────────────────┐
                                                 │ Supabase 28 tabel│
                                                 └──────────────────┘
```

### Delapan tool agent

| Tool | Sumber | Kegunaan |
|---|---|---|
| `search_faq` | ChromaDB | Kebijakan retur, pengiriman, pembayaran, perawatan bahan |
| `search_products` | RPC `search_products` | Cari produk (FTS Bahasa Indonesia + toleransi typo) |
| `get_product_detail` | `v_product_catalog` | Bahan, cara rawat, potongan, varian |
| `check_stock` | RPC `check_availability` | Stok **live** lintas gudang + ETA restock |
| `recommend_size` | RPC `recommend_size` | Cocokkan ukuran badan ke size chart |
| `track_order` | RPC `track_order` | Status pesanan, **wajib verifikasi identitas** |
| `check_promotion` | `v_active_promotions` | Promo yang benar-benar berlaku hari ini |
| `escalate_to_human` | tabel `escalations` | Handoff ke admin |

Deskripsi tiap tool menyebutkan **kapan tool TIDAK boleh dipakai**, bukan hanya
kapan dipakai. Dengan 8 tool, batas negatif jauh lebih efektif menekan salah
pilih tool daripada deskripsi positif saja.

### Keamanan data pelanggan

Tabel `customers` dan `addresses` **tidak terjangkau tool mana pun**. Satu-satunya
jalan ke data pesanan adalah RPC `track_order` yang mewajibkan nomor pesanan
**dan** 4 digit terakhir nomor HP. View `v_order_tracking` sudah memaskir nama
dan tidak memuat email maupun alamat.

## Struktur project

```
app/
├── config.py            # Pydantic Settings dari .env
├── dependencies.py      # factory ber-@lru_cache: LLM, embedder, chroma, supabase
├── prompts/system.py    # system prompt + guardrail
├── repositories/        # 1 kelas = 1 view/RPC, tanpa logika bisnis
├── services/            # logika bisnis + formatting ke string untuk LLM
├── tools/registry.py    # 8 FunctionTool + perekam audit
├── models/              # schema Pydantic
├── api/chat/            # routes.py · schemas.py · service.py
└── utils/               # logger, resolusi error pihak ketiga
supabase/migrations/     # 001–008, skema 28 tabel + view + RPC + index + RLS
scripts/                 # smoke_llm · ingest_faq · seed_database · run_eval
evals/                   # dataset.jsonl (40 kasus) + panduan
tests/                   # unit test repository & service, integration test route
ui/streamlit_app.py      # demo UI
```

## Setup

### 1. Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

copy .env.example .env    # lalu isi kredensialnya
```

Yang wajib diisi di `.env`:

| Variabel | Keterangan |
|---|---|
| `ANTHROPIC_API_KEY` | API key Claude |
| `SUPABASE_URL` | URL project Supabase |
| `SUPABASE_SERVICE_KEY` | Service-role key (backend saja, **jangan** dikirim ke frontend) |

### 2. Verifikasi koneksi LLM

```bash
python scripts/smoke_llm.py
```

Satu panggilan pendek ke `claude-haiku-4-5`. Jalankan ini lebih dulu sebagai
gerbang: kalau gagal, tidak ada gunanya melanjutkan ke seeding dan ingestion.

**Catatan kompatibilitas SDK.** `anthropic` 1.x menghapus `temperature`, `top_p`,
dan `top_k` dari signature `Messages.create()`. Wrapper `llama-index-llms-anthropic`
0.12.0 tetap mengirim `temperature` untuk model di luar daftar internalnya —
daftar itu hanya memuat model yang **API**-nya menolak parameter tersebut
(Opus 4.7/4.8/5, Fable 5, Sonnet 5), bukan model yang **SDK**-nya tidak lagi
mengekspos parameter itu. Akibatnya Haiku 4.5 gagal dengan:

```
TypeError: Messages.create() got an unexpected keyword argument 'temperature'
```

`app/utils/anthropic_compat.py` menyelesaikannya dengan memindahkan parameter
sampling ke `extra_body`, yang diteruskan SDK apa adanya ke body request —
Haiku 4.5 masih menerima `temperature` di level API, jadi nilai 0.2 tetap berlaku
dan jawaban tetap konsisten. Shim ini menetralkan diri sendiri: begitu
`llama-index` berhenti mengirim `temperature`, perilakunya sama persis dengan
wrapper aslinya. `tests/test_anthropic_compat.py` menjaga keduanya dan akan gagal
kalau salah satu asumsi itu berubah.

### 3. Skema database

Jalankan `supabase/migrations/001` sampai `008` **berurutan** di Supabase SQL Editor.

```
001_extensions.sql   pgcrypto (uuid) + pg_trgm (toleransi typo)
002_catalog.sql      11 tabel: kategori, koleksi, warna, ukuran, size chart, produk, varian
003_inventory.sql     4 tabel: gudang, stok, mutasi, jadwal restock
004_sales.sql         8 tabel: pelanggan, alamat, pesanan, item, kirim, retur, promo
005_chatbot.sql       5 tabel: percakapan, pesan, audit tool call, eskalasi, unanswered
006_views.sql        4 view peredam kompleksitas
007_functions.sql    4 RPC yang dipetakan langsung ke tool agent
008_indexes_rls.sql  index + Row Level Security
```

Lalu isi data contoh:

```bash
python scripts/seed_database.py
```

Seed dikunci (`Faker.seed(42)`) supaya reproducible. Kasus tepi ditanam sengaja:
produk habis dengan jadwal restock, produk nonaktif, varian di satu gudang saja,
promo kedaluwarsa / aktif / belum mulai. Di akhir proses script mencetak SKU dan
nomor pesanan acuan untuk pengujian.

### 4. Index FAQ

Taruh dokumen FAQ brand (PDF, TXT, atau MD) di `data/raw/faq/`, lalu:

```bash
python scripts/ingest_faq.py
```

Sudah ada `data/raw/faq/faq-contoh.md` sebagai contoh supaya pipeline bisa langsung
dicoba — ganti dengan dokumen asli sebelum dipakai ke pembeli. Unduhan model
embedding (~450 MB) terjadi sekali saat pertama dijalankan.

Dokumen Markdown dipecah **per heading** lebih dulu sebelum dipecah per kalimat.
Ini penting: dengan pemecahan per kalimat saja, satu chunk mencampur beberapa topik
FAQ dan retrieval jadi meleset — pertanyaan soal perawatan bahan bisa mengembalikan
bagian kebijakan retur.

### 5. Jalankan

```bash
uvicorn app.api.main:app --reload
streamlit run ui/streamlit_app.py     # terminal terpisah
```

```bash
curl http://localhost:8000/api/v1/health

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-1","message":"Hoodie hitam size L ready ga?"}'
```

## Pengujian

```bash
pytest                          # unit + integration test, tanpa jaringan
python scripts/run_eval.py      # eval end-to-end terhadap Claude sungguhan
```

`pytest` memakai client Supabase palsu, jadi cepat dan gratis. Termasuk di dalamnya
`tests/test_migrations.py`, yang memvalidasi sintaks seluruh migrasi SQL dengan parser
Postgres asli (libpg_query) dan memastikan kolom yang dikembalikan view/RPC tetap
cocok dengan model Pydantic yang memvalidasinya di runtime.
`run_eval.py` benar-benar memanggil API Claude (ada biaya) dan melaporkan:

- **akurasi pemilihan tool** — target ≥ 90%
- **groundedness** — target 100% pada klaim stok/harga
- **rata-rata tool call per pertanyaan** — proksi efisiensi biaya

Penilaian dibaca dari jejak tool call yang benar-benar terjadi
(tabel `message_tool_calls`), bukan dari menebak isi teks jawaban.
Detail: [`evals/README.md`](evals/README.md).

### Hasil terukur (41 kasus, Claude Haiku 4.5)

| Metrik | Hasil | Target |
|---|---|---|
| Akurasi pemilihan tool | **97,6%** | ≥ 90% |
| Groundedness | **100%** | 100% |
| Rata-rata tool call / pertanyaan | 0,95 | — |

Angka awalnya 87,8%. Dua perbaikan menaikkannya, dan keduanya berada di
**deskripsi tool**, bukan di system prompt — deskripsi tool ada persis di titik
keputusan model, jadi jauh lebih berpengaruh:

1. `escalate_to_human` semula berbunyi "jangan pakai sebagai jalan pintas".
   Kalimat itu justru membuat model mengumpulkan detail lebih dulu dan tidak
   pernah memanggilnya. Diganti dengan instruksi memanggil di giliran yang sama
   dan mengisi `reason` dengan kalimat pembeli apa adanya.
2. `search_products` tidak menyebutkan bahwa `keyword` boleh dikosongkan, jadi
   pertanyaan luas seperti "produk apa aja yang ready?" dibalas pertanyaan balik.

### Jaring pengaman eskalasi

Sisa kegagalan yang tidak bisa dihilangkan lewat prompt: sesekali model menulis
"saya teruskan ke admin" tanpa memanggil `escalate_to_human`. Pembeli lalu
menunggu balasan yang tidak akan pernah datang.

Efek samping sepenting itu tidak boleh bergantung pada kepatuhan model, jadi
`ChatbotService._guard_unrecorded_escalation` mendeteksi klaim tersebut di teks
jawaban dan mencatat eskalasinya sendiri, dengan penanda `[otomatis]`. Bentuk
tawaran ("mau saya teruskan ke admin?") sengaja tidak ikut terdeteksi.

Baris otomatis itu **tidak** ditambahkan ke `tool_calls`, supaya eval tetap
melaporkan kegagalan model apa adanya alih-alih menutupinya oleh jaring pengaman.

## Catatan konfigurasi Claude

`claude-haiku-4-5`, `max_tokens=2048` — balasan CS memang pendek, ini pengecualian
sadar dari default yang lebih besar. Parameter `thinking` dan `output_config.effort`
sengaja **tidak** dipakai: Haiku 4.5 menolak `effort`, dan thinking di Haiku memakai
`budget_tokens` gaya lama yang tidak diperlukan untuk alur berlatensi rendah ini.

## Batasan yang diketahui

- **Prompt caching belum diaktifkan.** System prompt dan definisi 8 tool stabil, jadi
  kandidat kuat untuk `cache_control` ephemeral. Belum dipasang karena perlu verifikasi
  bagaimana wrapper LlamaIndex meneruskan parameter tersebut.
- **8 tool masih dalam batas nyaman Haiku 4.5.** Kalau eval menunjukkan kebingungan
  pemilihan tool setelah tool bertambah, langkah berikutnya adalah
  `tool_search_tool_bm25_20251119` dengan `defer_loading`.
- **`escalate_to_human` hanya mencatat ke database.** Notifikasi nyata (email/WhatsApp
  ke admin) belum diimplementasikan.
- **Kepatuhan eskalasi model belum 100%.** Diukur 97,6% akurasi tool; sisanya
  ditangani jaring pengaman di kode, bukan diklaim beres. Kalau kepatuhan ini
  jadi kritis, langkah berikutnya adalah menaikkan model untuk rute eskalasi saja.
- **Streaming belum ada.** Endpoint mengembalikan jawaban utuh; untuk UX chat yang
  lebih responsif, SSE bisa ditambahkan.
- **Shim `anthropic_compat` bersifat sementara.** Ia menimpa property privat
  (`_model_kwargs`) milik wrapper LlamaIndex. Begitu ada rilis
  `llama-index-llms-anthropic` yang sadar SDK 1.x, hapus shim dan kembalikan
  `dependencies.get_llm()` ke `Anthropic` biasa — `tests/test_anthropic_compat.py`
  akan memberi tahu saat momen itu tiba.

## Varian implementasi

Branch ini memakai **Claude (Claude API)** sebagai penyedia LLM. Varian dengan
model lokal (mis. Qwen) direncanakan di branch terpisah. Titik sentuh yang
berbeda antar-varian hanya dua:

| Berkas | Yang perlu diganti |
|---|---|
| `app/dependencies.py` -> `get_llm()` | Kembalikan wrapper LLM lain, mis. `Ollama` atau `HuggingFaceLLM` |
| `app/config.py` | `llm_model`, `llm_max_tokens`, dan kredensial penyedia |

Sisanya tidak berubah: skema database, 8 tool, guardrail prompt, eval harness,
dan seluruh test tidak terikat pada penyedia LLM tertentu. `app/utils/anthropic_compat.py`
khusus Claude dan tidak diperlukan pada varian lokal.

## Kontributor

- **Arya Eka Septia Putra** — pemilik dan pengarah project
- **Claude** (Anthropic, model Opus 5) — implementasi kode, desain skema,
  eval harness, dan penulisan dokumentasi, dijalankan lewat Claude Code

Setiap commit di project ini mencantumkan Claude sebagai co-author.
