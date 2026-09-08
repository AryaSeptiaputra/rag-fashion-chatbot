/* Layar chat: gelembung percakapan, sumber jawaban, dan meter biaya.
 *
 * Strip metadata di bawah tiap jawaban adalah bagian yang paling membedakan
 * demo ini: sumber jawabannya disebut sampai halaman, dan biayanya ditampilkan
 * apa adanya alih-alih disembunyikan.
 */

import { ApiError, buatSesi, tanya } from "./api.js";
import { avatar, el, kosongkan, usd } from "./dom.js";
import { bahasa, t } from "./i18n.js";
import { perbaruiMeter, simpan, state, tambahPesan } from "./state.js";

let sedangMengirim = false;

/** Gambar ulang seluruh transkrip dari state. */
export function renderThread() {
  const wadah = kosongkan(document.getElementById("thread"));
  for (const pesan of state.messages) {
    wadah.append(pesan.role === "user" ? gelembungUser(pesan) : gelembungGaya(pesan));
  }
  gulirKeBawah();
}

/** Perbarui meter jatah dan anggaran di sidebar. */
export function renderMeter() {
  const { quota, budget } = state;

  const teksKuota = document.getElementById("teks-kuota");
  const pips = kosongkan(document.getElementById("pips-kuota"));
  if (quota) {
    teksKuota.textContent = t("meter.dariTotal", quota.remaining, quota.limit);
    for (let i = 0; i < quota.limit; i += 1) {
      pips.append(
        el("span", { class: i < quota.remaining ? "pip pip--used" : "pip" }),
      );
    }
  }

  const teksAnggaran = document.getElementById("teks-anggaran");
  const bar = document.getElementById("bar-anggaran");
  const catatan = document.getElementById("catatan-anggaran");
  if (budget) {
    const sisaPersen = Math.max(100 - budget.percent_used, 0);
    teksAnggaran.textContent = t("meter.persen", sisaPersen);
    bar.style.width = `${budget.percent_used}%`;
    const perGiliran = 0.005;
    const kira = Math.max(Math.floor(budget.remaining_usd / perGiliran), 0);
    catatan.textContent = `${t("meter.sisaJawaban", kira)} · $${usd(
      budget.spent_usd,
    )} / $${usd(budget.limit_usd)}`;
  }

  const sisa = document.getElementById("sisa-pertanyaan");
  if (quota) {
    sisa.textContent =
      quota.remaining > 0 ? t("sisa.pertanyaan", quota.remaining) : t("sisa.habis");
  }

  document.getElementById("pita-contoh").hidden = !state.stub;
  const chunk = document.getElementById("jumlah-chunk");
  if (chunk && state.faqChunks) chunk.textContent = `${state.faqChunks} potongan`;
}

/**
 * Kirim satu pertanyaan ke server dan gambar jawabannya.
 *
 * @param {string} teks Pertanyaan pembeli.
 */
export async function kirim(teks) {
  const isi = teks.trim();
  if (!isi || sedangMengirim) return;

  sedangMengirim = true;
  kuncikomposer(true);
  tambahPesan({ role: "user", content: isi });
  renderThread();

  const menunggu = tampilkanMengetik();

  try {
    if (!state.sessionId) await pastikanSesi();

    const jawaban = await tanya({
      session_id: state.sessionId,
      message: isi,
      language: bahasa(),
    });

    perbaruiMeter(jawaban);
    tambahPesan({
      role: "assistant",
      content: jawaban.answer,
      mode: jawaban.mode,
      citations: jawaban.citations || [],
      costUsd: jawaban.cost_usd,
      latencyMs: jawaban.latency_ms,
      stub: jawaban.stub,
    });
  } catch (galat) {
    await tanganiGalat(galat);
  } finally {
    menunggu.remove();
    sedangMengirim = false;
    kuncikomposer(false);
    renderThread();
    renderMeter();
  }
}

