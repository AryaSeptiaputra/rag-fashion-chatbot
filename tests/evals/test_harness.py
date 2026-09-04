"""Test perakitan penilai DeepEval.

Sebagian test ter-skip di venv utama karena DeepEval hanya terpasang di
.venv-eval. Yang diuji di sini adalah bagian yang tidak memanggil model juri:
penanganan kunci API, penolakan trace yang tidak bisa dinilai, dan metrik
hit-rate yang memang deterministik.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.evals.trace import EvalTrace, FaqSectionIndex

FAQ_MARKDOWN = """# FAQ

## Pengiriman

Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE, SiCepat, atau Anteraja.

## Pembayaran

Metode pembayaran transfer bank, QRIS, virtual account. COD belum tersedia.
"""


@pytest.fixture
def index(tmp_path: Path) -> FaqSectionIndex:
    """Indeks seksi dari dokumen FAQ contoh."""
    (tmp_path / "faq.md").write_text(FAQ_MARKDOWN, encoding="utf-8")
    return FaqSectionIndex.from_directory(tmp_path)


def make_trace(**overrides: object) -> EvalTrace:
    """Buat trace dengan nilai wajar untuk diubah sebagian."""
    payload: dict[str, object] = {
        "id": "ret-01",
        "question": "Berapa lama kirim ke luar Jawa?",
        "answer": "4-7 hari kerja kak.",
        "contexts": ["hasil tool utuh"],
        "retrieved_contexts": ["Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE."],
        "reference": "Luar Pulau Jawa 4-7 hari kerja.",
        "reference_sections": ["Pengiriman"],
        "called_tools": ["search_faq"],
    }
    payload.update(overrides)
    return EvalTrace(**payload)  # type: ignore[arg-type]


def test_missing_judge_key_says_the_chatbot_does_not_need_it() -> None:
    # Kunci kosong hanya boleh menghalangi penilaian mutu. Pesan yang tidak
    # menyebutkan itu akan membuat orang mengira chatbot-nya ikut butuh API.
    original = settings.anthropic_api_key
    settings.anthropic_api_key = ""
    try:
        with pytest.raises(ValueError, match="tidak membutuhkannya"):
            settings.require_judge_key()
    finally:
        settings.anthropic_api_key = original


def test_judge_key_is_returned_when_present() -> None:
    original = settings.anthropic_api_key
    settings.anthropic_api_key = "sk-ant-contoh"
    try:
        assert settings.require_judge_key() == "sk-ant-contoh"
    finally:
        settings.anthropic_api_key = original


def test_retrieval_evaluator_refuses_traces_without_retrieval() -> None:
    pytest.importorskip("deepeval")
    from app.evals.retrieval import RetrievalQualityEvaluator

    evaluator = RetrievalQualityEvaluator(judge=object())

    with pytest.raises(ValueError, match="retrieval"):
        evaluator.evaluate([make_trace(retrieved_contexts=[])])


def test_section_hit_rate_needs_no_judge(index: FaqSectionIndex) -> None:
    # Metrik ini deterministik dengan sengaja: ia tetap bisa dipercaya justru
    # saat skor juri terlihat mencurigakan.
    pytest.importorskip("deepeval")
    from app.evals.retrieval import RetrievalQualityEvaluator

    evaluator = RetrievalQualityEvaluator(judge=None, section_index=index)
    trace = make_trace(
        retrieved_contexts=[
            "Estimasi luar Pulau Jawa 4-7 hari kerja lewat JNE.",
            "Metode pembayaran transfer bank, QRIS, virtual account.",
        ]
    )

    assert evaluator._section_hit_rate(trace) == 0.5


def test_section_hit_rate_is_absent_without_reference_sections(
    index: FaqSectionIndex,
) -> None:
    pytest.importorskip("deepeval")
    from app.evals.retrieval import RetrievalQualityEvaluator

    evaluator = RetrievalQualityEvaluator(judge=None, section_index=index)

    assert evaluator._section_hit_rate(make_trace(reference_sections=[])) is None


def test_section_hit_rate_is_absent_without_index() -> None:
    pytest.importorskip("deepeval")
    from app.evals.retrieval import RetrievalQualityEvaluator

    evaluator = RetrievalQualityEvaluator(judge=None)

    assert evaluator._section_hit_rate(make_trace()) is None
