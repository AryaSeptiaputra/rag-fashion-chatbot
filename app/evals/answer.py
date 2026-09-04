"""Penilaian mutu jawaban akhir dengan RAGAS.

Konteks pembanding di sini adalah keluaran seluruh tool, bukan potongan FAQ.
Itu pilihan yang menentukan: AnswerComposer memang hanya boleh bersandar pada
hasil tool, jadi bukti itulah pembanding yang benar. Menilai jawaban stok
terhadap potongan FAQ akan menuduhnya berhalusinasi padahal datanya sah,
hanya datang dari Postgres alih-alih dari vector store.
"""

import math
from typing import Any

from ragas import EvaluationDataset, SingleTurnSample, evaluate

# ragas.metrics masih meneruskan nama-nama ini lewat __getattr__ dengan peringatan
# deprecation. Jalur resminya sekarang ragas.metrics.collections, dan di sana
# metriknya menerima llm serta embeddings di konstruktor, bukan lewat evaluate().
from ragas.metrics.collections import (
    AnswerRelevancy,
    FactualCorrectness,
    Faithfulness,
)

from app.config import settings
from app.evals.report import CaseScore, QualityReport
from app.evals.trace import EvalTrace
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_METRIC_FAMILY = "ragas-answer"


class AnswerQualityEvaluator:
    """Menilai jawaban akhir terhadap bukti yang dilihat composer."""

    def __init__(self, judge: Any, embeddings: Any | None = None) -> None:
        self.judge = judge
        self.embeddings = embeddings

    def evaluate(self, traces: list[EvalTrace]) -> QualityReport:
        """Nilai seluruh trace dan rangkum hasilnya.

        Args:
            traces: Trace hasil menjalankan kasus eval.

        Returns:
            Laporan berisi skor per kasus, agregat, dan jumlah gagal-nilai.

        Raises:
            ValueError: Kalau tidak ada trace yang bisa dinilai.
        """
        usable = [trace for trace in traces if trace.contexts]
        if not usable:
            raise ValueError(
                "Tidak ada trace yang punya keluaran tool. Metrik jawaban RAGAS "
                "menilai jawaban terhadap bukti, jadi trace tanpa tool call "
                "tidak bisa dinilai."
            )

        metrics, notes = self._build_metrics(usable)
        dataset = EvaluationDataset(
            samples=[self._to_sample(trace) for trace in usable]
        )

        logger.info(
            f"Menilai {len(usable)} trace dengan {len(metrics)} metrik RAGAS "
            f"(juri {settings.judge_model})"
        )
        # raise_exceptions=False membuat kasus yang gagal dinilai keluar sebagai
        # NaN alih-alih menggugurkan seluruh run. Juri 7B sesekali melanggar
        # skema JSON yang diminta, dan satu kasus rusak tidak boleh membatalkan
        # puluhan kasus lain yang sudah berjalan.
        #
        # llm dan embeddings tidak dioper ke evaluate(): metrik dari
        # ragas.metrics.collections sudah membawanya sendiri dari konstruktor.
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            raise_exceptions=False,
            show_progress=True,
        )

        cases = self._collect_scores(usable, result, metrics)
        skipped = len(traces) - len(usable)
        if skipped:
            notes.append(f"{skipped} trace dilewati karena tidak memanggil tool apa pun.")

        return QualityReport.build(
            metric_family=_METRIC_FAMILY,
            judge_model=settings.judge_model,
            cases=cases,
            notes=notes,
        )

    def _build_metrics(self, traces: list[EvalTrace]) -> tuple[list[Any], list[str]]:
        """Pilih metrik yang datanya benar-benar tersedia."""
        metrics: list[Any] = [Faithfulness(llm=self.judge)]
        notes: list[str] = []

        if self.embeddings is not None:
            metrics.append(
                AnswerRelevancy(llm=self.judge, embeddings=self.embeddings)
            )
        else:
            notes.append(
                "AnswerRelevancy dilewati: model embedding juri tidak tersedia."
            )

        if all(trace.reference for trace in traces):
            metrics.append(FactualCorrectness(llm=self.judge))
        else:
            without = sum(1 for trace in traces if not trace.reference)
            notes.append(
                f"FactualCorrectness dilewati: {without} dari {len(traces)} kasus "
                "belum punya jawaban acuan."
            )

        return metrics, notes

    @staticmethod
    def _to_sample(trace: EvalTrace) -> SingleTurnSample:
        return SingleTurnSample(
            user_input=trace.question,
            response=trace.answer,
            retrieved_contexts=trace.contexts,
            reference=trace.reference,
        )

    @staticmethod
    def _collect_scores(
        traces: list[EvalTrace], result: Any, metrics: list[Any]
    ) -> list[CaseScore]:
        """Ubah hasil RAGAS jadi skor per kasus, memisahkan yang gagal dinilai."""
        frame = result.to_pandas()
        names = [metric.name for metric in metrics]

        cases: list[CaseScore] = []
        for position, trace in enumerate(traces):
            scores: dict[str, float] = {}
            unscored: list[str] = []
            for name in names:
                if name not in frame.columns:
                    unscored.append(name)
                    continue
                value = frame.iloc[position][name]
                if value is None or (
                    isinstance(value, float) and math.isnan(value)
                ):
                    unscored.append(name)
                else:
                    scores[name] = round(float(value), 4)

            if unscored:
                logger.warning(
                    f"Kasus {trace.id} gagal dinilai untuk: {', '.join(unscored)}"
                )
            cases.append(
                CaseScore(
                    case_id=trace.id,
                    question=trace.question,
                    scores=scores,
                    unscored=unscored,
                )
            )

        return cases
