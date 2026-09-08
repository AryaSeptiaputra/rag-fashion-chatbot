"""Uji sifat ContextVar yang menjadi tumpuan seluruh pencatatan biaya.

Workflow LlamaIndex menjalankan tiap langkah agent sebagai task asyncio
terpisah yang mewarisi SALINAN konteks. Salinan itu memetakan variabel ke objek
yang sama, jadi mutasi terlihat oleh task induk sementara set() tidak. Uji di
berkas ini mengunci perilaku itu supaya tidak hilang saat seseorang "merapikan"
catat_respons menjadi pemanggilan set().
"""

import asyncio

from app.utils.usage import catat_respons, lacak_usage_giliran

from tests.utils.test_usage import bentuk_asli


class TestIsolasiAntarGiliran:
    """Request yang berjalan bersamaan tidak boleh saling menambahkan biaya."""

    async def test_dua_giliran_bersamaan_tidak_bocor(self) -> None:
        async def giliran(input_tokens: int) -> int:
            with lacak_usage_giliran() as usage:
                # Beri kesempatan giliran lain berjalan di antara dua panggilan.
                catat_respons(bentuk_asli(input_tokens=input_tokens))
                await asyncio.sleep(0)
                catat_respons(bentuk_asli(input_tokens=input_tokens))
                return usage.input_tokens

        pertama, kedua = await asyncio.gather(giliran(100), giliran(7))

        assert pertama == 200
        assert kedua == 14

    async def test_akumulator_dilepas_setelah_giliran_selesai(self) -> None:
        with lacak_usage_giliran() as usage:
            catat_respons(bentuk_asli(input_tokens=50))

        assert usage.input_tokens == 50

        # Di luar konteks, pencatatan tidak punya sasaran dan diam saja.
        catat_respons(bentuk_asli(input_tokens=999))
        assert usage.input_tokens == 50


class TestTaskAnak:
    """Kasus yang sesungguhnya terjadi di dalam workflow agent."""

    async def test_task_anak_terlihat_oleh_akumulator_induk(self) -> None:
        """Inilah situasi tiap langkah workflow LlamaIndex.

        Kalau catat_respons diubah jadi memanggil _usage_giliran.set(), uji ini
        gagal: set() di task anak tidak pernah naik ke induk, dan seluruh meter
        biaya diam-diam menjadi nol pada giliran yang memakai tool.
        """
        with lacak_usage_giliran() as usage:

            async def langkah_agent() -> None:
                catat_respons(bentuk_asli(input_tokens=1200, output_tokens=80))

            await asyncio.create_task(langkah_agent())

            assert usage.input_tokens == 1200
            assert usage.output_tokens == 80
            assert usage.llm_calls == 1

    async def test_beberapa_task_anak_terakumulasi(self) -> None:
        """Satu giliran bertool memanggil LLM lebih dari sekali."""
        with lacak_usage_giliran() as usage:

            async def langkah_agent() -> None:
                catat_respons(bentuk_asli(input_tokens=1000, output_tokens=50))

            await asyncio.gather(
                asyncio.create_task(langkah_agent()),
                asyncio.create_task(langkah_agent()),
            )

        assert usage.input_tokens == 2000
        assert usage.output_tokens == 100
        assert usage.llm_calls == 2
