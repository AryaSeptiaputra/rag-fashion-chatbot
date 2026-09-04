"""Test trace eval: bentuk data, muat/simpan, dan pemetaan seksi FAQ."""

from pathlib import Path

import pytest

from app.evals.trace import EvalTrace, FaqSectionIndex, load_traces, write_traces
from app.models.chat import AgentReply, ToolCallRecord

FAQ_MARKDOWN = """# FAQ Contoh

Kalimat pembuka yang bukan bagian seksi mana pun.

## Pengiriman

Pesanan diproses 1-2 hari kerja setelah pembayaran dikonfirmasi.
Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE, SiCepat, atau Anteraja.

## Pembayaran

Metode pembayaran: transfer bank, QRIS, virtual account, dan e-wallet.
Pembayaran COD belum tersedia. Batas waktu pembayaran 24 jam.
"""


@pytest.fixture
def faq_dir(tmp_path: Path) -> Path:
    """Direktori berisi satu dokumen FAQ contoh."""
    (tmp_path / "faq.md").write_text(FAQ_MARKDOWN, encoding="utf-8")
    return tmp_path


@pytest.fixture
def index(faq_dir: Path) -> FaqSectionIndex:
    """Indeks seksi dari dokumen contoh."""
    return FaqSectionIndex.from_directory(faq_dir)


def make_trace(**overrides: object) -> EvalTrace:
    """Buat trace dengan nilai wajar untuk diubah sebagian."""
    payload: dict[str, object] = {
        "id": "ret-01",
        "question": "Berapa lama kirim ke luar Jawa?",
        "answer": "4-7 hari kerja kak.",
        "contexts": ["hasil tool utuh"],
        "retrieved_contexts": ["Estimasi luar Pulau Jawa 4-7 hari kerja."],
        "reference": "Luar Pulau Jawa 4-7 hari kerja.",
        "reference_sections": ["Pengiriman"],
        "called_tools": ["search_faq"],
    }
    payload.update(overrides)
    return EvalTrace(**payload)  # type: ignore[arg-type]


def test_roundtrip_preserves_every_field(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    original = [make_trace(), make_trace(id="ret-02", reference=None)]

    assert write_traces(path, original) == 2

    assert load_traces(path) == original


def test_writing_zero_traces_still_creates_a_readable_file(tmp_path: Path) -> None:
    path = tmp_path / "kosong.jsonl"

    assert write_traces(path, []) == 0
    assert load_traces(path) == []


def test_missing_file_names_the_fix(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run_eval.py"):
        load_traces(tmp_path / "tidak-ada.jsonl")


def test_malformed_line_names_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "rusak.jsonl"
    path.write_text(
        make_trace().model_dump_json() + "\n{bukan json}\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Baris 2"):
        load_traces(path)


def test_has_retrieval_distinguishes_turns_without_vector_store() -> None:
    assert make_trace().has_retrieval is True
    assert make_trace(retrieved_contexts=[]).has_retrieval is False


def test_from_case_uses_full_tool_output_not_truncated_summary() -> None:
    # Juri yang melihat bukti lebih sedikit daripada composer akan memvonis
    # jawaban yang sah sebagai halusinasi.
    full = "Daftar produk panjang. " * 60
    reply = AgentReply(
        answer="Ada 12 produk kak.",
        tool_calls=[
            ToolCallRecord(tool_name="search_products", result_summary=full[:500])
        ],
        tool_outputs=[full],
        retrieved_contexts=[],
    )

    trace = EvalTrace.from_case({"id": "search-01", "question": "ada apa aja?"}, reply)

    assert trace.contexts == [full]
    assert trace.called_tools == ["search_products"]
    assert trace.reference is None


def test_from_case_carries_reference_fields() -> None:
    case = {
        "id": "ret-01",
        "question": "q",
        "reference": "jawaban acuan",
        "reference_sections": ["Pengiriman"],
    }

    trace = EvalTrace.from_case(case, AgentReply(answer="a"))

    assert trace.reference == "jawaban acuan"
    assert trace.reference_sections == ["Pengiriman"]


def test_index_splits_on_level_two_headings(index: FaqSectionIndex) -> None:
    assert set(index.sections) == {"Pengiriman", "Pembayaran"}
    assert "JNE" in index.sections["Pengiriman"]
    assert "COD" in index.sections["Pembayaran"]


def test_directory_without_sections_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "kosong.md").write_text("# Judul saja\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Tidak ada seksi FAQ"):
        FaqSectionIndex.from_directory(tmp_path)


def test_unknown_section_lists_the_available_ones(index: FaqSectionIndex) -> None:
    # Acuan yang menunjuk seksi tidak ada akan diam-diam menghasilkan recall nol
    # dan terbaca seperti kegagalan retrieval, jadi ini harus gagal keras.
    with pytest.raises(KeyError, match="Pembayaran"):
        index.texts_for(["Seksi Karangan"])


def test_texts_for_returns_sections_in_requested_order(index: FaqSectionIndex) -> None:
    texts = index.texts_for(["Pembayaran", "Pengiriman"])

    assert "COD" in texts[0]
    assert "JNE" in texts[1]


def test_locate_matches_a_chunk_to_its_source_section(index: FaqSectionIndex) -> None:
    chunk = "Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE, SiCepat."

    assert index.locate(chunk) == "Pengiriman"


def test_locate_rejects_text_from_outside_the_corpus(index: FaqSectionIndex) -> None:
    assert index.locate("Harga saham naik tajam di bursa Tokyo pagi ini.") is None


def test_locate_on_empty_chunk_returns_none(index: FaqSectionIndex) -> None:
    assert index.locate("   ") is None


def test_section_hits_flag_chunks_from_the_wrong_section(
    index: FaqSectionIndex,
) -> None:
    trace = make_trace(
        retrieved_contexts=[
            "Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE.",
            "Metode pembayaran transfer bank, QRIS, virtual account.",
        ],
        reference_sections=["Pengiriman"],
    )

    assert list(index.section_hits(trace)) == [True, False]
