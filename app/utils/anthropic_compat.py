"""Jembatan kompatibilitas antara wrapper LLM LlamaIndex dan SDK anthropic 1.x."""

from typing import Any

from llama_index.llms.anthropic import Anthropic


class CompatAnthropic(Anthropic):
    """Wrapper Anthropic LlamaIndex yang aman dipakai dengan SDK anthropic 1.x.

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
