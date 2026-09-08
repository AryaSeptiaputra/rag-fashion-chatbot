/* Pembungkus fetch ke API demo.
 *
 * Backend mengirim kode mesin di detail error, bukan kalimat untuk pengguna,
 * jadi lapisan ini hanya menormalkan bentuknya. Kalimatnya disusun i18n.js.
 */

const BASIS = "/api/v1";
const TIMEOUT_CHAT = 120_000;
const TIMEOUT_UMUM = 20_000;

/** Kegagalan permintaan yang sudah dinormalkan bentuknya. */
export class ApiError extends Error {
  /**
   * @param {number} status Kode status HTTP; 0 untuk kegagalan jaringan.
   * @param {string} kode Kode mesin dari backend.
   * @param {object} [ekstra] Data tambahan seperti resets_at.
   */
  constructor(status, kode, ekstra = {}) {
    super(`${status} ${kode}`);
    this.status = status;
    this.kode = kode;
    Object.assign(this, ekstra);
  }
}

async function minta(path, { method = "GET", body, timeout = TIMEOUT_UMUM } = {}) {
  const pembatal = new AbortController();
  const jam = setTimeout(() => pembatal.abort(), timeout);

  let respons;
  try {
    respons = await fetch(BASIS + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: pembatal.signal,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "koneksi");
  } finally {
    clearTimeout(jam);
  }

  const isi = await respons.json().catch(() => ({}));
  if (respons.ok) return isi;

  throw bacaGalat(respons.status, isi);
}

/**
 * Ubah badan error jadi ApiError.
 *
 * detail bisa berbentuk objek ber-kode (pengaman kuota) atau string biasa
 * (pemetaan error Claude yang sudah ada sebelumnya). Keduanya harus ditangani.
 *
 * @param {number} status Kode status HTTP.
 * @param {object} isi Badan respons.
 * @returns {ApiError} Galat yang sudah dinormalkan.
 */
function bacaGalat(status, isi) {
  const detail = isi?.detail;
  if (detail && typeof detail === "object") {
    const { code, ...ekstra } = detail;
    return new ApiError(status, code || "umum", ekstra);
  }
  const kode = status === 503 ? "belumSiap" : status >= 500 ? "layanan" : "umum";
  return new ApiError(status, kode, { pesan: typeof detail === "string" ? detail : "" });
}

/** @returns {Promise<object>} Sesi baru beserta jatah dan anggarannya. */
export function buatSesi() {
  return minta("/session", { method: "POST" });
}

/** @returns {Promise<object>} Hasil pemanasan seluruh komponen berat. */
export function panaskan() {
  return minta("/warmup", { method: "POST", timeout: 180_000 });
}

/** @returns {Promise<object>} Data acuan halaman panduan. */
export function ambilContoh() {
  return minta("/demo/facts");
}

/**
 * Kirim satu pertanyaan.
 *
 * @param {object} muatan session_id, message, dan language.
 * @returns {Promise<object>} Jawaban beserta sumber, biaya, dan sisa jatah.
 */
export function tanya(muatan) {
  return minta("/chat", { method: "POST", body: muatan, timeout: TIMEOUT_CHAT });
}
