# RAG Fashion Chatbot

Customer service AI untuk clothing brand kecil. Menjawab pertanyaan pembeli soal
FAQ, ketersediaan stok, detail produk, ukuran, promo, dan status pesanan —
dengan jawaban yang selalu bersumber dari data, bukan karangan model.

## Masalah yang diselesaikan

Skema database di project ini berskala e-commerce nyata: **28 tabel**. Itu
menghadirkan masalah yang tidak muncul di skema kecil:

> Permukaan skema terlalu lebar untuk LLM. Model kecil seperti Qwen3-1.7B yang
> dihadapkan pada puluhan tabel mentah akan salah pilih join, mengarang nama
> kolom, dan salah memilih tool.

Solusinya berlapis — **LLM tidak pernah menyentuh tabel mentah:**

```
28 tabel  ──►  4 view + 4 RPC Postgres  ──►  8 tool berdeskripsi tegas  ──►  Qwen3-1.7B
   raw            peredam kompleksitas         permukaan yang dilihat LLM
```

Ditambah aturan kedua: **data yang berubah tiap transaksi tidak boleh di-embed.**
FAQ dari PDF masuk ke vector store; stok dan pesanan selalu di-query live.
Chatbot yang menyebut stok basi lebih merugikan daripada chatbot yang bilang
tidak tahu.

Aturan ketiga khusus varian ini: **model kecil tidak memilih tool dan menulis
jawaban dalam satu tarikan napas.** Model 1.7B yang mengerjakan keduanya
sekaligus cenderung melengkapi kalimatnya dengan harga dan stok yang tidak
pernah dikembalikan tool. Karena itu jawaban akhir disusun tahap kedua yang
hanya melihat hasil tool, bukan pertanyaan aslinya saja.

## Tech stack

| Komponen | Pilihan | Alasan |
|---|---|---|
| Framework chatbot | LlamaIndex (`FunctionAgent`) | Agentic tool-calling, bukan router |
| LLM agent | **Qwen3-1.7B** via Ollama (`qwen3:1.7b`) | Nol biaya API, jalan penuh di lokal, muat di VRAM 4 GB |
| LLM composer | **Qwen3-1.7B** via Ollama, temperature 0.1 | Menyusun jawaban akhir hanya dari hasil tool |
| Database | Supabase (Postgres) | Katalog, inventori, penjualan, riwayat chat |
| Vector DB | ChromaDB (persisten lokal) | Index FAQ dari PDF |
| Embedding | `intfloat/multilingual-e5-base` (HuggingFace lokal) | Kuat di Bahasa Indonesia, jalan di CPU, dan tidak menuntut VRAM yang sedang dipakai LLM |
| API | FastAPI | `POST /api/v1/chat`, `GET /api/v1/health` |
| Demo UI | Streamlit | Peragaan ke klien |

## Arsitektur

