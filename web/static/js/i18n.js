/* Kamus dua bahasa dan penerapannya ke DOM.
 *
 * Seluruh prosa untuk pengguna hidup di sini, termasuk pesan kegagalan.
 * Backend sengaja hanya mengirim kode mesin -- ia tidak tahu bahasa apa yang
 * sedang dipilih, dan tidak perlu tahu.
 */

export const KAMUS = {
  id: {
    tagline: "Tampil Percaya Diri Setiap Hari",
    "notice.dummy":
      "Seluruh data di demo ini fiktif — merek, katalog, stok, pesanan, sampai dokumen kebijakannya dibuat khusus untuk peragaan. Tidak ada toko sungguhan di baliknya.",
    "status.memanaskan": "menyiapkan Gaya…",
    "status.siap": "Gaya sudah siap menjawab",
    "status.gagal": "sebagian layanan belum siap",

    "hero.judul": "Halo! Aku Gaya, asisten belanja GAYA.ID.",
    "hero.teks":
      "Kenalan sebentar yuk, biar pertanyaan pertamamu langsung ketemu jawabannya. Aku tidak menebak — semua yang aku bilang aku ambil dari dokumen resmi toko atau dari database yang aku cek saat itu juga.",

    "bisa.judul": "Aku bisa bantu soal ini",
    "bisa.hint": "Pertanyaan bertanda titik ini gratis — tidak mengurangi jatahmu",

    "sumber.judul": "Jawabanku datang dari dua tempat",
    "sumber.teks":
      "Di setiap jawaban nanti aku tulis aku ambilnya dari mana — sampai nama berkas dan halamannya. Kalau dokumen dan database berselisih, yang aku pakai adalah database.",
    "sumber.dok.judul": "Dokumen resmi toko",
    "sumber.dok.teks": "Empat berkas, isinya tetap sampai diperbarui.",
    "sumber.db.judul": "Database toko",
    "sumber.db.teks": "Aku cek saat kamu tanya, bukan dari catatan lama.",

    "contoh.judul": "Contoh yang bisa kamu salin",
    "contoh.teks":
      "Nomor-nomor ini asli dari database demo. Pakai salah satunya ya — kalau kamu karang sendiri, aku memang tidak akan menemukan apa pun.",
    "contoh.catatan":
      "Kode promo di atas sengaja berbeda status. Menanyakan yang kedaluwarsa atau yang belum mulai adalah cara tercepat melihat aku menolak mengarang.",

    "batas.judul": "Yang belum bisa aku bantu",
    "kecuali.judul": "Dua dokumen sengaja tidak aku baca",
    "kecuali.teks":
      "Katalog grosir dan laporan kinerja kuartalan tidak dimasukkan ke indeks yang bisa aku jangkau. Laporan itu bertanda INTERNAL USE ONLY — isinya omzet, margin per produk, dan target penjualan.",

    "mulai.judul": "Sebelum mulai, tiga hal kecil",
    "mulai.kuota": "pertanyaan untuk satu hari",
    "mulai.biaya":
      "tiap jawabanku memakai saldo AI sungguhan — biayanya aku tampilkan apa adanya",
    "mulai.gratis": "pertanyaan bertanda titik gratis, tidak mengurangi jatahmu",
    "mulai.tombol": "Yuk, mulai ngobrol",
    "mulai.catatan": "Jatahmu baru mulai dihitung setelah tombol ini ditekan.",

    "footer.kiri": "Demo portofolio · Claude Haiku 4.5 · ChromaDB + Supabase",
    "footer.kanan": "Dokumen dan katalognya fiktif, dibuat khusus untuk demo ini",

    "chat.peran": "Asisten belanja GAYA.ID",
    "chat.siap": "Gaya siap membantu",
    "chat.sumber": "Aku ambil jawaban dari",
    "chat.sumber.dok": "Dokumen resmi",
    "chat.sumber.db": "Database toko",
    "chat.sumber.db.ket": "terhubung, dicek saat ditanya",
    "chat.obrolanBaru": "Mulai obrolan baru",
    "chat.catatanBiaya":
      "Biaya di bawah tiap jawaban dihitung dari pemakaian asli, bukan perkiraan.",
    "chat.lihatPanduan": "Lihat panduan",
    "chat.placeholder": "Tanya apa saja soal produk, stok, ukuran, ongkir…",
    "chat.disclaimer": "Katalog dan dokumennya fiktif, dibuat khusus untuk demo",

    "meter.kuota": "Sisa pertanyaanmu",
    "meter.anggaran": "Jatah demo hari ini",
    "meter.sisaJawaban": (n) => `cukup untuk kira-kira ${n} jawaban lagi`,
    "meter.dariTotal": (sisa, total) => `${sisa} dari ${total}`,
    "meter.persen": (p) => `masih ${p}%`,

    "stub.label": "Mode contoh",
    "stub.teks":
      "Jawaban di bawah diambil dari contoh yang ditulis di muka — belum memanggil AI sungguhan.",

    "badge.dokumen": "Aku baca dari dokumen",
    "badge.database": "Aku cek langsung ke database",
    "badge.campuran": "Dokumen dan database",
    "badge.tanpa_sumber": "Dijawab langsung",
    "meta.gratis": "gratis",
    "meta.biaya": (usd) => `biaya $${usd}`,
    "meta.detik": (d) => `${d} detik`,
    "cites.judul": "Halaman yang aku baca",
    "cites.cocok": (p) => `cocok ${p}%`,
    "cites.halaman": (n) => `halaman ${n}`,

    "sisa.pertanyaan": (n) => `Sisa ${n} pertanyaan hari ini`,
    "sisa.habis": "Jatah pertanyaanmu hari ini sudah habis",

    "galat.kuota_pengunjung_habis":
      "Wah, jatah pertanyaanmu hari ini sudah terpakai semua. Pertanyaan contoh di panduan tetap bisa dicoba ya.",
    "galat.kuota_ip_habis":
      "Jaringan ini sudah memakai jatah hariannya. Coba lagi besok ya.",
    "galat.budget_harian_habis":
      "Anggaran demo hari ini sudah habis. Coba lagi besok ya, Kak.",
    "galat.sesi_tidak_dikenali":
      "Sesi ini sudah tidak dikenali. Aku buatkan yang baru ya — coba kirim ulang pertanyaannya.",
    "galat.terlalu_sering": "Pelan-pelan ya, tunggu sebentar lagi.",
    "galat.koneksi": "Koneksi terputus sebelum jawaban selesai. Coba lagi ya.",
    "galat.layanan":
      "Layanan AI atau database tidak bisa dihubungi saat ini. Coba beberapa saat lagi.",
    "galat.belumSiap":
      "Aku belum siap menjawab. Coba buka panduan sebentar lalu kembali lagi.",
    "galat.umum": "Ada yang tidak beres di sisi kami. Coba lagi sebentar lagi.",
  },

  en: {
    tagline: "Confidence, Every Single Day",
    "notice.dummy":
      "Everything in this demo is fictional — the brand, catalogue, stock, orders, and policy documents were all made for the demonstration. There is no real store behind it.",
    "status.memanaskan": "warming Gaya up…",
    "status.siap": "Gaya is ready to answer",
    "status.gagal": "some services are not ready",

    "hero.judul": "Hi! I'm Gaya, the GAYA.ID shopping assistant.",
    "hero.teks":
      "Let's get acquainted first, so your very first question lands on an answer. I don't guess — everything I say comes from the store's official documents or from the database I check right at that moment.",

    "bisa.judul": "Here's what I can help with",
    "bisa.hint": "Questions with this dot are free — they don't use your quota",

    "sumber.judul": "My answers come from two places",
    "sumber.teks":
      "Every answer tells you where I got it — down to the file name and page. When a document and the database disagree, the database wins.",
    "sumber.dok.judul": "Official store documents",
    "sumber.dok.teks": "Four files, unchanged until they are re-indexed.",
    "sumber.db.judul": "Store database",
    "sumber.db.teks": "Checked the moment you ask, not from old notes.",

    "contoh.judul": "Examples you can copy",
    "contoh.teks":
      "These come straight from the demo database. Use one of them — if you make one up, I genuinely won't find anything.",
    "contoh.catatan":
      "The promo codes above deliberately have different statuses. Asking about the expired or the not-yet-started one is the fastest way to watch me refuse to make things up.",

    "batas.judul": "What I can't help with yet",
    "kecuali.judul": "Two documents I deliberately don't read",
    "kecuali.teks":
      "The wholesale catalogue and the quarterly performance report are kept out of the index I can reach. That report is marked INTERNAL USE ONLY — it holds revenue, per-product margins, and sales targets.",

    "mulai.judul": "Three small things before we start",
    "mulai.kuota": "questions per day",
    "mulai.biaya":
      "every answer spends real AI credit — I show you the cost as it is",
    "mulai.gratis": "dotted questions are free and don't touch your quota",
    "mulai.tombol": "Let's chat",
    "mulai.catatan": "Your quota only starts counting after you press this.",

    "footer.kiri": "Portfolio demo · Claude Haiku 4.5 · ChromaDB + Supabase",
    "footer.kanan": "The documents and catalogue are fictional, built for this demo",

    "chat.peran": "GAYA.ID shopping assistant",
    "chat.siap": "Gaya is here to help",
    "chat.sumber": "I draw answers from",
    "chat.sumber.dok": "Official documents",
    "chat.sumber.db": "Store database",
    "chat.sumber.db.ket": "connected, checked on demand",
    "chat.obrolanBaru": "Start a new chat",
    "chat.catatanBiaya":
      "The cost under each answer is computed from real usage, not an estimate.",
    "chat.lihatPanduan": "Back to guide",
    "chat.placeholder": "Ask about products, stock, sizing, shipping…",
    "chat.disclaimer": "Catalogue and documents are fictional, built for this demo",

    "meter.kuota": "Questions left",
    "meter.anggaran": "Today's demo budget",
    "meter.sisaJawaban": (n) => `enough for roughly ${n} more answers`,
    "meter.dariTotal": (sisa, total) => `${sisa} of ${total}`,
    "meter.persen": (p) => `${p}% left`,

    "stub.label": "Sample mode",
    "stub.teks":
      "The answers below come from pre-written samples — no real AI call yet.",

    "badge.dokumen": "Read from documents",
    "badge.database": "Checked the database",
    "badge.campuran": "Documents and database",
    "badge.tanpa_sumber": "Answered directly",
    "meta.gratis": "free",
    "meta.biaya": (usd) => `cost $${usd}`,
    "meta.detik": (d) => `${d}s`,
    "cites.judul": "Pages I read",
    "cites.cocok": (p) => `${p}% match`,
    "cites.halaman": (n) => `page ${n}`,

    "sisa.pertanyaan": (n) => `${n} questions left today`,
    "sisa.habis": "You've used today's questions",

    "galat.kuota_pengunjung_habis":
      "You've used all of today's questions. The sample questions on the guide still work though.",
    "galat.kuota_ip_habis":
      "This network has used its daily allowance. Please try again tomorrow.",
    "galat.budget_harian_habis":
      "Today's demo budget is spent. Please come back tomorrow.",
    "galat.sesi_tidak_dikenali":
      "This session is no longer recognised. I've started a new one — send your question again.",
    "galat.terlalu_sering": "Easy there — give it a moment.",
    "galat.koneksi": "The connection dropped before the answer finished. Try again.",
    "galat.layanan":
      "The AI service or the database can't be reached right now. Try again shortly.",
    "galat.belumSiap":
      "I'm not ready yet. Open the guide for a moment, then come back.",
    "galat.umum": "Something went wrong on our side. Try again shortly.",
  },
};

