"""Orkestrasi agent: merakit LLM, tool, memori, lalu menjalankan satu giliran."""

import re

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import LLM

from app.config import settings
from app.models.chat import AgentReply, ToolCallRecord
from app.prompts.system import SYSTEM_PROMPT
from app.services.catalog import CatalogService
from app.services.composer import AnswerComposer
from app.services.inventory import InventoryService
from app.services.memory import ConversationMemory
from app.services.order import OrderService
from app.services.retrieval import FAQRetriever
from app.tools.registry import ToolCallRecorder, build_tools
from app.utils.logger import setup_logger
from app.utils.text import strip_thinking

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
_ESCALATION_CLAIM_PATTERN = re.compile(
    r"(?<!bisa )(?<!mau )(?<!boleh )(?:saya|aku)\s+"
    r"(?:sudah\s+|akan\s+|langsung\s+)?"
    r"(?:teruskan|sampaikan|hubungkan|laporkan)\w*\s+"
    r"(?:\w+\s+){0,3}?admin",
    re.IGNORECASE,
)


class ChatbotService:
    """Menjalankan agent customer service untuk satu giliran percakapan."""

    def __init__(
        self,
        llm: LLM,
        composer: AnswerComposer,
        faq_retriever: FAQRetriever,
        catalog_service: CatalogService,
        inventory_service: InventoryService,
        order_service: OrderService,
        memory: ConversationMemory,
    ) -> None:
        self.llm = llm
        self.composer = composer
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
    ) -> AgentReply:
        """Jawab satu pesan pembeli.

        Args:
            session_id: Identifier sesi dari klien.
            message: Pesan dari pembeli.
            channel: Kanal asal percakapan.

        Returns:
            Jawaban chatbot beserta jejak tool yang dipakai.

        Raises:
            RuntimeError: Kalau agent gagal menyelesaikan giliran.
        """
        conversation_id = self.memory.start_session(session_id, channel)
        history = self.memory.load_history(conversation_id)

        recorder = ToolCallRecorder()
        agent = self._build_agent(conversation_id, recorder)

        logger.info(
            f"Menjalankan agent untuk sesi {session_id} "
            f"({len(history)} pesan riwayat)"
        )
        # max_iterations diterima di run(), bukan di konstruktor FunctionAgent.
        # early_stopping_method="generate" membuat agent menyusun jawaban saat
        # batas tercapai, bukan melempar exception ke pembeli.
        handler = agent.run(
            user_msg=message,
            chat_history=history,
            max_iterations=settings.agent_max_iterations,
            early_stopping_method="generate",
        )
        response = await handler

        # Jawaban tahap agent hanya dipakai kalau composer gagal. Selebihnya
        # dibuang: yang dikirim ke pembeli harus jawaban yang disusun semata
        # dari hasil tool, bukan dari kalimat yang dirangkai sambil memilih tool.
        agent_answer = strip_thinking(str(response))
        answer = (
            await self.composer.compose(
                question=message,
                observations=recorder.observations,
                history=history,
            )
            or agent_answer
        )
        tool_calls = list(recorder.records)

        self.memory.record_turn(
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=answer,
            tool_calls=tool_calls,
        )

        self._guard_unrecorded_escalation(conversation_id, message, answer, tool_calls)

        if self._is_unanswered(tool_calls):
            self.memory.log_unanswered(conversation_id, message)

        logger.info(
            f"Giliran selesai dengan {len(tool_calls)} tool call: "
            f"{[call.tool_name for call in tool_calls]}"
        )
        return AgentReply(
            answer=answer,
            tool_calls=tool_calls,
            tool_outputs=[
                observation.result for observation in recorder.observations
            ],
            retrieved_contexts=[
                context
                for observation in recorder.observations
                for context in observation.contexts
            ],
        )

    def _build_agent(
        self, conversation_id: str, recorder: ToolCallRecorder
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

        return FunctionAgent(
            tools=tools,
            llm=self.llm,
            system_prompt=SYSTEM_PROMPT,
        )

    def _guard_unrecorded_escalation(
        self,
        conversation_id: str,
        user_message: str,
        answer: str,
        tool_calls: list[ToolCallRecord],
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
        if not _ESCALATION_CLAIM_PATTERN.search(answer):
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
