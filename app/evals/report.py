"""Bentuk laporan penilaian mutu."""

from statistics import fmean

from pydantic import BaseModel, Field


class CaseScore(BaseModel):
    """Skor seluruh metrik untuk satu kasus uji."""

    case_id: str
    question: str
    scores: dict[str, float] = Field(default_factory=dict)
    unscored: list[str] = Field(
        default_factory=list,
        description=(
            "Metrik yang gagal dinilai untuk kasus ini, mis. keluaran juri tidak "
            "sesuai skema. Dicatat terpisah, tidak dihitung sebagai skor nol."
        ),
    )


class QualityReport(BaseModel):
    """Hasil satu keluarga metrik atas satu berkas trace."""

    metric_family: str
    judge_model: str
    cases: list[CaseScore] = Field(default_factory=list)
    aggregates: dict[str, float] = Field(default_factory=dict)
    unscored_total: int = 0
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def build(
        cls,
        metric_family: str,
        judge_model: str,
        cases: list[CaseScore],
        notes: list[str] | None = None,
    ) -> "QualityReport":
        """Rakit laporan lengkap dengan agregat yang sudah dihitung.

        Kasus yang gagal dinilai tidak ikut rata-rata dan tidak dihitung nol.
        Skor nol berarti juri menilai dan menyatakan buruk; gagal-nilai berarti
        tidak ada pengukuran sama sekali. Mencampur keduanya membuat kegagalan
        infrastruktur terbaca seperti kegagalan sistem yang diuji.

        Args:
            metric_family: Nama keluarga metrik, mis. "deepeval-retrieval".
            judge_model: Model juri yang menghasilkan skor ini.
            cases: Skor per kasus.
            notes: Catatan yang harus ikut terbaca bersama angkanya.

        Returns:
            Laporan siap disimpan.
        """
        collected: dict[str, list[float]] = {}
        for case in cases:
            for metric, score in case.scores.items():
                collected.setdefault(metric, []).append(score)

        return cls(
            metric_family=metric_family,
            judge_model=judge_model,
            cases=cases,
            aggregates={
                metric: round(fmean(values), 4)
                for metric, values in sorted(collected.items())
                if values
            },
            unscored_total=sum(len(case.unscored) for case in cases),
            notes=notes or [],
        )

    def worst_cases(self, metric: str, limit: int = 5) -> list[CaseScore]:
        """Ambil kasus dengan skor terendah untuk satu metrik.

        Rata-rata tanpa daftar kasus terburuk tidak bisa ditindaklanjuti: angka
        turun tanpa petunjuk pertanyaan mana yang harus diperbaiki.

        Args:
            metric: Nama metrik.
            limit: Jumlah kasus yang dikembalikan.

        Returns:
            Kasus terburuk lebih dulu.
        """
        scored = [case for case in self.cases if metric in case.scores]
        return sorted(scored, key=lambda case: case.scores[metric])[:limit]