/** Buat sesi baru; jatah pengunjung TIDAK ikut direset. */
export async function pastikanSesi() {
  const sesi = await buatSesi();
  state.sessionId = sesi.session_id;
  perbaruiMeter(sesi);
  simpan();
}

async function tanganiGalat(galat) {
  if (!(galat instanceof ApiError)) {
    tambahPesan({ role: "assistant", error: true, content: t("galat.umum") });
    return;
  }

  // Sesi hilang karena server restart: terbitkan yang baru diam-diam supaya
  // pengunjung tinggal mengirim ulang, bukan menemui jalan buntu.
  if (galat.kode === "sesi_tidak_dikenali") {
    try {
      await pastikanSesi();
    } catch {
      // Diabaikan; pesannya tetap ditampilkan di bawah.
    }
  }

  const kunci = `galat.${galat.kode}`;
  const pesan = t(kunci);
  tambahPesan({
    role: "assistant",
    error: true,
    content: pesan === kunci ? t("galat.umum") : pesan,
    resetsAt: galat.resets_at,
  });
}

function gelembungUser(pesan) {
  return el("div", {
    class: "turn turn--user",
    children: [el("div", { class: "bubble", text: pesan.content })],
  });
}

function gelembungGaya(pesan) {
  const badan = el("div", { class: "turn__body" });
  badan.append(el("div", { class: "bubble", text: pesan.content }));

  if (!pesan.error) {
    badan.append(stripMeta(pesan));
    const kutipan = kartuKutipan(pesan.citations);
    if (kutipan) badan.append(kutipan);
  }

  return el("div", {
    class: pesan.error ? "turn turn--error" : "turn",
    children: [avatar(34), badan],
  });
}

function stripMeta(pesan) {
  const mode = pesan.mode || "tanpa_sumber";
  const gratis = !pesan.costUsd;

  const bagian = [
    el("span", {
      class: `badge badge--${mode}`,
      children: [el("i"), el("span", { text: t(`badge.${mode}`) })],
    }),
  ];

  if (pesan.latencyMs) {
    bagian.push(
      el("span", { text: t("meta.detik", (pesan.latencyMs / 1000).toFixed(1)) }),
    );
  }
  bagian.push(
    el("span", {
      class: gratis ? "cost cost--free" : "cost",
      text: gratis ? t("meta.gratis") : t("meta.biaya", usd(pesan.costUsd)),
    }),
  );

  return el("div", { class: "meta", children: bagian });
}

function kartuKutipan(kutipan) {
  if (!kutipan?.length) return null;

  const daftar = el("div", { class: "cites__list" });
  for (const satu of kutipan) {
    const persen = satu.match_percent ?? 0;
    daftar.append(
      el("div", {
        class: "cite",
        children: [
          el("span", {
            class: persen >= 70 ? "cite__pct" : "cite__pct cite__pct--weak",
            text: t("cites.cocok", persen),
          }),
          el("div", {
            class: "cite__text",
            children: [
              el("b", {
                text: satu.page
                  ? `${satu.file_name} · ${t("cites.halaman", satu.page)}`
                  : satu.file_name,
              }),
              el("span", { class: "cite__snippet", text: satu.snippet || "" }),
            ],
          }),
        ],
      }),
    );
  }

  const rincian = el("details", { class: "cites", attrs: { open: "" } });
  rincian.append(el("summary", { text: t("cites.judul") }), daftar);
  return rincian;
}

function tampilkanMengetik() {
  const simpul = el("div", {
    class: "turn",
    children: [
      avatar(34),
      el("div", {
        class: "bubble typing",
        children: [el("i"), el("i"), el("i")],
      }),
    ],
  });
  document.getElementById("thread").append(simpul);
  gulirKeBawah();
  return simpul;
}

function kuncikomposer(terkunci) {
  document.getElementById("pesan").disabled = terkunci;
  document.getElementById("kirim").disabled = terkunci;
}

function gulirKeBawah() {
  const thread = document.getElementById("thread");
  thread.scrollTop = thread.scrollHeight;
}
