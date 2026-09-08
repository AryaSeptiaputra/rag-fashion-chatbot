/* State demo di peramban.
 *
 * sessionStorage, bukan localStorage: tab baru berarti demo baru, tapi refresh
 * tidak membuang percakapan. Karena backend menyimpan riwayat per session_id,
 * refresh benar-benar memulihkan konteks -- Gaya masih ingat.
 *
 * Setiap akses dibungkus try/catch: mode penyamaran dan setelan privasi bisa
 * membuat sessionStorage melempar, dan itu tidak boleh mematikan halaman.
 */

const KUNCI = "gaya-demo";
const BATAS_PESAN = 50;

export const state = {
  sessionId: null,
  language: "id",
  view: "panduan",
  messages: [],
  budget: null,
  quota: null,
  stub: false,
  facts: null,
};

/** Baca state yang tersimpan dari sesi peramban sebelumnya. */
export function muat() {
  try {
    const mentah = sessionStorage.getItem(KUNCI);
    if (!mentah) return;
    Object.assign(state, JSON.parse(mentah));
  } catch {
    // Storage rusak atau diblokir; jalan terus dengan state kosong.
  }
}

/** Simpan state supaya bertahan melewati refresh. */
export function simpan() {
  try {
    sessionStorage.setItem(
      KUNCI,
      JSON.stringify({
        sessionId: state.sessionId,
        language: state.language,
        view: state.view,
        messages: state.messages.slice(-BATAS_PESAN),
        budget: state.budget,
        quota: state.quota,
        stub: state.stub,
      }),
    );
  } catch {
    // Tidak bisa menyimpan bukan alasan menggagalkan percakapan.
  }
}

/**
 * Tambahkan satu pesan ke transkrip.
 *
 * @param {object} pesan Pesan yang akan disimpan.
 */
export function tambahPesan(pesan) {
  state.messages.push(pesan);
  if (state.messages.length > BATAS_PESAN) {
    state.messages.splice(0, state.messages.length - BATAS_PESAN);
  }
  simpan();
}

/**
 * Perbarui potret jatah dan anggaran dari respons API.
 *
 * @param {object} sumber Respons yang membawa budget dan quota.
 */
export function perbaruiMeter(sumber) {
  if (sumber?.budget) state.budget = sumber.budget;
  if (sumber?.quota) state.quota = sumber.quota;
  if (typeof sumber?.stub === "boolean") state.stub = sumber.stub;
  simpan();
}
