"""Test pembersih blok penalaran dari keluaran model."""

from app.utils.text import strip_thinking


def test_closed_block_is_removed() -> None:
    raw = "<think>pikir dulu</think>Halo Kak, stoknya masih ada."

    assert strip_thinking(raw) == "Halo Kak, stoknya masih ada."


def test_multiple_blocks_are_removed() -> None:
    raw = "<think>satu</think>Halo Kak.<think>dua</think> Ada yang bisa dibantu?"

    assert strip_thinking(raw) == "Halo Kak. Ada yang bisa dibantu?"


def test_unclosed_block_swallows_the_rest() -> None:
    # Jawaban yang terpotong di tengah penalaran lebih baik hilang sama sekali
    # daripada terkirim setengah jadi ke pembeli.
    raw = "Halo Kak.<think>masih mikir dan kehabisan token"

    assert strip_thinking(raw) == "Halo Kak."


def test_stray_closing_tag_is_removed() -> None:
    raw = "sisa penalaran</think> Halo Kak."

    assert strip_thinking(raw) == "sisa penalaran Halo Kak."


def test_text_without_block_is_only_stripped() -> None:
    raw = "  Halo Kak, ada yang bisa dibantu?  "

    assert strip_thinking(raw) == "Halo Kak, ada yang bisa dibantu?"


def test_answer_that_is_entirely_thinking_becomes_empty() -> None:
    raw = "<think>hanya penalaran, tidak ada jawaban</think>"

    assert strip_thinking(raw) == ""
