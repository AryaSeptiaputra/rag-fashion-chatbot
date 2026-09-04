"""Jejak satu giliran eval: masukan penilai mutu.

Trace ditulis saat generate dan dibaca saat menilai. Pemisahan itu disengaja:
generate butuh Supabase, ChromaDB, dan model yang diuji, sedangkan penilaian
hanya butuh model juri. Kalau sesi penilaian putus, generate tidak perlu
diulang.
"""

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.models.chat import AgentReply
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Heading level dua adalah batas topik di dokumen FAQ. Judul itu yang dirujuk
# dataset lewat reference_sections, bukan teks chunk-nya, supaya acuan tidak
# basi setiap kali CHUNK_SIZE disetel ulang.
_SECTION_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)

# Kata yang muncul di hampir semua seksi sehingga tidak membedakan apa pun saat
# mencocokkan potongan ke seksi asalnya.
_STOPWORDS = frozenset(
    {
        "yang", "dan", "atau", "untuk", "dengan", "di", "ke", "dari", "pada",
        "ini", "itu", "tidak", "bisa", "akan", "sudah", "kalau", "juga", "ada",
        "kami", "adalah", "dalam", "saat", "setelah", "lebih", "jadi", "hari",
    }
)

_MIN_OVERLAP_RATIO = 0.35


class EvalTrace(BaseModel):
    """Satu baris masukan penilaian, hasil menjalankan satu kasus eval."""

    id: str
    question: str
    answer: str
    contexts: list[str] = Field(
        default_factory=list,
        description=(
            "Keluaran seluruh tool pada giliran ini. Inilah bukti yang dilihat "
            "AnswerComposer, jadi inilah pembanding yang benar untuk menilai "
            "faithfulness jawaban."
        ),
    )
    retrieved_contexts: list[str] = Field(
        default_factory=list,
        description=(
            "Potongan FAQ mentah dari vector store. Hanya bagian ini yang "
            "relevan untuk menilai mutu retrieval."
        ),
    )
    reference: str | None = None
    reference_sections: list[str] = Field(default_factory=list)
    called_tools: list[str] = Field(default_factory=list)

    @property
    def has_retrieval(self) -> bool:
        """True kalau giliran ini benar-benar mengambil potongan dokumen."""
        return bool(self.retrieved_contexts)

    @classmethod
    def from_case(cls, case: dict[str, Any], reply: AgentReply) -> "EvalTrace":
        """Rakit trace dari definisi kasus dan jawaban agent.

        `contexts` diambil dari tool_outputs, bukan dari result_summary di
        tool_calls: yang terakhir dipotong 500 karakter untuk audit. Juri yang
        melihat bukti lebih sedikit daripada yang dilihat composer akan
        memvonis jawaban sah sebagai halusinasi.

        Args:
            case: Satu baris dataset eval.
            reply: Jawaban agent beserta jejaknya.

        Returns:
            Trace siap ditulis ke JSONL.
        """
        return cls(
            id=str(case.get("id", "?")),
            question=str(case.get("question", "")),
            answer=reply.answer,
            contexts=list(reply.tool_outputs),
            retrieved_contexts=list(reply.retrieved_contexts),
            reference=case.get("reference"),
            reference_sections=list(case.get("reference_sections", [])),
            called_tools=[call.tool_name for call in reply.tool_calls],
        )


def write_traces(path: Path, traces: Iterable[EvalTrace]) -> int:
    """Tulis trace ke berkas JSONL.

    Args:
        path: Path berkas tujuan; direktori induknya dibuat kalau belum ada.
        traces: Trace yang akan ditulis.

    Returns:
        Jumlah baris yang ditulis.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [trace.model_dump_json() for trace in traces]
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    logger.info(f"{len(lines)} trace eval ditulis ke {path}")
    return len(lines)


def load_traces(path: Path) -> list[EvalTrace]:
    """Baca trace dari berkas JSONL.

    Args:
        path: Path berkas trace.

    Returns:
        Seluruh trace dalam berkas.

    Raises:
        FileNotFoundError: Kalau berkasnya tidak ada.
        ValueError: Kalau ada baris yang bukan JSON valid.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Berkas trace tidak ditemukan: {path}. "
            "Jalankan scripts/run_eval.py lebih dulu."
        )

    traces: list[EvalTrace] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            traces.append(EvalTrace.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"Baris {line_number} di {path} tidak valid: {exc}") from exc

    return traces


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word for word in words if len(word) > 3 and word not in _STOPWORDS}


