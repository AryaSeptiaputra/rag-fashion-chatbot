"""Manajemen riwayat percakapan yang dipersistensi di Supabase."""

from llama_index.core.base.llms.types import ChatMessage as LlamaChatMessage
from llama_index.core.base.llms.types import MessageRole

from app.config import settings
from app.models.chat import ChatMessage, ToolCallRecord
from app.repositories.chat import ChatRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ROLE_MAP = {
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
}


class ConversationMemory:
    """Jembatan antara riwayat percakapan di Supabase dan format pesan LlamaIndex."""

    def __init__(
        self,
        chat_repository: ChatRepository,
        turn_limit: int | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.turn_limit = turn_limit or settings.history_turn_limit

    def start_session(self, session_id: str, channel: str = "web") -> str:
        """Ambil atau buat percakapan untuk sebuah session_id.

        Args:
            session_id: Identifier sesi dari klien.
            channel: Kanal asal percakapan.

        Returns:
            UUID percakapan.
        """
        return self.chat_repository.get_or_create_conversation(session_id, channel)

    def load_history(self, conversation_id: str) -> list[LlamaChatMessage]:
        """Muat riwayat percakapan dalam format pesan LlamaIndex.

        Args:
            conversation_id: UUID percakapan.

        Returns:
            List pesan urut kronologis, siap dipakai sebagai chat_history agent.
        """
        history = self.chat_repository.get_history(conversation_id, limit=self.turn_limit)
        return [self._to_llama_message(message) for message in history]

    def record_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        tool_calls: list[ToolCallRecord],
    ) -> str:
        """Simpan satu giliran percakapan beserta jejak tool-nya.

        Args:
            conversation_id: UUID percakapan.
            user_message: Pesan dari pembeli.
            assistant_message: Jawaban chatbot.
            tool_calls: Tool yang dipanggil selama giliran ini.

        Returns:
            UUID pesan assistant, dipakai eval harness untuk membaca audit tool.
        """
        self.chat_repository.save_message(conversation_id, "user", user_message)
        assistant_message_id = self.chat_repository.save_message(
            conversation_id, "assistant", assistant_message
        )
        self.chat_repository.save_tool_calls(assistant_message_id, tool_calls)

        if not tool_calls:
            logger.info("Giliran dijawab tanpa tool call")

        return assistant_message_id

    def escalate(
        self, conversation_id: str, reason: str, contact: str | None = None
    ) -> str:
        """Catat eskalasi ke admin manusia.

        Args:
            conversation_id: UUID percakapan.
            reason: Alasan eskalasi.
            contact: Kontak yang ditinggalkan pembeli.

        Returns:
            UUID baris eskalasi.
        """
        return self.chat_repository.create_escalation(conversation_id, reason, contact)

    def log_unanswered(self, conversation_id: str, query: str) -> None:
        """Catat pertanyaan yang tidak terjawab sebagai kandidat FAQ baru.

        Args:
            conversation_id: UUID percakapan.
            query: Pertanyaan asli pembeli.
        """
        self.chat_repository.log_unanswered(conversation_id, query)

    @staticmethod
    def _to_llama_message(message: ChatMessage) -> LlamaChatMessage:
        return LlamaChatMessage(
            role=_ROLE_MAP.get(message.role, MessageRole.USER),
            content=message.content,
        )
