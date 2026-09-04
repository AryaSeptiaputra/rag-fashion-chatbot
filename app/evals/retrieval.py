"""Penilaian mutu retrieval dengan DeepEval, plus metrik hit-rate tanpa juri.

Konteks yang dinilai di sini hanya potongan FAQ mentah dari vector store.
Keluaran tool lain sengaja tidak ikut: data stok dan pesanan datang dari
Postgres lewat RPC, bukan dari retrieval, jadi memasukkannya akan mengukur hal
yang berbeda dari yang dimaksud.

Selain tiga metrik DeepEval yang dinilai LLM, modul ini menghitung satu metrik
deterministik: berapa bagian potongan yang benar-benar berasal dari seksi FAQ
yang diharapkan dataset. Metrik itu tidak bergantung pada juri sama sekali,
jadi ia tetap bisa dipercaya justru saat skor juri terlihat mencurigakan.
"""

from typing import Any

from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
)
from deepeval.test_case import LLMTestCase

from app.config import settings
from app.evals.report import CaseScore, QualityReport
from app.evals.trace import EvalTrace, FaqSectionIndex
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_METRIC_FAMILY = "deepeval-retrieval"
_SECTION_HIT_RATE = "section_hit_rate"


class RetrievalQualityEvaluator:
    """Menilai potongan yang diambil vector store untuk tiap pertanyaan."""

    def __init__(self, judge: Any, section_index: FaqSectionIndex | None = None) -> None:
        self.judge = judge
        self.section_index = section_index

    def evaluate(self, traces: list[EvalTrace]) -> QualityReport:
        """Nilai mutu retrieval seluruh trace yang benar-benar melakukan retrieval.

        Args:
            traces: Trace hasil menjalankan kasus eval.

        Returns:
            Laporan berisi skor per kasus, agregat, dan jumlah gagal-nilai.

        Raises:
            ValueError: Kalau tidak ada trace yang melakukan retrieval.
        """
        usable = [trace for trace in traces if trace.has_retrieval]
        if not usable:
            raise ValueError(
                "Tidak ada trace yang memanggil retrieval. Pastikan kasusnya "
                "memicu search_faq, dan index FAQ sudah dibangun."
            )

        notes: list[str] = []
        skipped = len(traces) - len(usable)
        if skipped:
            notes.append(
                f"{skipped} trace dilewati karena tidak melakukan retrieval sama sekali."
            )

        without_reference = [trace for trace in usable if not trace.reference]
        if without_reference:
            notes.append(
                f"ContextualPrecision dan ContextualRecall dilewati pada "
                f"{len(without_reference)} kasus yang belum punya jawaban acuan."
            )

        if self.section_index is None:
            notes.append(
                "section_hit_rate dilewati: indeks seksi FAQ tidak diberikan."
            )

        logger.info(
            f"Menilai retrieval {len(usable)} trace dengan juri {settings.judge_model}"
        )
        cases = [self._evaluate_case(trace) for trace in usable]

        return QualityReport.build(
            metric_family=_METRIC_FAMILY,
            judge_model=settings.judge_model,
            cases=cases,
            notes=notes,
        )

    def _evaluate_case(self, trace: EvalTrace) -> CaseScore:
        test_case = LLMTestCase(
            input=trace.question,
            actual_output=trace.answer,
            expected_output=trace.reference,
            retrieval_context=trace.retrieved_contexts,
        )

        scores: dict[str, float] = {}
        unscored: list[str] = []

        for metric in self._metrics_for(trace):
            name = type(metric).__name__
            try:
                metric.measure(test_case)
            except Exception as exc:  # noqa: BLE001
                # DeepEval membungkus kegagalan parsing juri, timeout, dan error
                # transport dalam tipe yang berbeda-beda dan tidak stabil antar
                # rilis. Yang penting di sini satu: kasus ini tidak punya skor,
                # dan sisa kasus tetap harus dinilai.
                logger.warning(f"Metrik {name} gagal di kasus {trace.id}: {exc}")
                unscored.append(name)
                continue

            if metric.score is None:
                unscored.append(name)
            else:
                scores[name] = round(float(metric.score), 4)

        hit_rate = self._section_hit_rate(trace)
        if hit_rate is not None:
            scores[_SECTION_HIT_RATE] = hit_rate

        return CaseScore(
            case_id=trace.id,
            question=trace.question,
            scores=scores,
            unscored=unscored,
        )

    def _metrics_for(self, trace: EvalTrace) -> list[Any]:
        """Rakit metrik yang datanya lengkap untuk kasus ini."""
        metrics: list[Any] = [ContextualRelevancyMetric(model=self.judge)]
        if trace.reference:
            metrics.append(ContextualPrecisionMetric(model=self.judge))
            metrics.append(ContextualRecallMetric(model=self.judge))
        return metrics

    def _section_hit_rate(self, trace: EvalTrace) -> float | None:
        """Hitung bagian potongan yang berasal dari seksi FAQ yang diharapkan.

        Args:
            trace: Trace yang sedang dinilai.

        Returns:
            Rasio 0..1, atau None kalau kasusnya tidak menyebut seksi acuan.
        """
        if self.section_index is None or not trace.reference_sections:
            return None

        hits = list(self.section_index.section_hits(trace))
        if not hits:
            return None
        return round(sum(hits) / len(hits), 4)