class FaqSectionIndex:
    """Peta judul seksi FAQ ke isinya, untuk metrik retrieval tanpa juri LLM.

    Metrik DeepEval bergantung pada model juri yang bisa keliru. Indeks ini
    memberi pembanding deterministik: potongan yang terambil berasal dari seksi
    mana, dan apakah seksi itu memang yang diharapkan dataset.
    """

    def __init__(self, sections: dict[str, str]) -> None:
        self.sections = sections
        self._vocabulary = {
            title: _significant_words(body) for title, body in sections.items()
        }

    @classmethod
    def from_directory(cls, source_dir: Path | None = None) -> "FaqSectionIndex":
        """Bangun indeks dari seluruh dokumen Markdown di direktori sumber FAQ.

        Args:
            source_dir: Direktori dokumen FAQ; default dari setting.

        Returns:
            Indeks seksi siap pakai.

        Raises:
            FileNotFoundError: Kalau tidak ada dokumen Markdown yang bisa dibaca.
        """
        directory = source_dir or settings.faq_path
        sections: dict[str, str] = {}

        for document in sorted(Path(directory).glob("*.md")):
            sections.update(cls._split_sections(document.read_text(encoding="utf-8")))

        if not sections:
            raise FileNotFoundError(
                f"Tidak ada seksi FAQ yang terbaca di {directory}. "
                "Indeks seksi butuh dokumen Markdown ber-heading '## '."
            )

        logger.info(f"Indeks seksi FAQ memuat {len(sections)} seksi dari {directory}")
        return cls(sections)

    @staticmethod
    def _split_sections(markdown: str) -> dict[str, str]:
        matches = list(_SECTION_HEADING.finditer(markdown))
        sections: dict[str, str] = {}
        for position, match in enumerate(matches):
            start = match.end()
            end = (
                matches[position + 1].start()
                if position + 1 < len(matches)
                else len(markdown)
            )
            sections[match.group("title")] = markdown[start:end].strip()
        return sections

    def texts_for(self, titles: Iterable[str]) -> list[str]:
        """Ambil isi seksi berdasarkan judulnya.

        Args:
            titles: Judul seksi seperti tertulis di dataset.

        Returns:
            Isi tiap seksi, urut sesuai judul yang diminta.

        Raises:
            KeyError: Kalau ada judul yang tidak ada di dokumen. Sengaja keras:
                acuan yang menunjuk seksi tidak ada akan diam-diam menghasilkan
                recall nol dan terbaca seperti kegagalan retrieval.
        """
        missing = [title for title in titles if title not in self.sections]
        if missing:
            raise KeyError(
                f"Seksi FAQ tidak ditemukan: {', '.join(missing)}. "
                f"Seksi yang tersedia: {', '.join(sorted(self.sections))}"
            )
        return [self.sections[title] for title in titles]

    def locate(self, chunk: str) -> str | None:
        """Tebak seksi asal sebuah potongan berdasarkan tumpang tindih kata.

        Pencocokan tidak memakai substring karena chunker menyisipkan konteks
        heading dan memotong di batas kalimat, sehingga potongan tidak pernah
        persis sama dengan penggalan dokumen aslinya.

        Args:
            chunk: Teks potongan hasil retrieval.

        Returns:
            Judul seksi paling cocok, atau None kalau tidak ada yang cukup mirip.
        """
        words = _significant_words(chunk)
        if not words:
            return None

        best_title: str | None = None
        best_ratio = 0.0
        for title, vocabulary in self._vocabulary.items():
            ratio = len(words & vocabulary) / len(words)
            if ratio > best_ratio:
                best_title, best_ratio = title, ratio

        return best_title if best_ratio >= _MIN_OVERLAP_RATIO else None

    def section_hits(self, trace: EvalTrace) -> Iterator[bool]:
        """Nilai tiap potongan: berasal dari seksi yang diharapkan atau tidak.

        Args:
            trace: Trace yang punya reference_sections dan retrieved_contexts.

        Yields:
            True untuk potongan yang berasal dari salah satu seksi acuan.
        """
        expected = set(trace.reference_sections)
        for chunk in trace.retrieved_contexts:
            yield self.locate(chunk) in expected
