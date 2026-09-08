/* Pembantu DOM.
 *
 * Satu aturan keras di berkas ini: teks apa pun yang berasal dari model atau
 * dari database dipasang lewat textContent, tidak pernah innerHTML. Jawaban
 * LLM bisa memuat markup, dan begitu ia dirender sebagai HTML, halaman ini
 * jadi celah XSS untuk siapa pun yang bisa mengetik ke kotak chat.
 */

/**
 * Bangun satu elemen.
 *
 * @param {string} tag Nama tag.
 * @param {object} [opsi] class, text, html, attrs, dan children.
 * @returns {HTMLElement} Elemen yang sudah terisi.
 */
export function el(tag, opsi = {}) {
  const simpul = document.createElement(tag);
  if (opsi.class) simpul.className = opsi.class;
  if (opsi.text !== undefined) simpul.textContent = opsi.text;
  // html hanya untuk markup yang kita tulis sendiri di berkas ini, tidak
  // pernah untuk isi yang datang dari jaringan.
  if (opsi.html !== undefined) simpul.innerHTML = opsi.html;
  for (const [nama, nilai] of Object.entries(opsi.attrs || {})) {
    if (nilai !== null && nilai !== undefined) simpul.setAttribute(nama, String(nilai));
  }
  for (const anak of opsi.children || []) {
    if (anak) simpul.append(anak);
  }
  return simpul;
}

/**
 * Kosongkan isi satu elemen.
 *
 * @param {HTMLElement} simpul Elemen yang dikosongkan.
 * @returns {HTMLElement} Elemen yang sama.
 */
export function kosongkan(simpul) {
  simpul.replaceChildren();
  return simpul;
}

/**
 * Pasang wajah asisten ke seluruh penampung yang menandainya.
 *
 * @param {ParentNode} [akar] Batas pencarian.
 */
export function pasangWajah(akar = document) {
  const template = document.getElementById("tpl-wajah");
  for (const wadah of akar.querySelectorAll("[data-wajah]")) {
    if (wadah.querySelector("svg")) continue;
    wadah.prepend(template.content.cloneNode(true));
  }
}

/**
 * Buat elemen avatar berisi wajah asisten.
 *
 * @param {number} ukuran Sisi avatar dalam piksel.
 * @returns {HTMLElement} Avatar siap pasang.
 */
export function avatar(ukuran = 34) {
  const wadah = el("div", {
    class: "avatar",
    attrs: { style: `width:${ukuran}px;height:${ukuran}px` },
  });
  wadah.append(document.getElementById("tpl-wajah").content.cloneNode(true));
  return wadah;
}

/**
 * Format dolar dengan empat desimal.
 *
 * @param {number} nilai Biaya dalam USD.
 * @returns {string} Angka yang siap ditampilkan.
 */
export function usd(nilai) {
  return Number(nilai || 0).toFixed(4);
}
