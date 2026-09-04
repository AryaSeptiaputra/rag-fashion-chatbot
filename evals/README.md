# Eval Harness

Tiga lapis pengukuran, dari yang paling murah ke paling mahal:

| Lapis | Dijalankan oleh | Butuh juri LLM? | Yang diukur |
|---|---|---|---|
| Akurasi pemilihan tool | `scripts/run_eval.py` | Tidak | Agent memilih sumber data yang benar |
| Mutu jawaban akhir | RAGAS, lewat notebook | Ya | Jawaban bersandar pada bukti dan menjawab yang ditanya |
| Mutu retrieval | DeepEval, lewat notebook | Ya (kecuali `section_hit_rate`) | Potongan yang tepat terambil, dan berperingkat benar |

Lapis pertama menguji klaim inti project: **agent dengan 8 tool di atas 28 tabel tetap
memilih sumber data yang benar, dan tidak mengarang saat data tidak ada.** Dua lapis
berikutnya menguji hal yang tidak terjangkau jejak tool call: apakah kalimat yang
sampai ke pembeli benar-benar bersandar pada bukti, dan apakah buktinya sendiri sudah
yang tepat.

## Dua dataset

| Berkas | Isi | Dipakai untuk |
|---|---|---|
| `dataset.jsonl` | 41 kasus, seluruh permukaan 8 tool | Akurasi tool + mutu jawaban |
| `retrieval.jsonl` | 16 kasus FAQ, dua per seksi dokumen | Mutu retrieval |

## Cara kerja

`scripts/run_eval.py` menjalankan tiap pertanyaan lewat `ChatbotService` yang sama
dengan yang dipakai API, lalu menilai dari **jejak tool call yang benar-benar terjadi**
(`ToolCallRecorder`, dipersistensi ke tabel `message_tool_calls`) — bukan dari menebak
isi teks jawaban.

## Format satu baris

```json
{
  "id": "stock-01",
  "question": "KAO-0001 size L masih ada ga?",
  "expect_tools": ["check_stock"],
  "forbid_tools": [],
  "must_not_contain": ["mungkin masih", "sepertinya ada"],
  "history": [],
  "note": "keterangan opsional"
}
```

| Field | Arti |
|---|---|
| `expect_tools` | Tool yang **wajib** terpanggil. Kosong berarti tidak ada kewajiban. |
| `forbid_tools` | Tool yang **tidak boleh** terpanggil (mis. `track_order` sebelum verifikasi). |
| `must_not_contain` | Frasa yang tidak boleh muncul di jawaban — penangkap halusinasi dan bahasa ragu. |
| `history` | Pertanyaan yang dikirim lebih dulu di sesi yang sama, untuk menguji kesadaran konteks. |
| `reference` | Jawaban acuan. Membuka metrik `FactualCorrectness`, `ContextualPrecision`, dan `ContextualRecall`. |
| `reference_sections` | Judul seksi FAQ yang seharusnya terambil, mis. `["Pengiriman"]`. |

`reference_sections` menyebut **judul seksi**, bukan menempelkan teks potongan.
`CHUNK_SIZE` dan `CHUNK_OVERLAP` bisa berubah kapan saja, dan acuan yang menempel pada
teks potongan akan basi diam-diam setiap kali ingestion disetel ulang. Pemetaan seksi
ke teks dilakukan saat menilai, dengan mem-parse heading `##` dokumen sumbernya.

Acuan hanya ditulis untuk kasus yang jawabannya sepenuhnya bersumber dari dokumen FAQ.
Kasus stok, promo, dan pesanan tidak diberi acuan: jawabannya bergantung pada isi
database yang berubah tiap seed, jadi acuan tetap justru akan salah.

## Metrik

### Lapis 1 — dari jejak tool call, tanpa juri

- **Akurasi pemilihan tool** — target ≥ 90%
- **Groundedness** — target 100% pada klaim stok, harga, dan status pesanan
- **Rata-rata tool call per pertanyaan** — proksi latensi; naik tajam berarti agent bingung

### Lapis 2 — mutu jawaban akhir (RAGAS)