```
                  ┌──────────────┐        ┌─────────────────┐
   Pembeli ──────►│  FastAPI     │───────►│ Tahap 1: agent  │
        ▲         │  /api/v1/chat│        │ (FunctionAgent) │
        │         └──────────────┘        └────────┬────────┘
        │                                          │ 8 tool
        │  ┌──────────────────────────┐            │
        └──┤ Tahap 2: AnswerComposer  │◄───────────┤
  jawaban  │ Qwen3-1.7B, temp 0.1     │  hasil     │
           │ jawaban HANYA dari bukti │  tool utuh │
           └──────────────────────────┘            │
                                                   │
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
├── prompts/             # system.py (pemilihan tool) + composer.py (jawaban akhir)
├── repositories/        # 1 kelas = 1 view/RPC, tanpa logika bisnis
├── services/            # logika bisnis + composer.py (penyusun jawaban akhir)
├── tools/registry.py    # 8 FunctionTool + perekam audit
├── models/              # schema Pydantic
├── evals/               # penilai mutu: judge · answer (RAGAS) · retrieval (DeepEval)
├── api/chat/            # routes.py · schemas.py · service.py
└── utils/               # logger, resolusi error pihak ketiga, pembersih <think>
supabase/migrations/     # 001–008, skema 28 tabel + view + RPC + index + RLS
scripts/                 # smoke_llm · ingest_faq · seed_database · run_eval
evals/                   # dataset.jsonl (41 kasus) + retrieval.jsonl (16) + panduan
notebooks/               # 00_eval_quality_colab.ipynb — eval mutu di Colab T4
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
| `SUPABASE_URL` | URL project Supabase |
| `SUPABASE_SERVICE_KEY` | Service-role key (backend saja, **jangan** dikirim ke frontend) |

Tidak ada API key LLM di varian ini. Yang dibutuhkan sebagai gantinya adalah
server [Ollama](https://ollama.com) yang jalan di mesin yang sama:

```bash
ollama pull qwen3:1.7b
ollama list                # pastikan qwen3:1.7b muncul
```

Bobot Q4 model ini ~1,4 GB dan muat di GPU 4 GB. Setelan lain (`LLM_CONTEXT_WINDOW`,
`LLM_KEEP_ALIVE`, `LLM_THINKING`, dan seluruh `COMPOSER_*`) sudah punya default yang
masuk akal di `.env.example` — alasan tiap angka ditulis sebagai komentar di berkas itu.

### 2. Verifikasi koneksi LLM

```bash
python scripts/smoke_llm.py
```

Gerbang tiga lapis, dari yang paling murah ke paling mahal:

1. Server Ollama hidup dan `qwen3:1.7b` benar-benar ter-pull.
2. Model menjawab satu prompt pendek, dan jawabannya **tidak** memuat blok `<think>`.
3. Model benar-benar memancarkan tool call untuk satu tool dummy.

Lapis ketiga yang paling penting. Tool calling adalah kemampuan paling rapuh pada
model 1.7B, dan seluruh arsitektur ini bergantung padanya — jauh lebih murah
ketahuan di sini daripada di tengah eval 41 kasus.

**Catatan thinking mode.** Qwen3 adalah model hybrid: default-nya memancarkan blok
penalaran sebelum menjawab. Blok itu memperlambat tiap giliran dan bisa bocor ke
pembeli, jadi dimatikan lewat `LLM_THINKING=false` (diteruskan sebagai `think=false`
ke Ollama). Lapis kedua dipasang di kode: `app/utils/text.py` membuang blok `<think>`
dari keluaran agent maupun composer, apa pun kondisinya. Teks yang langsung dibaca
pembeli terlalu berisiko untuk hanya diandalkan pada satu setelan.

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

Pengukuran project ini berlapis tiga, dari yang paling murah ke paling mahal:

| Lapis | Perkakas | Butuh juri LLM? | Menjawab pertanyaan |
|---|---|---|---|
| Akurasi pemilihan tool | `scripts/run_eval.py` | Tidak | Agent memilih sumber data yang benar? |
| Mutu jawaban akhir | RAGAS | Ya, Claude API | Jawaban bersandar pada bukti, dan menjawab yang ditanya? |
| Mutu retrieval | DeepEval | Ya, Claude API — kecuali `section_hit_rate` | Potongan yang tepat terambil, dan berperingkat benar? |

Lapis pertama membaca jejak tool call, jadi deterministik dan gratis. Dua lapis
berikutnya menjawab hal yang tidak terjangkau jejak: `must_not_contain` hanya
menangkap frasa yang sudah diantisipasi penulis dataset, dan tidak ada satu pun
metrik lama yang tahu apakah `search_faq` mengambil potongan yang benar. Tanpa
lapis ketiga, jawaban bisa "grounded" terhadap bukti yang keliru dan tetap
dinyatakan lulus.

```bash
pytest                          # unit + integration test, tanpa jaringan
python scripts/run_eval.py      # eval end-to-end terhadap model lokal sungguhan
```

`pytest` memakai client Supabase palsu, jadi cepat dan gratis. Termasuk di dalamnya
`tests/test_migrations.py`, yang memvalidasi sintaks seluruh migrasi SQL dengan parser
Postgres asli (libpg_query) dan memastikan kolom yang dikembalikan view/RPC tetap
cocok dengan model Pydantic yang memvalidasinya di runtime.
`run_eval.py` benar-benar menjalankan model lokal — dua panggilan per kasus
(agent + composer), jadi run penuh 41 kasus memakan waktu puluhan menit di GPU
laptop. Yang dilaporkan:

- **akurasi pemilihan tool** — target ≥ 90%
- **groundedness** — target 100% pada klaim stok/harga
- **rata-rata tool call per pertanyaan** — proksi latensi per giliran

Penilaian dibaca dari jejak tool call yang benar-benar terjadi
(tabel `message_tool_calls`), bukan dari menebak isi teks jawaban.
Detail: [`evals/README.md`](evals/README.md).

### Mutu jawaban dan retrieval (RAGAS + DeepEval)

Run `run_eval.py` juga menulis `outputs/eval_trace.jsonl`: pertanyaan, jawaban,
bukti, dan potongan yang terambil untuk tiap kasus. Berkas itu yang dinilai
lapis dua dan tiga.

Dua jenis konteks dicatat terpisah, dan pemisahan itu menentukan benar-tidaknya
angkanya. RAGAS menilai jawaban terhadap **keluaran seluruh tool** — itulah bukti
yang dilihat `AnswerComposer`. DeepEval menilai retrieval terhadap **potongan FAQ
saja**. Kalau keduanya disatukan, jawaban stok akan dituduh berhalusinasi karena
angkanya tidak ada di potongan FAQ, padahal datanya sah dan datang dari Postgres.

Jalankan lewat [`notebooks/00_eval_quality_colab.ipynb`](notebooks/00_eval_quality_colab.ipynb)
pada runtime Colab T4. Notebook memasang Ollama, menarik model, membangun index
FAQ, menjalankan kedua dataset, lalu menilai — hasilnya `outputs/quality_report.json`.

Model juri `claude-haiku-4-5` lewat Claude API, terpisah dari `qwen3:1.7b` yang
diuji. Model yang menilai jawabannya sendiri bukan pengukuran, dan juri kecil
menilai terlalu berisik untuk dipercaya.

**Ini satu-satunya bagian project yang memakai API berbayar, dan itu disengaja.**
Juri adalah alat ukur, bukan bagian produk — chatbot-nya tetap berjalan penuh di
lokal tanpa kunci API mana pun, dan justru itu klaim yang sedang diuji.
`ANTHROPIC_API_KEY` hanya dibutuhkan saat menjalankan penilaian mutu; kosongkan
kalau hanya menjalankan chatbot. Embedding juri tetap lokal, karena Anthropic
tidak menyediakan API embedding dan metrik yang memakainya hanya mengukur
kemiripan vektor.

Dependency penilai berat (langchain, datasets, grpcio, opentelemetry), jadi
dipasang di venv terpisah lewat `requirements-eval.txt`, bukan di venv utama.

**Tiga hal yang harus ikut terbaca bersama angkanya:**

- Sebut juri dan yang diuji berpasangan. Angkanya berarti "Qwen3-1.7B lokal,
  dinilai `claude-haiku-4-5`"; `judge_model` ikut tersimpan di laporan supaya
  tidak tercatat terpisah dari skornya.
- Korpus FAQ baru 9 potongan dari satu dokumen contoh. Metrik retrieval di atas
  16 pertanyaan membuktikan pipeline-nya bekerja, bukan bahwa retrieval-nya bagus.
- Gagal-nilai bukan skor nol. `unscored_total` dilaporkan terpisah dan tidak ikut
  rata-rata; angka besar di sana menunjuk masalah transport atau rate limit,
  bukan mutu chatbot.

### Hasil terukur (41 kasus yang sama, dua penyedia LLM)

| Metrik | Claude Haiku 4.5 (API) | Qwen3-1.7B (lokal) | Target |
|---|---|---|---|
| Akurasi pemilihan tool | **97,6%** | _belum diukur_ | ≥ 90% |
| Groundedness | **100%** | _belum diukur_ | 100% |
| Rata-rata tool call / pertanyaan | 0,95 | _belum diukur_ | — |

> Kolom Qwen diisi dari `outputs/eval_report_qwen.json` setelah run penuh
> dijalankan. Angka Claude direproduksi dari branch `chatbot-claude-api`.
> Tidak ada angka yang ditulis di sini tanpa pengukuran.

Nilai perbandingan ini bukan pada siapa yang menang. Dataset, tool, prompt
guardrail, dan cara skoringnya identik, jadi selisihnya mengukur satu hal saja:
berapa banyak akurasi pemilihan tool yang dilepas ketika biaya per token
dihilangkan dan seluruh data pembeli berhenti meninggalkan mesin.

Pada varian API, angka awalnya 87,8%. Dua perbaikan menaikkannya ke 97,6%, dan
keduanya berada di **deskripsi tool**, bukan di system prompt — deskripsi tool
ada persis di titik keputusan model, jadi jauh lebih berpengaruh:

1. `escalate_to_human` semula berbunyi "jangan pakai sebagai jalan pintas".
   Kalimat itu justru membuat model mengumpulkan detail lebih dulu dan tidak
   pernah memanggilnya. Diganti dengan instruksi memanggil di giliran yang sama
   dan mengisi `reason` dengan kalimat pembeli apa adanya.
2. `search_products` tidak menyebutkan bahwa `keyword` boleh dikosongkan, jadi
   pertanyaan luas seperti "produk apa aja yang ready?" dibalas pertanyaan balik.

Kedua perbaikan itu ikut terbawa ke branch ini tanpa perubahan — itu justru yang
membuat perbandingannya adil.

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

## Catatan konfigurasi model lokal

| Setelan | Nilai | Alasan |
|---|---|---|
| `LLM_CONTEXT_WINDOW` | 8192 | `num_ctx` default Ollama terlalu kecil untuk system prompt + skema 8 tool + riwayat + hasil tool. Qwen3-1.7B native 32k; 8k cukup dan aman di VRAM 4 GB |
| `LLM_KEEP_ALIVE` | `10m` | Tanpa ini bobot di-unload antar request dan tiap giliran bayar cold start — fatal saat eval 41 kasus |
| `LLM_MAX_TOKENS` | 1024 | Tahap agent hanya perlu memancarkan tool call, bukan prosa |
| `COMPOSER_TEMPERATURE` | 0.1 | Tahap yang menyentuh angka harga dan stok tidak boleh kreatif |
| `AGENT_MAX_ITERATIONS` | 5 | Model 1.7B yang bingung cenderung memanggil tool berulang-ulang; batas ini yang membatasi latensi terburuk |

`num_ctx` yang jebol tidak melempar error: Ollama diam-diam memotong prompt dari
kiri, yang justru membuang system prompt beserta seluruh aturan groundedness-nya.
Karena itu blok bukti yang dikirim ke composer dibatasi di sisi aplikasi
(`app/services/composer.py`), bukan diserahkan ke pemotongan otomatis.

## Batasan yang diketahui

- **Butuh GPU untuk latensi yang wajar.** Diukur di RTX 3050 Laptop 4 GB. Di CPU
  murni model ini hanya beberapa token/detik, jadi varian ini tidak bisa di-deploy
  ke tier gratis mana pun yang tanpa GPU — lihat [Varian implementasi](#varian-implementasi).
- **8 tool berada di batas atas kemampuan model 1.7B.** Ini titik paling rapuh
  arsitektur ini dan yang paling patut diperhatikan sebelum menambah tool.
- **`escalate_to_human` hanya mencatat ke database.** Notifikasi nyata (email/WhatsApp
  ke admin) belum diimplementasikan.
- **Kepatuhan eskalasi model belum 100%.** Sisanya ditangani jaring pengaman di
  kode, bukan diklaim beres. Pada model 1.7B jaring pengaman ini justru lebih
  sering terpakai daripada di varian API.
- **Streaming belum ada.** Endpoint mengembalikan jawaban utuh; untuk UX chat yang
  lebih responsif, SSE bisa ditambahkan.
- **Composer menambah satu panggilan LLM per giliran.** Itu harga yang dibayar
  untuk groundedness. Kalau latensi jadi masalah, composer bisa dibuat bersyarat
  (hanya jalan saat ada tool call), tapi jalur jawaban jadi bercabang dua.
- **Kualitas bahasa Indonesia Qwen3-1.7B di bawah model besar.** Jawaban benar
  secara fakta belum tentu terdengar luwes. Yang dijaga di sini groundedness-nya,
  bukan gaya bahasanya.

## Varian implementasi

Repo ini punya dua branch yang menjalankan produk yang sama di atas skema, tool,
prompt guardrail, dataset eval, dan test yang identik — yang berbeda hanya
penyedia LLM-nya.

| Branch | LLM | Biaya | Bisa di-deploy gratis? |
|---|---|---|---|
| `chatbot-claude-api` | Claude Haiku 4.5 lewat Claude API | Per token | Ya — inferensi di sisi penyedia, host cukup CPU kecil |
| `chatbot-local-llm` (branch ini) | Qwen3-1.7B lewat Ollama, dua tahap | Nol biaya API | Tidak — butuh GPU, dijalankan lokal |

Perbedaan biaya dan deployability itu bukan detail teknis; itu inti trade-off
yang dibandingkan project ini. Varian lokal menghilangkan biaya per token dan
membuat seluruh data pembeli tidak pernah meninggalkan mesin, dengan bayaran
akurasi pemilihan tool yang lebih rendah dan kebutuhan GPU.

### Titik sentuh antar-varian

README lama mengklaim hanya dua berkas yang berbeda. Klaim itu meleset. Daftar
sebenarnya:

| Berkas | Perbedaan |
|---|---|
| `app/dependencies.py` | `get_llm()` + `get_composer_llm()` mengembalikan `Ollama`, plus `probe_llm_ready()` |
| `app/config.py`, `.env.example` | Setelan Ollama menggantikan kredensial API |
| `app/services/composer.py`, `app/prompts/composer.py` | Tahap kedua; tidak ada di varian API |
| `app/services/chatbot.py` | Memanggil composer, anotasi LLM jadi netral penyedia |
| `app/tools/registry.py`, `app/models/chat.py` | `ToolObservation`: hasil tool utuh untuk composer |
| `app/utils/errors.py`, `app/api/chat/routes.py` | Taksonomi error Ollama menggantikan error `anthropic` |
| `app/utils/text.py` | Pembersih blok `<think>`; tidak diperlukan varian API |
| `app/evals/` | Penilai RAGAS + DeepEval; belum ada di varian API |
| `scripts/smoke_llm.py` | Gerbang tiga lapis termasuk probe tool calling |
| `requirements.txt`, `requirements-eval.txt` | `llama-index-llms-ollama` + `ollama` menggantikan `anthropic`; dependency penilai di venv terpisah |

Yang **tidak** berubah: 28 tabel dan seluruh migrasi, 4 view + 4 RPC, delapan
tool beserta deskripsinya, jaring pengaman eskalasi, dataset eval 41 kasus, dan
cara skoringnya. Lapis penilaian RAGAS dan DeepEval memakai trace yang formatnya
netral penyedia, jadi varian API bisa memakainya tanpa perubahan begitu jurinya
disambungkan.

### Pindah branch

`.env` tidak ikut di-commit, jadi ia tidak berpindah bersama branch. Kredensial
varian API disimpan di `.env.claude-api` (ikut di-gitignore) saat branch ini
dibuat; salin kembali ke `.env` sebelum menjalankan `chatbot-claude-api`.

## Kontributor

- **Arya Eka Septia Putra** — pemilik dan pengarah project
- **Claude** (Anthropic, model Opus 5) — implementasi kode, desain skema,
  eval harness, dan penulisan dokumentasi, dijalankan lewat Claude Code

Setiap commit di project ini mencantumkan Claude sebagai co-author.
