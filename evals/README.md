# Eval Harness

Dataset ini menguji satu klaim inti project: **agent dengan 8 tool di atas 28 tabel
tetap memilih sumber data yang benar, dan tidak mengarang saat data tidak ada.**

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

## Metrik

- **Akurasi pemilihan tool** — target ≥ 90%
- **Groundedness** — target 100% pada klaim stok, harga, dan status pesanan
- **Rata-rata tool call per pertanyaan** — proksi efisiensi biaya; naik tajam berarti agent bingung

## Menjalankan

```bash
python scripts/run_eval.py                 # semua kasus
python scripts/run_eval.py --only stock    # hanya kasus stok
```

Laporan lengkap tersimpan di `outputs/eval_report.json`.

## Catatan

Kasus yang menyebut SKU spesifik (`KAO-0001`, `HOO-0006`) dan nomor pesanan
(`INV-2026-000006`) bergantung pada `scripts/seed_database.py` dengan seed 42.
Kalau seed diubah, sesuaikan nilai-nilai itu — `seed_database.py` mencetak data
acuan di akhir proses untuk memudahkan.

Tiap kali eval dijalankan, API Claude benar-benar dipanggil sebanyak jumlah kasus,
jadi ada biaya nyata. Pakai `--only` saat iterasi.