let bahasaAktif = "id";

/**
 * Ambil teks terjemahan.
 *
 * @param {string} kunci Kunci di kamus.
 * @param {...unknown} argumen Argumen untuk kunci yang berupa fungsi.
 * @returns {string} Teks dalam bahasa aktif, atau kuncinya kalau tidak ada.
 */
export function t(kunci, ...argumen) {
  const nilai = KAMUS[bahasaAktif][kunci] ?? KAMUS.id[kunci];
  if (typeof nilai === "function") return nilai(...argumen);
  return nilai ?? kunci;
}

/**
 * @returns {string} Kode bahasa yang sedang dipakai.
 */
export function bahasa() {
  return bahasaAktif;
}

/**
 * Ganti bahasa dan tulis ulang seluruh teks statis di halaman.
 *
 * Transkrip percakapan sengaja tidak ikut diterjemahkan: gelembung lama tetap
 * dalam bahasa saat ia dijawab. Menerjemahkan ulang berarti memanggil model
 * lagi, dan itu memakan saldo untuk sesuatu yang sudah dijawab.
 *
 * @param {string} kode Kode bahasa, "id" atau "en".
 */
export function terapkanBahasa(kode) {
  bahasaAktif = KAMUS[kode] ? kode : "id";
  document.documentElement.lang = bahasaAktif;

  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of document.querySelectorAll("[data-i18n-placeholder]")) {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  }
  for (const tombol of document.querySelectorAll(".langswitch button")) {
    tombol.setAttribute("aria-pressed", String(tombol.dataset.lang === bahasaAktif));
  }
}

/**
 * Tebak bahasa awal dari setelan peramban.
 *
 * @returns {string} "id" untuk peramban berbahasa Indonesia, selain itu "en".
 */
export function bahasaBawaan() {
  return (navigator.language || "id").toLowerCase().startsWith("id") ? "id" : "en";
}
