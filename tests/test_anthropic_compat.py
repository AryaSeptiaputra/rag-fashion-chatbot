"""Guard kompatibilitas wrapper LLM LlamaIndex terhadap SDK anthropic 1.x.

Regresi yang dijaga: SDK anthropic 1.x menghapus temperature/top_p/top_k dari
signature Messages.create(), sementara wrapper LlamaIndex tetap mengirim
temperature untuk model di luar daftar internalnya. Tanpa shim, setiap
panggilan ke claude-haiku-4-5 gagal dengan TypeError.
"""

import inspect

import pytest
from anthropic.resources.messages import Messages
from llama_index.llms.anthropic import Anthropic

from app.utils.anthropic_compat import CompatAnthropic

MODEL = "claude-haiku-4-5"
DUMMY_KEY = "sk-ant-dummy"

SDK_ACCEPTED_PARAMS = set(inspect.signature(Messages.create).parameters)


def build(cls: type[Anthropic], **overrides: object) -> Anthropic:
    """Bangun wrapper LLM dengan kredensial dummy."""
    kwargs: dict[str, object] = {
        "model": MODEL,
        "api_key": DUMMY_KEY,
        "max_tokens": 2048,
        "temperature": 0.2,
    }
    kwargs.update(overrides)
    return cls(**kwargs)


def test_sdk_really_dropped_sampling_params() -> None:
    # Kalau assertion ini gagal, SDK sudah mengembalikan parameter sampling
    # dan shim di app/utils/anthropic_compat.py bisa dipertimbangkan untuk dihapus.
    assert "temperature" not in SDK_ACCEPTED_PARAMS
    assert "top_p" not in SDK_ACCEPTED_PARAMS
    assert "top_k" not in SDK_ACCEPTED_PARAMS
    assert "extra_body" in SDK_ACCEPTED_PARAMS


def test_upstream_wrapper_still_sends_temperature() -> None:
    # Mendokumentasikan penyebab masalah. Kalau llama-index memperbaikinya,
    # test ini gagal dan shim boleh dievaluasi ulang.
    kwargs = build(Anthropic)._get_all_kwargs()

    assert "temperature" in kwargs


def test_compat_sends_only_params_the_sdk_accepts() -> None:
    kwargs = build(CompatAnthropic)._get_all_kwargs()

    rejected = set(kwargs) - SDK_ACCEPTED_PARAMS
    assert not rejected, f"parameter ini akan ditolak SDK: {sorted(rejected)}"


def test_compat_preserves_temperature_via_extra_body() -> None:
    # Temperature rendah menjaga konsistensi jawaban CS, jadi tidak boleh
    # sekadar dibuang; Haiku 4.5 masih menerimanya di level API.
    kwargs = build(CompatAnthropic)._get_all_kwargs()

    assert kwargs["extra_body"]["temperature"] == 0.2


def test_compat_keeps_model_and_max_tokens() -> None:
    kwargs = build(CompatAnthropic)._get_all_kwargs()

    assert kwargs["model"] == MODEL
    assert kwargs["max_tokens"] == 2048


def test_compat_does_not_clobber_existing_extra_body() -> None:
    llm = build(
        CompatAnthropic,
        additional_kwargs={"extra_body": {"metadata": {"tenant": "brand"}}},
    )

    extra_body = llm._get_all_kwargs()["extra_body"]

    assert extra_body["metadata"] == {"tenant": "brand"}
    assert extra_body["temperature"] == 0.2


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-sonnet-5"])
def test_compat_is_a_noop_for_models_upstream_already_handles(model: str) -> None:
    # Untuk model yang sudah ada di ANTHROPIC_NO_TEMP_MODELS, wrapper induk
    # tidak mengirim temperature; shim harus diam saja, bukan menambahkannya.
    kwargs = build(CompatAnthropic, model=model)._get_all_kwargs()

    assert "temperature" not in kwargs
    assert "temperature" not in kwargs.get("extra_body", {})
