"""Ukur akurasi pemilihan tool dan groundedness chatbot di skema besar.

Nilai proyek ini bergantung pada satu klaim: agent dengan 8 tool di atas 28
tabel tetap memilih sumber data yang benar. Script ini yang membuktikannya,
memakai jejak tool call yang benar-benar terjadi, bukan menebak dari teks jawaban.

Jalankan: python scripts/run_eval.py
Prasyarat: database sudah di-seed dan index FAQ sudah dibangun.
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.api.chat.service import build_chatbot_service
from app.config import PROJECT_ROOT, settings
from app.dependencies import probe_llm_ready
from app.evals.trace import EvalTrace, write_traces
from app.models.chat import AgentReply
from app.services.chatbot import ChatbotService
from app.utils.console import configure_console_encoding
from app.utils.errors import LLM_UNAVAILABLE_ERRORS, describe_llm_error
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

DATASET_PATH = PROJECT_ROOT / "evals" / "dataset.jsonl"


@dataclass
class CaseResult:
    """Hasil evaluasi satu kasus uji."""

    case_id: str
    question: str
    answer: str
    called_tools: list[str]
    expected_tools: list[str]
    forbidden_tools: list[str]
    tool_ok: bool
    grounded_ok: bool
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True kalau kasus ini lulus pemeriksaan tool dan groundedness."""
        return self.tool_ok and self.grounded_ok


def parse_args() -> argparse.Namespace:
    """Baca argumen command line.

    Returns:
        Namespace berisi path dataset dan filter kasus.
    """
    parser = argparse.ArgumentParser(description="Jalankan eval chatbot")
    parser.add_argument(
        "--dataset", type=Path, default=DATASET_PATH, help="Path file dataset.jsonl"
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Jalankan hanya kasus yang id-nya diawali prefix ini, mis. 'stock'",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "eval_report.json",
        help="Path file laporan JSON",
    )
    parser.add_argument(
        "--trace-output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "eval_trace.jsonl",
        help=(
            "Path file trace JSONL untuk penilaian mutu retrieval. "
            "Ditulis di run yang sama supaya chatbot tidak perlu dijalankan dua kali."
        ),
    )
    return parser.parse_args()


def load_cases(dataset_path: Path, prefix: str | None = None) -> list[dict[str, Any]]:
    """Baca kasus uji dari file JSONL.

    Args:
        dataset_path: Path file dataset.
        prefix: Kalau diisi, hanya kasus dengan id berawalan ini yang diambil.

    Returns:
        List kasus uji.

    Raises:
        FileNotFoundError: Kalau file dataset tidak ada.
    """
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset eval tidak ditemukan: {dataset_path}")

    cases: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Baris {line_number} di {dataset_path} bukan JSON valid: {exc}"
            ) from exc
        if prefix is None or str(case.get("id", "")).startswith(prefix):
            cases.append(case)

    return cases


def evaluate_case(case: dict[str, Any], reply: AgentReply) -> CaseResult:
    """Nilai satu jawaban terhadap ekspektasi kasus.

    Args:
        case: Definisi kasus dari dataset.
        reply: Jawaban agent beserta jejak tool-nya.

    Returns:
        Hasil evaluasi kasus.
    """
    called = [call.tool_name for call in reply.tool_calls]
    expected = list(case.get("expect_tools", []))
    forbidden = list(case.get("forbid_tools", []))
    violations: list[str] = []

    missing = [tool for tool in expected if tool not in called]
    if missing:
        violations.append(f"tool wajib tidak dipanggil: {', '.join(missing)}")

    used_forbidden = [tool for tool in forbidden if tool in called]
    if used_forbidden:
        violations.append(f"tool terlarang dipanggil: {', '.join(used_forbidden)}")

    answer_lower = reply.answer.lower()
    banned = [
        phrase
        for phrase in case.get("must_not_contain", [])
        if phrase.lower() in answer_lower
    ]
    if banned:
        violations.append(f"jawaban memuat frasa terlarang: {', '.join(banned)}")

    return CaseResult(
        case_id=str(case.get("id", "?")),
        question=str(case.get("question", "")),
        answer=reply.answer,
        called_tools=called,
        expected_tools=expected,
        forbidden_tools=forbidden,
        tool_ok=not missing and not used_forbidden,
        grounded_ok=not banned,
        violations=violations,
    )


async def run_case(
    service: ChatbotService, case: dict[str, Any]
) -> tuple[CaseResult, EvalTrace]:
    """Jalankan satu kasus uji terhadap chatbot.

    Setiap kasus memakai session_id unik supaya riwayat antar-kasus tidak
    saling mencemari, kecuali kasus yang memang menguji kesadaran konteks.

    Args:
        service: ChatbotService yang diuji.
        case: Definisi kasus dari dataset.

    Returns:
        Hasil evaluasi kasus, beserta trace untuk penilaian mutu lanjutan.
    """
    session_id = f"eval-{case.get('id', uuid.uuid4().hex)}-{uuid.uuid4().hex[:8]}"

    for previous_question in case.get("history", []):
        await service.answer(session_id=session_id, message=previous_question)

    reply = await service.answer(
        session_id=session_id, message=str(case["question"])
    )
    return evaluate_case(case, reply), EvalTrace.from_case(case, reply)


