"""Jembatan kompatibilitas antara wrapper LLM LlamaIndex dan SDK anthropic 1.x."""

from collections.abc import Sequence
from typing import Any

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.llms.anthropic import Anthropic

from app.utils.usage import catat_respons


class CompatAnthropic(Anthropic):
    """Wrapper Anthropic LlamaIndex: tambalan SDK 1.x plus pencatat pemakaian.

    Dua tanggung jawab, keduanya menutup celah antara wrapper LlamaIndex dan
    SDK anthropic 1.x.

    ## 1. Memindahkan parameter sampling ke extra_body

    SDK anthropic 1.x menghapus temperature, top_p, dan top_k dari signature
    Messages.create(). Wrapper LlamaIndex tetap menyisipkan temperature untuk
    model di luar daftar internal ANTHROPIC_NO_TEMP_MODELS -- daftar itu hanya
    memuat model yang API-nya menolak temperature (Opus 4.7/4.8/5, Fable 5,
    Sonnet 5), bukan model yang SDK-nya tidak lagi mengekspos parameter itu.
    Akibatnya Claude Haiku 4.5 gagal dengan:

        TypeError: Messages.create() got an unexpected keyword argument 'temperature'

    Kelas ini memindahkan temperature ke extra_body, yang diteruskan SDK apa
    adanya ke body request. Haiku 4.5 masih menerima temperature di level API,
    jadi nilainya tetap berlaku dan jawaban tetap konsisten.

    Override ini menetralkan diri sendiri: kalau versi llama-index berikutnya
    berhenti mengirim temperature, pop() tidak menemukan apa pun dan perilaku
    kelas ini sama persis dengan induknya.

    ## 2. Mencatat pemakaian token tiap panggilan

    chat() dan achat() dibungkus supaya jumlah token tiap panggilan masuk ke
    akumulator giliran di app.utils.usage. Ini satu-satunya titik yang melihat
    SELURUH panggilan dalam satu giliran; AgentOutput yang diterima
    ChatbotService hanya membawa yang terakhir.

    Pasangannya ada di ChatbotService: FunctionAgent harus dibangun dengan
    streaming=False, karena defaultnya True dan jalur streaming memakai
    astream_chat yang tidak lewat sini sama sekali.
    """

    @property
    def _model_kwargs(self) -> dict[str, Any]:
        """Kwargs model dengan parameter sampling dipindah ke extra_body.

        Returns:
            Kwargs yang seluruh kuncinya diterima Messages.create() SDK 1.x.
        """
        kwargs = dict(super()._model_kwargs)
        extra_body = dict(kwargs.get("extra_body") or {})

        for parameter in ("temperature", "top_p", "top_k"):
            value = kwargs.pop(parameter, None)
            if value is not None:
                extra_body.setdefault(parameter, value)

        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        """Jalankan chat async, lalu catat pemakaian tokennya.

        Pencatatan ditaruh di sini, bukan di ChatbotService, karena satu giliran
        dengan tool memicu beberapa panggilan sekaligus: satu per iterasi untuk
        memilih tool, satu lagi untuk menulis jawaban. Objek AgentOutput yang
        diterima ChatbotService hanya membawa panggilan terakhir, sehingga
        mencatat dari sana akan melewatkan sebagian besar biaya.

        Args:
            messages: Riwayat percakapan yang dikirim ke model.
            **kwargs: Parameter tambahan untuk Messages.create().

        Returns:
            Respons dari induk, tidak diubah sama sekali.
        """
        # Sengaja TIDAK didekorasi @llm_chat_callback(): metode induk sudah
        # membawanya, dan mendekorasi ulang membuat callback berbunyi dua kali.
        response = await super().achat(messages, **kwargs)
        catat_respons(response.raw)
        return response

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Jalankan chat sinkron, lalu catat pemakaian tokennya.

        Args:
            messages: Riwayat percakapan yang dikirim ke model.
            **kwargs: Parameter tambahan untuk Messages.create().

        Returns:
            Respons dari induk, tidak diubah sama sekali.
        """
        response = super().chat(messages, **kwargs)
        catat_respons(response.raw)
        return response
