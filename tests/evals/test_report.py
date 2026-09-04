"""Test bentuk laporan penilaian: agregasi dan pemisahan kasus gagal-nilai."""

from app.evals.report import CaseScore, QualityReport


def case(case_id: str, **scores: float) -> CaseScore:
    """Buat skor satu kasus."""
    return CaseScore(case_id=case_id, question=f"pertanyaan {case_id}", scores=scores)


def test_aggregate_is_the_mean_per_metric() -> None:
    report = QualityReport.build(
        metric_family="ragas-answer",
        judge_model="qwen2.5:7b-instruct",
        cases=[case("a", faithfulness=1.0), case("b", faithfulness=0.5)],
    )

    assert report.aggregates == {"faithfulness": 0.75}


def test_unscored_case_is_not_counted_as_zero() -> None:
    # Skor nol berarti juri menilai dan menyatakan buruk. Gagal-nilai berarti
    # tidak ada pengukuran sama sekali. Mencampur keduanya membuat kegagalan
    # infrastruktur terbaca seperti kegagalan sistem yang diuji.
    scored = case("a", faithfulness=1.0)
    failed = CaseScore(case_id="b", question="q", unscored=["faithfulness"])

    report = QualityReport.build(
        metric_family="ragas-answer",
        judge_model="qwen2.5:7b-instruct",
        cases=[scored, failed],
    )

    assert report.aggregates == {"faithfulness": 1.0}
    assert report.unscored_total == 1


def test_metric_scored_nowhere_is_absent_from_aggregates() -> None:
    report = QualityReport.build(
        metric_family="deepeval-retrieval",
        judge_model="qwen2.5:7b-instruct",
        cases=[CaseScore(case_id="a", question="q", unscored=["ContextualRecall"])],
    )

    assert report.aggregates == {}
    assert report.unscored_total == 1


def test_metrics_are_aggregated_independently() -> None:
    report = QualityReport.build(
        metric_family="deepeval-retrieval",
        judge_model="qwen2.5:7b-instruct",
        cases=[
            case("a", relevancy=1.0, recall=0.0),
            CaseScore(case_id="b", question="q", scores={"relevancy": 0.0}),
        ],
    )

    assert report.aggregates == {"recall": 0.0, "relevancy": 0.5}


def test_worst_cases_are_ordered_lowest_first() -> None:
    report = QualityReport.build(
        metric_family="ragas-answer",
        judge_model="qwen2.5:7b-instruct",
        cases=[case("a", f=0.9), case("b", f=0.1), case("c", f=0.5)],
    )

    assert [item.case_id for item in report.worst_cases("f", limit=2)] == ["b", "c"]


def test_worst_cases_skips_cases_without_that_metric() -> None:
    report = QualityReport.build(
        metric_family="ragas-answer",
        judge_model="qwen2.5:7b-instruct",
        cases=[case("a", f=0.9), CaseScore(case_id="b", question="q")],
    )

    assert [item.case_id for item in report.worst_cases("f")] == ["a"]


def test_judge_model_travels_with_the_numbers() -> None:
    # Angka dari juri berbeda tidak sebanding. Nama jurinya harus menempel di
    # laporan, bukan diingat terpisah.
    report = QualityReport.build(
        metric_family="ragas-answer",
        judge_model="qwen2.5:7b-instruct",
        cases=[case("a", f=1.0)],
        notes=["ResponseRelevancy dilewati."],
    )

    assert report.judge_model == "qwen2.5:7b-instruct"
    assert report.notes == ["ResponseRelevancy dilewati."]