def print_report(results: list[CaseResult]) -> dict[str, Any]:
    """Cetak ringkasan hasil eval dan kembalikan metriknya.

    Args:
        results: Hasil seluruh kasus.

    Returns:
        Dict metrik agregat.
    """
    total = len(results)
    tool_passed = sum(1 for result in results if result.tool_ok)
    grounded_passed = sum(1 for result in results if result.grounded_ok)
    fully_passed = sum(1 for result in results if result.passed)
    total_calls = sum(len(result.called_tools) for result in results)

    metrics = {
        "total_cases": total,
        "tool_accuracy": round(tool_passed / total, 4) if total else 0.0,
        "groundedness": round(grounded_passed / total, 4) if total else 0.0,
        "overall_pass_rate": round(fully_passed / total, 4) if total else 0.0,
        "avg_tool_calls_per_question": round(total_calls / total, 2) if total else 0.0,
    }

    print("\n" + "=" * 72)
    print("LAPORAN EVAL CHATBOT")
    print("=" * 72)
    print(
        f"Model agent / composer       : "
        f"{settings.llm_model} / {settings.composer_model}"
    )
    print(f"Kasus diuji                  : {metrics['total_cases']}")
    print(f"Akurasi pemilihan tool       : {metrics['tool_accuracy']:.1%} (target >= 90%)")
    print(f"Groundedness                 : {metrics['groundedness']:.1%} (target 100%)")
    print(f"Lulus keduanya               : {metrics['overall_pass_rate']:.1%}")
    print(f"Rata-rata tool call / soal   : {metrics['avg_tool_calls_per_question']}")

    failures = [result for result in results if not result.passed]
    if failures:
        print(f"\n{len(failures)} kasus gagal:")
        for result in failures:
            print(f"\n  [{result.case_id}] {result.question}")
            print(f"    tool dipanggil : {result.called_tools or '-'}")
            print(f"    tool diharapkan: {result.expected_tools or '-'}")
            for violation in result.violations:
                print(f"    pelanggaran    : {violation}")
            print(f"    jawaban        : {result.answer[:160]}")
    else:
        print("\nSemua kasus lulus.")

    print("=" * 72)
    return metrics


def save_report(
    output_path: Path, metrics: dict[str, Any], results: list[CaseResult]
) -> None:
    """Simpan laporan eval ke file JSON.

    Args:
        output_path: Path file laporan.
        metrics: Metrik agregat.
        results: Hasil seluruh kasus.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        # Model ikut dicatat supaya laporan dari branch berbeda bisa
        # dibandingkan tanpa menebak run mana milik model mana.
        "llm_model": settings.llm_model,
        "composer_model": settings.composer_model,
        "metrics": metrics,
        "cases": [
            {
                "id": result.case_id,
                "question": result.question,
                "answer": result.answer,
                "called_tools": result.called_tools,
                "expected_tools": result.expected_tools,
                "passed": result.passed,
                "violations": result.violations,
            }
            for result in results
        ],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nLaporan lengkap disimpan di {output_path}")


async def run_all(args: argparse.Namespace) -> int:
    """Jalankan seluruh kasus eval secara berurutan.

    Args:
        args: Argumen command line.

    Returns:
        0 kalau semua kasus lulus, 1 kalau ada yang gagal atau setup bermasalah.
    """
    try:
        cases = load_cases(args.dataset, prefix=args.only)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(f"{exc}")
        return 1

    if not cases:
        logger.error("Tidak ada kasus yang cocok dengan filter yang diberikan")
        return 1

    llm_ready, llm_detail = probe_llm_ready()
    if not llm_ready:
        logger.error(llm_detail)
        logger.error("Eval dibatalkan sebelum kasus pertama dijalankan.")
        return 1

    try:
        service = build_chatbot_service()
    except ValueError as exc:
        logger.error(f"Konfigurasi belum lengkap: {exc}")
        return 1

    results: list[CaseResult] = []
    traces: list[EvalTrace] = []
    for index, case in enumerate(cases, start=1):
        case_id = case.get("id", "?")
        logger.info(f"[{index}/{len(cases)}] Menjalankan kasus {case_id}")
        try:
            result, trace = await run_case(service, case)
            results.append(result)
            traces.append(trace)
        except LLM_UNAVAILABLE_ERRORS as exc:
            # Server Ollama mati atau model hilang akan berulang di setiap kasus
            # berikutnya, jadi tidak ada gunanya melanjutkan 40 kasus lagi. Trace
            # yang sudah terkumpul tetap ditulis supaya kasus yang sudah berjalan
            # tidak perlu diulang setelah servernya dibetulkan.
            logger.error(describe_llm_error(exc))
            logger.error("Eval dihentikan sebelum kasus berikutnya dijalankan.")
            write_traces(args.trace_output, traces)
            return 1
        except (RuntimeError, ValueError) as exc:
            logger.error(f"Kasus {case_id} gagal dijalankan: {exc}", exc_info=True)
            results.append(
                CaseResult(
                    case_id=str(case_id),
                    question=str(case.get("question", "")),
                    answer=f"ERROR: {exc}",
                    called_tools=[],
                    expected_tools=list(case.get("expect_tools", [])),
                    forbidden_tools=list(case.get("forbid_tools", [])),
                    tool_ok=False,
                    grounded_ok=False,
                    violations=[f"exception: {exc}"],
                )
            )

    metrics = print_report(results)
    save_report(args.output, metrics, results)
    write_traces(args.trace_output, traces)
    print(f"Trace untuk penilaian mutu disimpan di {args.trace_output}")

    return 0 if metrics["overall_pass_rate"] == 1.0 else 1


def main() -> int:
    """Entry point script eval.

    Returns:
        Exit code proses.
    """
    configure_console_encoding()
    args = parse_args()
    return asyncio.run(run_all(args))


if __name__ == "__main__":
    sys.exit(main())
