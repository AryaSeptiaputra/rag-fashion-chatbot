"""Orkestrasi agent: merakit LLM, tool, memori, lalu menjalankan satu giliran."""

import re

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.anthropic import Anthropic

from app.config import settings
from app.models.chat import AgentReply, Bahasa, ToolCallRecord
from app.prompts.system import SYSTEM_PROMPT_BY_LANGUAGE
from app.services.catalog import CatalogService
from app.services.inventory import InventoryService
from app.services.memory import ConversationMemory
from app.services.order import OrderService
from app.services.retrieval import FAQRetriever
from app.tools.registry import ToolCallRecorder, build_tools, resolve_mode
from app.utils.logger import setup_logger
from app.utils.usage import hitung_biaya_usd, lacak_usage_giliran

logger = setup_logger(__name__)

# Penanda yang dipakai service layer saat data tidak ada. Kalau seluruh tool
# dalam satu giliran mengembalikan penanda ini, pertanyaannya dianggap tidak
# terjawab dan dicatat sebagai kandidat FAQ baru.
_NOT_FOUND_MARKERS = (
    "tidak ditemukan",
    "tidak ada di katalog",
    "tidak ada di database",
    "tidak berlaku",
    "tidak punya size chart",
)

# Klaim bahwa percakapan sudah diteruskan ke admin. Bentuk tawaran ("bisa saya
# teruskan?", "mau saya teruskan?") sengaja tidak ikut cocok, karena menawarkan
# bukan menjanjikan.
_ESCALATION_CLAIM_PATTERN_ID = re.compile(
    r"(?<!bisa )(?<!mau )(?<!boleh )(?:saya|aku)\s+"
    r"(?:sudah\s+|akan\s+|langsung\s+)?"
    r"(?:teruskan|sampaikan|hubungkan|laporkan)\w*\s+"
    r"(?:\w+\s+){0,3}?admin",
    re.IGNORECASE,
)

# Padanan Inggrisnya wajib ada, bukan pelengkap. Tanpa ini, menyalakan Bahasa
# Inggris berarti mematikan guardrail: "I've forwarded this to our admin" tidak
# akan cocok dengan pola Indonesia, eskalasinya tidak tercatat, dan permintaan
# pembeli hilang tanpa jejak. Bentuk tawaran ("can I forward this to an admin?")
# sengaja tidak ikut cocok, sama seperti versi Indonesia.
_ESCALATION_CLAIM_PATTERN_EN = re.compile(
    r"(?<!can )(?<!shall )(?<!may )(?<!should )"
    r"i(?:'ve|'ll|'m| have| will| am)?\s+"
    r"(?:already\s+|just\s+|now\s+)?"
    r"(?:forward|pass|escalat|report|connect|relay|sent|send)\w*\s+"
    r"(?:\w+\s+){0,4}?admin",
    re.IGNORECASE,
)

_ESCALATION_CLAIM_PATTERNS = {
    "id": _ESCALATION_CLAIM_PATTERN_ID,
    "en": _ESCALATION_CLAIM_PATTERN_EN,
}


