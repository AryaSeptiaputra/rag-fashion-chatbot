/* Layar panduan: mengajari pengunjung apa yang bisa ditanyakan.
 *
 * Bagian terpentingnya bukan daftar kemampuan, melainkan blok data acuan.
 * Tidak ada pengunjung yang bisa menebak SKU atau nomor pesanan yang sah, dan
 * tanpa itu tiga dari delapan tool mustahil dicoba -- chatbot lalu terlihat
 * bodoh justru ketika ia berperilaku benar dengan menolak mengarang.
 */

import { ambilContoh } from "./api.js";
import { el, kosongkan, pasangWajah } from "./dom.js";
import { bahasa } from "./i18n.js";
import { state } from "./state.js";

const IKON = {
  dokumen: `<path d="M20 12a8 8 0 1 0-3.2 6.4L20 20z"/><path d="M9 10h6"/><path d="M9 14h4"/>`,
  ukuran: `<path d="M4 8h16"/><path d="M4 8v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="m7 8 2-4h6l2 4"/>`,
  kotak: `<path d="M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.73l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>`,
  truk: `<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>`,
};

const KEMAMPUAN = [
  {
    ikon: "dokumen",
    sumber: "dokumen",
    judul: { id: "Retur & garansi", en: "Returns & warranty" },
    teks: {
      id: "Lima jenis garansi, syarat retur, dan siapa yang menanggung ongkirnya.",
      en: "Five warranty types, return conditions, and who pays the shipping.",
    },
    chips: [
      {
        gratis: true,
        teks: {
          id: "Garansi sablon berapa lama?",
          en: "How long is the print warranty?",
        },
      },
      {
        gratis: true,
        teks: {
          id: "Ongkir retur siapa yang bayar?",
          en: "Who pays for return shipping?",
        },
      },
    ],
  },
  {
    ikon: "ukuran",
    sumber: "dokumen",
    judul: { id: "Ongkir & ukuran", en: "Shipping & sizing" },
    teks: {
      id: "Tarif tiap zona untuk tiga kurir, dan tabel ukuran kaos, kemeja, polo.",
      en: "Per-zone rates for three couriers, plus tee, shirt, and polo size charts.",
    },
    chips: [
      {
        gratis: true,
        teks: {
          id: "Gratis ongkir minimal belanja berapa?",
          en: "What's the minimum for free shipping?",
        },
      },
      {
        gratis: true,
        teks: { id: "Dada 98 cm, aku size apa?", en: "98 cm chest — what size?" },
      },
    ],
  },
  {
    ikon: "kotak",
    sumber: "database",
    judul: { id: "Stok & produk", en: "Stock & products" },
    teks: {
      id: "Sisa stok tiap ukuran dan warna di tiap gudang, plus cari-cari produk.",
      en: "Remaining stock per size, colour, and warehouse, plus product search.",
    },
    chips: [
      { dinamis: "stok" },
      {
        gratis: true,
        teks: { id: "Ada hoodie warna olive?", en: "Any hoodies in olive?" },
      },
    ],
  },
  {
    ikon: "truk",
    sumber: "database",
    judul: { id: "Pesanan & promo", en: "Orders & promos" },
    teks: {
      id: "Sudah sampai mana paketmu, dan kode promo mana yang lagi jalan.",
      en: "Where your parcel is, and which promo codes are running.",
    },
    chips: [{ dinamis: "pesanan" }, { dinamis: "promo" }],
  },
];

const DOKUMEN = [
  {
    nama: { id: "FAQ pelanggan", en: "Customer FAQ" },
    isi: { id: "bahan, cara pesan, pembayaran", en: "fabrics, ordering, payment" },
  },
  {
    nama: { id: "Panduan ukuran", en: "Size guide" },
    isi: { id: "kaos, kemeja, polo", en: "tees, shirts, polos" },
  },
  {
    nama: { id: "Kebijakan pengiriman", en: "Shipping policy" },
    isi: { id: "7 kurir, ongkir per zona", en: "7 couriers, per-zone rates" },
  },
  {
    nama: { id: "Kebijakan retur & garansi", en: "Returns & warranty policy" },
    isi: { id: "5 jenis garansi, prosedur", en: "5 warranty types, procedure" },
  },
];

