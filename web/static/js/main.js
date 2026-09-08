/* Titik masuk demo.
 *
 * Satu dokumen, dua tampilan, dengan location.hash sebagai sumber kebenaran --
 * sehingga tombol back peramban bekerja dan layar chat bisa ditautkan.
 *
 * Pemanasan dimulai bersamaan dengan render halaman panduan. Proses API memuat
 * model embedding ratusan megabita saat pertama kali dipakai; membiarkannya
 * berjalan selagi pengunjung membaca berarti 30-90 detik itu tidak pernah jadi
 * layar kosong.
 */

import { panaskan } from "./api.js";
import { kirim, pastikanSesi, renderMeter, renderThread } from "./chat.js";
import { muatContoh, pasangHero, renderPanduan, saatChipDiklik } from "./guide.js";
import { bahasaBawaan, t, terapkanBahasa } from "./i18n.js";
import { muat, simpan, state } from "./state.js";

/**
 * Pindah ke satu tampilan dan sinkronkan hash-nya.
 *
 * @param {string} view "panduan" atau "chat".
 */
function tampilkan(view) {
  const tujuan = view === "chat" ? "chat" : "panduan";
  state.view = tujuan;
  document.body.dataset.view = tujuan;
  if (location.hash.slice(1) !== tujuan) location.hash = tujuan;
  simpan();

  if (tujuan === "chat") {
    renderThread();
    renderMeter();
    document.getElementById("pesan").focus();
  } else {
    renderPanduan();
  }
}

/**
 * Buka layar chat, opsional langsung mengirim satu pertanyaan.
 *
 * @param {string} [pertanyaanAwal] Teks dari chip yang diklik di panduan.
 */
async function keChat(pertanyaanAwal) {
  if (!state.sessionId) {
    try {
      await pastikanSesi();
    } catch {
      // Sesi dicoba lagi saat pesan pertama dikirim.
    }
  }
  tampilkan("chat");
  if (pertanyaanAwal) await kirim(pertanyaanAwal);
}

/** Panaskan komponen berat di latar dan tampilkan hasilnya di pil status. */
async function jalankanPemanasan() {
  const pil = document.getElementById("status-panduan");
  const label = pil.querySelector("span:last-child");

  try {
    const hasil = await panaskan();
    state.faqChunks = hasil.faq_chunks;
    state.stub = hasil.stub;
    if (hasil.budget) state.budget = hasil.budget;
    simpan();

    pil.dataset.state = hasil.ready ? "siap" : "gagal";
    label.textContent = t(hasil.ready ? "status.siap" : "status.gagal");
  } catch {
    pil.dataset.state = "gagal";
    label.textContent = t("status.gagal");
  }
  renderMeter();
}

/** Mulai obrolan baru tanpa mengembalikan jatah pengunjung. */
async function obrolanBaru() {
  // Jatah sengaja TIDAK direset di sini. Kalau ia ikut direset, seluruh
  // pembatasan bisa dielakkan hanya dengan menekan tombol ini berulang kali.
  state.messages = [];
  state.sessionId = null;
  simpan();
  renderThread();

  try {
    await pastikanSesi();
  } catch {
    // Dicoba lagi saat pesan berikutnya dikirim.
  }
  renderMeter();
}

function pasangPeristiwa() {
  document.getElementById("mulai-demo").addEventListener("click", () => keChat());
  document
    .getElementById("kembali-panduan")
    .addEventListener("click", () => tampilkan("panduan"));
  document.getElementById("obrolan-baru").addEventListener("click", obrolanBaru);

  document.getElementById("composer").addEventListener("submit", (peristiwa) => {
    peristiwa.preventDefault();
    const kotak = document.getElementById("pesan");
    const teks = kotak.value;
    kotak.value = "";
    kirim(teks);
  });

  for (const tombol of document.querySelectorAll(".langswitch button")) {
    tombol.addEventListener("click", () => {
      state.language = tombol.dataset.lang;
      simpan();
      terapkanBahasa(state.language);
      renderPanduan();
      renderThread();
      renderMeter();
    });
  }

  saatChipDiklik((teks) => keChat(teks));

  window.addEventListener("hashchange", () => {
    tampilkan(location.hash.slice(1) || "panduan");
  });
}

function mulai() {
  muat();
  state.language = state.language || bahasaBawaan();
  terapkanBahasa(state.language);

  pasangHero();
  pasangPeristiwa();
  tampilkan(location.hash.slice(1) || state.view || "panduan");

  jalankanPemanasan();
  muatContoh();
}

mulai();
