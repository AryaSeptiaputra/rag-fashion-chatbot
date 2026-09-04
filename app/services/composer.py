"""Penyusunan jawaban akhir dari hasil tool, terpisah dari pemilihan tool."""

from llama_index.core.base.llms.types import ChatMessage as LlamaChatMessage
from llama_index.core.base.llms.types import MessageRole
from llama_index.core.llms import LLM

from app.config import settings
from app.models.chat import ToolObservation
from app.prompts.composer import COMPOSER_PROMPT
from app.utils.errors import LLM_UNAVAILABLE_ERRORS
from app.utils.logger import setup_logger
from app.utils.text import strip_thinking

logger = setup_logger(__name__)

# Batas ukuran blok bukti. num_ctx yang jebol tidak melempar error: Ollama
# diam-diam memotong prompt dari kiri, yang justru membuang system prompt dan
# menyisakan bukti tanpa aturan groundedness-nya.
_MAX_CHARS_PER_OBSERVATION = 1500
_MAX_EVIDENCE_CHARS = 6000
_TRUNCATION_MARKER = "\n...(dipotong)"

_EMPTY_EVIDENCE = (
    "(tidak ada hasil tool pada giliran ini -- kamu tidak punya fakta apa pun "
    "untuk disampaikan)"
)


class AnswerComposer:
    """Menyusun jawaban akhir yang hanya bersandar pada hasil tool.

    Tahap ini tidak punya tool sendiri dan tidak melihat jawaban versi agent,
    jadi tidak ada jalan bagi halusinasi tahap sebelumnya untuk lolos ke
    pembeli lewat sini.
    """

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    async def compose(
        self,
        question: str,
        observations: list[ToolObservation],
        history: list[LlamaChatMessage] | None = None,
    ) -> str:
        """Susun jawaban akhir untuk satu giliran percakapan.

        Args:
            question: Pesan pembeli pada giliran ini.
            observations: Hasil utuh seluruh tool yang dipanggil giliran ini.
            history: Riwayat percakapan; hanya beberapa pesan terakhir dipakai.

        Returns:
            Jawaban siap kirim, atau string kosong kalau composer gagal
            sehingga pemanggil bisa jatuh balik ke jawaban agent.
        """
        prompt = self._build_prompt(question, observations, history or [])
        messages = [
            LlamaChatMessage(role=MessageRole.SYSTEM, content=COMPOSER_PROMPT),
            LlamaChatMessage(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = await self.llm.achat(messages)
        except LLM_UNAVAILABLE_ERRORS as exc:
            logger.warning(
                f"Composer gagal dihubungi, jawaban agent dipakai apa adanya: {exc}"
            )
            return ""

        answer = strip_thinking(str(response.message.content or ""))
        if not answer:
            logger.warning("Composer mengembalikan jawaban kosong")
        return answer

    def _build_prompt(
        self,
        question: str,
        observations: list[ToolObservation],
        history: list[LlamaChatMessage],
    ) -> str:
        sections = []

        recent = self._render_history(history)
        if recent:
            sections.append(f"PERCAKAPAN SEBELUMNYA:\n{recent}")

        sections.append(f"PESAN PEMBELI SEKARANG:\n{question.strip()}")
        sections.append(f"BUKTI:\n{self._render_evidence(observations)}")
        sections.append(
            "Tulis jawaban untuk pembeli sekarang, hanya berdasarkan BUKTI di atas."
        )
        return "\n\n".join(sections)

    @staticmethod
    def _render_history(history: list[LlamaChatMessage]) -> str:
        """Ambil beberapa pesan terakhir sebagai konteks anafora.

        Riwayat dipakai hanya untuk memahami rujukan seperti "yang tadi itu",
        bukan sebagai sumber fakta, jadi sengaja dipotong pendek.

        Args:
            history: Riwayat percakapan lengkap.

        Returns:
            Riwayat singkat berlabel peran, atau string kosong kalau tidak ada.
        """
        limit = max(settings.composer_history_turns, 0) * 2
        if limit == 0 or not history:
            return ""

        labels = {MessageRole.USER: "Pembeli", MessageRole.ASSISTANT: "Asisten"}
        lines = [
            f"{labels[message.role]}: {str(message.content).strip()}"
            for message in history[-limit:]
            if message.role in labels and str(message.content).strip()
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_evidence(observations: list[ToolObservation]) -> str:
        """Rakit hasil tool jadi blok bukti bernomor.

        Argumen tool ikut ditulis supaya composer tahu bukti mana menjawab
        pertanyaan yang mana saat satu giliran memanggil beberapa tool.

        Args:
            observations: Hasil utuh seluruh tool pada giliran ini.

        Returns:
            Blok bukti siap tempel, atau penanda kosong kalau tidak ada tool
            yang dipanggil.
        """
        if not observations:
            return _EMPTY_EVIDENCE

        blocks: list[str] = []
        used_chars = 0
        for position, observation in enumerate(observations, start=1):
            if used_chars >= _MAX_EVIDENCE_CHARS:
                blocks.append(f"[Bukti {position} dan seterusnya dipotong]")
                break

            budget = min(
                _MAX_CHARS_PER_OBSERVATION, _MAX_EVIDENCE_CHARS - used_chars
            )
            result = observation.result.strip()
            if len(result) > budget:
                result = result[:budget].rstrip() + _TRUNCATION_MARKER

            signature = AnswerComposer._format_call(observation)
            blocks.append(f"[Bukti {position} - {signature}]\n{result}")
            used_chars += len(result)

        return "\n\n".join(blocks)

    @staticmethod
    def _format_call(observation: ToolObservation) -> str:
        arguments = ", ".join(
            f"{name}={value!r}"
            for name, value in observation.arguments.items()
            if value is not None
        )
        return f"{observation.tool_name}({arguments})"