const DATABASE = [
  {
    nama: { id: "Katalog produk", en: "Product catalogue" },
    isi: { id: "nama, harga, bahan", en: "name, price, fabric" },
  },
  {
    nama: { id: "Stok tiap varian", en: "Stock per variant" },
    isi: { id: "per ukuran, warna, gudang", en: "by size, colour, warehouse" },
  },
  {
    nama: { id: "Status pesanan", en: "Order status" },
    isi: { id: "butuh nomor + 4 digit HP", en: "needs number + last 4 digits" },
  },
  {
    nama: { id: "Promo berjalan", en: "Running promos" },
    isi: { id: "kode, periode, minimum", en: "code, period, minimum" },
  },
];

const BATAS = [
  {
    id: "Memproses pembayaran atau membuatkan pesanan baru",
    en: "Processing payments or creating new orders",
  },
  {
    id: "Membatalkan pesanan sendiri — aku cuma bisa teruskan ke admin",
    en: "Cancelling an order myself — I can only pass it to an admin",
  },
  {
    id: "Menjawab omzet, margin, atau angka penjualan toko",
    en: "Answering revenue, margin, or sales figures",
  },
  {
    id: "Tren fashion umum di luar dokumen dan katalog ini",
    en: "General fashion trends outside these documents and catalogue",
  },
];

let kirimPertanyaan = () => {};

/**
 * Daftarkan aksi yang dijalankan saat chip pertanyaan diklik.
 *
 * @param {(teks: string) => void} aksi Pengirim pertanyaan.
 */
export function saatChipDiklik(aksi) {
  kirimPertanyaan = aksi;
}

/** Gambar ulang seluruh isi layar panduan sesuai bahasa aktif. */
export function renderPanduan() {
  const b = bahasa();
  renderKemampuan(b);
  renderSumber(b);
  renderBatas(b);
  renderContoh(b);

  const kuota = document.getElementById("aturan-kuota");
  if (kuota && state.quota) kuota.textContent = String(state.quota.limit);
}

function renderKemampuan(b) {
  const wadah = kosongkan(document.getElementById("kartu-kemampuan"));

  for (const item of KEMAMPUAN) {
    const chips = item.chips
      .map((chip) => buatChip(chip, b))
      .filter((simpul) => simpul !== null);

    wadah.append(
      el("div", {
        class: "card",
        children: [
          el("div", {
            class: "card__top",
            children: [
              el("span", {
                class:
                  item.sumber === "dokumen" ? "icon-tile" : "icon-tile icon-tile--db",
                html: `<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="${
                  item.sumber === "dokumen" ? "#1e2f6b" : "#177c86"
                }" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${
                  IKON[item.ikon]
                }</svg>`,
              }),
              el("span", {
                class: item.sumber === "dokumen" ? "tag" : "tag tag--db",
                text: item.sumber,
              }),
            ],
          }),
          el("div", {
            children: [
              el("h3", { text: item.judul[b] }),
              el("p", { text: item.teks[b] }),
            ],
          }),
          el("div", { class: "chips", children: chips }),
        ],
      }),
    );
  }
}

function buatChip(chip, b) {
  const teks = chip.dinamis ? teksDinamis(chip.dinamis, b) : chip.teks[b];
  if (!teks) return null;

  const tombol = el("button", {
    class: "chip",
    attrs: { type: "button" },
    children: [
      chip.gratis ? el("span", { class: "dot" }) : null,
      el("span", { text: teks }),
    ],
  });
  tombol.addEventListener("click", () => kirimPertanyaan(teks));
  return tombol;
}

function teksDinamis(jenis, b) {
  const fakta = state.facts;
  if (!fakta?.available) return null;

  if (jenis === "stok") {
    const varian = fakta.variants_ready?.[0];
    if (!varian) return null;
    return b === "id"
      ? `${varian.variant_sku} masih ready?`
      : `Is ${varian.variant_sku} still in stock?`;
  }
  if (jenis === "pesanan") {
    const pesanan = fakta.orders?.[0];
    if (!pesanan) return null;
    return b === "id"
      ? `Lacak ${pesanan.order_number}, HP ${pesanan.phone_last4}`
      : `Track ${pesanan.order_number}, phone ${pesanan.phone_last4}`;
  }
  if (jenis === "promo") {
    const promo = fakta.promotions?.find((p) => p.status === "expired");
    if (!promo) return null;
    return b === "id"
      ? `Kode ${promo.code} masih bisa dipakai?`
      : `Can I still use code ${promo.code}?`;
  }
  return null;
}