Konteks pembandingnya **keluaran seluruh tool**, bukan potongan FAQ. `AnswerComposer`
memang hanya boleh bersandar pada hasil tool, jadi itulah bukti yang sah. Menilai
jawaban stok terhadap potongan FAQ akan menuduhnya berhalusinasi padahal datanya
benar, hanya datang dari Postgres alih-alih dari vector store.

- **Faithfulness** — ada klaim yang tidak didukung bukti?
- **AnswerRelevancy** — jawabannya menjawab yang ditanya? Butuh model embedding juri.
- **FactualCorrectness** — cocok dengan acuan? Hanya untuk kasus yang punya `reference`.

### Lapis 3 — mutu retrieval (DeepEval)

Konteksnya hanya potongan FAQ dari vector store.

- **ContextualRelevancy** — berapa bagian potongan yang benar-benar relevan?
- **ContextualRecall** — informasi yang dibutuhkan acuan berhasil terambil?
- **ContextualPrecision** — potongan relevan berperingkat lebih tinggi?
- **section_hit_rate** — berapa bagian potongan yang berasal dari seksi yang ditunjuk
  acuan. **Dihitung deterministik, tanpa juri**, jadi ia tetap bisa dipercaya justru
  saat skor juri terlihat mencurigakan.

## Menjalankan

### Lapis 1, lokal

```bash
python scripts/run_eval.py                 # semua kasus
python scripts/run_eval.py --only stock    # hanya kasus stok
```

Laporan tersimpan di `outputs/eval_report.json`, dan trace untuk lapis 2 dan 3 di
`outputs/eval_trace.jsonl`. Keduanya ditulis di run yang sama: menjalankan chatbot dua
kali membuang waktu dan menghasilkan jawaban yang berbeda, sehingga penilaiannya tidak
lagi mengacu pada jawaban yang sama.

### Lapis 2 dan 3, di Colab

`notebooks/00_eval_quality_colab.ipynb` menjalankan semuanya end-to-end pada runtime
T4: memasang Ollama, menarik model, membangun index FAQ, menjalankan kedua dataset,
lalu menilai dengan RAGAS dan DeepEval. Hasil akhirnya `outputs/quality_report.json`.

Model juri `qwen2.5:7b-instruct`, terpisah dari `qwen3:1.7b` yang diuji. Model yang
menilai jawabannya sendiri bukan pengukuran.

Untuk menjalankannya lokal, dependency penilai ada di venv terpisah:

```bash
python -m venv .venv-eval
.venv-eval\Scripts\pip install -r requirements-eval.txt
```

## Membaca angka lapis 2 dan 3

**Jurinya model 7B lokal.** Angkanya sah untuk membandingkan antar-run dengan juri yang
sama — sebelum dan sesudah mengubah prompt, chunking, atau `RETRIEVAL_TOP_K`. Angka ini
**tidak** sebanding dengan skor RAGAS yang dipublikasikan di internet, yang hampir
selalu memakai juri kelas GPT-4.

**Korpus FAQ baru 9 potongan dari satu dokumen contoh.** Metrik retrieval di atas 16
pertanyaan membuktikan pipeline-nya bekerja, bukan bahwa retrieval-nya bagus pada
korpus produksi.

**Gagal-nilai bukan skor nol.** `unscored_total` menghitung kasus yang jurinya gagal
mengeluarkan JSON sesuai skema; kasus itu tidak ikut rata-rata. Kalau angkanya besar,
yang bermasalah jurinya, bukan sistem yang diuji.

## Catatan

Kasus yang menyebut SKU spesifik (`KAO-0001`, `HOO-0006`) dan nomor pesanan
(`INV-2026-000006`) bergantung pada `scripts/seed_database.py` dengan seed 42.
Kalau seed diubah, sesuaikan nilai-nilai itu — `seed_database.py` mencetak data
acuan di akhir proses untuk memudahkan.

Tiap kali eval dijalankan, model lokal benar-benar dipanggil minimal dua kali per
kasus (agent + composer), jadi run penuh memakan waktu puluhan menit di GPU laptop.
Pakai `--only` saat iterasi.
