"""Akses data percakapan chatbot: sesi, pesan, audit tool call, eskalasi."""

from typing import Any

from postgrest.exceptions import APIError

from app.models.chat import ChatMessage, ToolCallRecord
from app.repositories.base import BaseRepository, RepositoryError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChatRepository(BaseRepository):
    """Persistensi riwayat percakapan dan jejak tool ke Supabase."""

    def get_or_create_conversation(self, session_id: str, channel: str = "web") -> str:
        """Ambil id percakapan untuk session_id, buat baru kalau belum ada.

        Args:
            session_id: Identifier sesi dari klien.
            channel: Kanal asal percakapan.

        Returns:
            UUID percakapan sebagai string.

        Raises:
            RepositoryError: Kalau operasi database gagal.
        """
        existing = self.select_view(
            "conversations", filters={"session_id": session_id}, columns="id", limit=1
        )
        if existing:
            return str(existing[0]["id"])

        created = self._insert(
            "conversations", {"session_id": session_id, "channel": channel}
        )
        return str(created["id"])

    def get_history(self, conversation_id: str, limit: int = 10) -> list[ChatMessage]:
        """Ambil pesan terakhir dalam satu percakapan, urut kronologis.

        Args:
            conversation_id: UUID percakapan.
            limit: Jumlah pesan terakhir yang diambil.

        Returns:
            List pesan dari yang paling lama ke paling baru.

        Raises:
            RepositoryError: Kalau operasi database gagal.
        """
        try:
            response = (
                self.client.table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except APIError as exc:
            logger.error(f"Gagal membaca history percakapan: {exc.message}", exc_info=True)
            raise RepositoryError("Gagal membaca riwayat percakapan") from exc

        rows = self._as_rows(response.data)
        return [ChatMessage.model_validate(row) for row in reversed(rows)]

    def save_message(self, conversation_id: str, role: str, content: str) -> str:
        """Simpan satu pesan percakapan.

        Args:
            conversation_id: UUID percakapan.
            role: "user" atau "assistant".
            content: Isi pesan.

        Returns:
            UUID pesan yang baru dibuat.

        Raises:
            RepositoryError: Kalau operasi database gagal.
        """
        created = self._insert(
            "messages",
            {"conversation_id": conversation_id, "role": role, "content": content},
        )
        return str(created["id"])

    def save_tool_calls(self, message_id: str, tool_calls: list[ToolCallRecord]) -> None:
        """Simpan jejak tool call yang menghasilkan satu pesan assistant.

        Kegagalan audit tidak boleh menjatuhkan percakapan yang sudah berhasil,
        jadi error di sini hanya di-log.

        Args:
            message_id: UUID pesan assistant terkait.
            tool_calls: Jejak tool yang dipanggil selama giliran tersebut.
        """
        if not tool_calls:
            return

        payload = [
            {
                "message_id": message_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_summary": call.result_summary,
                "is_error": call.is_error,
                "latency_ms": call.latency_ms,
            }
            for call in tool_calls
        ]
        try:
            self.client.table("message_tool_calls").insert(payload).execute()
        except APIError as exc:
            logger.warning(f"Gagal menyimpan audit tool call: {exc.message}", exc_info=True)

    def create_escalation(
        self, conversation_id: str, reason: str, contact: str | None = None
    ) -> str:
        """Catat permintaan eskalasi ke admin manusia.

        Args:
            conversation_id: UUID percakapan.
            reason: Alasan eskalasi.
            contact: Kontak yang ditinggalkan pembeli, kalau ada.

        Returns:
            UUID baris eskalasi.

        Raises:
            RepositoryError: Kalau operasi database gagal.
        """
        created = self._insert(
            "escalations",
            {"conversation_id": conversation_id, "reason": reason, "contact": contact},
        )
        self._update_status(conversation_id, "escalated")
        return str(created["id"])

    def log_unanswered(self, conversation_id: str, query: str) -> None:
        """Catat pertanyaan yang tidak terjawab sebagai kandidat FAQ baru.

        Args:
            conversation_id: UUID percakapan.
            query: Pertanyaan asli pembeli.
        """
        try:
            self.client.table("unanswered_queries").insert(
                {"conversation_id": conversation_id, "query": query}
            ).execute()
        except APIError as exc:
            logger.warning(f"Gagal mencatat unanswered query: {exc.message}", exc_info=True)

    def list_tool_calls_for_message(self, message_id: str) -> list[dict[str, Any]]:
        """Baca audit tool call satu pesan. Dipakai eval harness.

        Args:
            message_id: UUID pesan assistant.

        Returns:
            List baris audit tool call.
        """
        return self.select_view("message_tool_calls", filters={"message_id": message_id})

    def _insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.table(table).insert(payload).execute()
        except APIError as exc:
            logger.error(f"Insert ke {table} gagal: {exc.message}", exc_info=True)
            raise RepositoryError(f"Gagal menyimpan data ke {table}") from exc

        rows = self._as_rows(response.data)
        if not rows:
            raise RepositoryError(f"Insert ke {table} tidak mengembalikan baris")
        return rows[0]

    def _update_status(self, conversation_id: str, status: str) -> None:
        try:
            self.client.table("conversations").update({"status": status}).eq(
                "id", conversation_id
            ).execute()
        except APIError as exc:
            logger.warning(f"Gagal mengubah status percakapan: {exc.message}", exc_info=True)