function renderSumber(b) {
  isiBaris(document.getElementById("daftar-dokumen"), DOKUMEN, b);
  isiBaris(document.getElementById("daftar-database"), DATABASE, b);
}

function isiBaris(wadah, daftar, b) {
  kosongkan(wadah);
  for (const baris of daftar) {
    wadah.append(
      el("div", {
        class: "source-row",
        children: [
          el("b", { text: baris.nama[b] }),
          el("span", { text: baris.isi[b] }),
        ],
      }),
    );
  }
}

function renderBatas(b) {
  const wadah = kosongkan(document.getElementById("daftar-batas"));
  for (const batas of BATAS) {
    wadah.append(
      el("div", {
        class: "limit",
        children: [el("i", { text: "×" }), el("span", { text: batas[b] })],
      }),
    );
  }
}

function renderContoh(b) {
  const blok = document.getElementById("blok-contoh");
  const fakta = state.facts;

  // Blok disembunyikan saat database tidak bisa dibaca. Kotak error merah di
  // layar pertama jauh lebih buruk daripada satu bagian yang tidak muncul.
  if (!fakta?.available || !(fakta.variants_ready || []).length) {
    blok.hidden = true;
    return;
  }
  blok.hidden = false;

  const wadah = kosongkan(document.getElementById("daftar-contoh"));

  for (const varian of fakta.variants_ready) {
    wadah.append(
      barisFakta("ready", varian.variant_sku, rincianVarian(varian), [
        el("span", {
          class: "fact__meta",
          text:
            b === "id"
              ? `sisa ${varian.available_quantity} pcs`
              : `${varian.available_quantity} pcs left`,
        }),
      ]),
    );
  }

  for (const varian of fakta.variants_restock || []) {
    wadah.append(
      barisFakta("habis", varian.variant_sku, rincianVarian(varian), [
        el("span", {
          class: "fact__meta",
          text:
            b === "id"
              ? `restock ${varian.next_restock_date}`
              : `restock ${varian.next_restock_date}`,
        }),
      ]),
    );
  }

  for (const pesanan of fakta.orders || []) {
    wadah.append(
      barisFakta(
        "db",
        pesanan.order_number,
        b === "id"
          ? `4 digit terakhir HP ${pesanan.phone_last4} — dua-duanya wajib`
          : `Last 4 phone digits ${pesanan.phone_last4} — both required`,
        [el("span", { class: "fact__meta", text: pesanan.order_status })],
      ),
    );
  }

  if (fakta.promotions?.length) {
    const promo = el("div", { class: "promos" });
    for (const item of fakta.promotions) {
      promo.append(
        el("span", {
          class: `promo promo--${item.status}`,
          children: [
            el("code", { text: item.code }),
            el("span", { text: labelStatus(item.status, b) }),
          ],
        }),
      );
    }
    wadah.append(
      el("div", {
        class: "fact",
        children: [
          el("span", { class: "fact__label fact__label--db", text: "promo" }),
          promo,
        ],
      }),
    );
  }
}

function rincianVarian(varian) {
  return [varian.product_name, varian.size, varian.color].filter(Boolean).join(" · ");
}

function barisFakta(jenis, kode, rincian, ekstra) {
  return el("div", {
    class: "fact",
    children: [
      el("span", {
        class: `fact__label fact__label--${jenis}`,
        text: jenis === "db" ? "pesanan" : jenis,
      }),
      el("span", { class: "fact__code", text: kode }),
      el("span", { class: "fact__desc", text: rincian }),
      ...ekstra,
    ],
  });
}

function labelStatus(status, b) {
  const peta = {
    id: { active: "aktif", expired: "kedaluwarsa", scheduled: "belum mulai" },
    en: { active: "active", expired: "expired", scheduled: "not started" },
  };
  return peta[b][status] || status;
}

/** Ambil data acuan dari server lalu gambar ulang bagian yang memakainya. */
export async function muatContoh() {
  try {
    state.facts = await ambilContoh();
  } catch {
    state.facts = { available: false };
  }
  renderPanduan();
}

/** Isi setiap penampung avatar yang ada di markup. */
export function pasangHero() {
  pasangWajah();
}