class ChatbotService:
    """Menjalankan agent customer service untuk satu giliran percakapan."""

    def __init__(
        self,
        llm: Anthropic,
        faq_retriever: FAQRetriever,
        catalog_service: CatalogService,
        inventory_service: InventoryService,
        order_service: OrderService,
        memory: ConversationMemory,
    ) -> None:
        self.llm = llm
        self.faq_retriever = faq_retriever
        self.catalog_service = catalog_service
        self.inventory_service = inventory_service
        self.order_service = order_service
        self.memory = memory

    async def answer(
        self,
        session_id: str,
        message: str,
        channel: str = "web",
        language: Bahasa = "id",
    ) -> AgentReply:
        """Jawab satu pesan pembeli.

        Args:
            session_id: Identifier sesi dari klien.
            message: Pesan dari pembeli.
            channel: Kanal asal percakapan.
            language: Bahasa jawaban yang diminta pembeli.

        Returns:
            Jawaban chatbot beserta jejak tool yang dipakai.

        Raises:
            RuntimeError: Kalau agent gagal menyelesaikan giliran.
        """
        conversation_id = self.memory.start_session(session_id, channel)
        history = self.memory.load_history(conversation_id)

        recorder = ToolCallRecorder()
        agent = self._build_agent(conversation_id, recorder, language)

        logger.info(
            f"Menjalankan agent untuk sesi {session_id} "
            f"({len(history)} pesan riwayat)"
        )
        # max_iterations diterima di run(), bukan di konstruktor FunctionAgent.
        # early_stopping_method="generate" membuat agent menyusun jawaban saat
        # batas tercapai, bukan melempar exception ke pembeli.
        # Akumulator dibuka SEBELUM agent.run(), karena di situlah workflow
        # membuat task anak dan menyalin konteksnya.
        with lacak_usage_giliran() as usage:
            handler = agent.run(
                user_msg=message,
                chat_history=history,
                max_iterations=settings.agent_max_iterations,
                early_stopping_method="generate",
            )
            response = await handler

        answer = str(response).strip()
        tool_calls = list(recorder.records)
        cost_usd = hitung_biaya_usd(usage)

        if usage.llm_calls == 0:
            # Alarm untuk kasus paling berbahaya: jalur streaming tidak melewati
            # CompatAnthropic sama sekali, jadi biayanya tercatat nol padahal
            # saldo tetap terpakai. Periksa streaming=False di _build_agent().
            logger.warning(
                "Pemakaian token tidak terekam untuk giliran ini; "
                "periksa apakah FunctionAgent masih dibangun non-streaming"
            )

        self.memory.record_turn(
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=answer,
            tool_calls=tool_calls,
        )

        self._guard_unrecorded_escalation(
            conversation_id, message, answer, tool_calls, language
        )

        if self._is_unanswered(tool_calls):
            self.memory.log_unanswered(conversation_id, message)

        logger.info(
            f"Giliran selesai dengan {len(tool_calls)} tool call: "
            f"{[call.tool_name for call in tool_calls]}"
        )
        return AgentReply(
            answer=answer,
            tool_calls=tool_calls,
            usage=usage,
            cost_usd=cost_usd,
            citations=list(recorder.citations),
            mode=resolve_mode(tool_calls),
        )

    def _build_agent(
        self,
        conversation_id: str,
        recorder: ToolCallRecorder,
        language: Bahasa = "id",
    ) -> FunctionAgent:
        def escalate_handler(reason: str, contact: str | None = None) -> str:
            """Catat eskalasi ke database lalu balas ke agent."""
            self.memory.escalate(conversation_id, reason, contact)
            return (
                "Permintaan sudah diteruskan ke admin. Admin akan menghubungi "
                f"pembeli lewat {contact or settings.support_contact}. "
                "Sampaikan ke pembeli bahwa admin akan segera membalas."
            )

        tools = build_tools(
            faq_retriever=self.faq_retriever,
            catalog_service=self.catalog_service,
            inventory_service=self.inventory_service,
            order_service=self.order_service,
            escalate_handler=escalate_handler,
            recorder=recorder,
        )

        # streaming=False wajib dan tidak boleh dihapus. Defaultnya True, dan
        # jalur streaming memakai astream_chat yang TIDAK melewati override
        # pencatat usage di CompatAnthropic -- akibatnya seluruh biaya tercatat
        # nol tanpa satu pun error. Dijaga oleh tests/services/test_agent_streaming.py.
        return FunctionAgent(
            tools=tools,
            llm=self.llm,
            system_prompt=SYSTEM_PROMPT_BY_LANGUAGE[language],
            streaming=False,
        )

    def _guard_unrecorded_escalation(
        self,
        conversation_id: str,
        user_message: str,
        answer: str,
        tool_calls: list[ToolCallRecord],
        language: Bahasa = "id",
    ) -> None:
        """Catat eskalasi yang dijanjikan di teks tapi tool-nya tidak dipanggil.

        Sesekali model menulis "saya teruskan ke admin" tanpa benar-benar
        memanggil escalate_to_human. Akibatnya pembeli menunggu balasan yang
        tidak akan pernah datang, dan permintaannya hilang tanpa jejak. Efek
        samping sepenting itu tidak boleh bergantung pada kepatuhan model, jadi
        di sini janji tersebut ditepati oleh kode.

        Baris eskalasi diberi penanda [otomatis] dan sengaja TIDAK ditambahkan
        ke tool_calls, supaya eval harness tetap melaporkan kegagalan model apa
        adanya alih-alih menutupinya.

        Args:
            conversation_id: UUID percakapan.
            user_message: Pesan asli pembeli.
            answer: Jawaban yang dihasilkan agent.
            tool_calls: Tool yang benar-benar dipanggil pada giliran ini.
        """
        if any(call.tool_name == "escalate_to_human" for call in tool_calls):
            return
        if not _ESCALATION_CLAIM_PATTERNS[language].search(answer):
            return

        logger.warning(
            "Jawaban mengaku meneruskan ke admin tanpa memanggil escalate_to_human; "
            "eskalasi dicatat otomatis agar permintaan pembeli tidak hilang"
        )
        self.memory.escalate(
            conversation_id,
            reason=f"[otomatis] {user_message}",
        )

    @staticmethod
    def _is_unanswered(tool_calls: list[ToolCallRecord]) -> bool:
        """Tentukan apakah giliran ini gagal menemukan data."""
        data_calls = [
            call for call in tool_calls if call.tool_name != "escalate_to_human"
        ]
        if not data_calls:
            return any(call.tool_name == "escalate_to_human" for call in tool_calls)

        return all(
            call.is_error
            or any(
                marker in (call.result_summary or "").lower()
                for marker in _NOT_FOUND_MARKERS
            )
            for call in data_calls
        )
