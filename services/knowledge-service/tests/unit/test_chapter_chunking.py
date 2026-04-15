"""K15.9 — chapter chunking unit tests (pure, no Neo4j)."""

from __future__ import annotations

import pytest

from app.extraction.pattern_extractor import (
    _split_chapter_into_chunks,
)


def test_invalid_budget_raises():
    with pytest.raises(ValueError):
        _split_chapter_into_chunks("hello", budget=0)
    with pytest.raises(ValueError):
        _split_chapter_into_chunks("hello", budget=-5)


def test_empty_returns_empty():
    assert _split_chapter_into_chunks("") == []
    assert _split_chapter_into_chunks("   \n\n  \n") == []


def test_single_short_paragraph_single_chunk():
    out = _split_chapter_into_chunks("Kai met Zhao.", budget=100)
    assert out == ["Kai met Zhao."]


def test_merges_small_paragraphs_up_to_budget():
    para_a = "Kai met Zhao at the river."
    para_b = "Drake watched from the trees."
    text = f"{para_a}\n\n{para_b}"
    out = _split_chapter_into_chunks(text, budget=200)
    assert len(out) == 1
    assert para_a in out[0]
    assert para_b in out[0]


def test_splits_when_budget_would_overflow():
    para_a = "A" * 50
    para_b = "B" * 50
    para_c = "C" * 50
    text = f"{para_a}\n\n{para_b}\n\n{para_c}"
    out = _split_chapter_into_chunks(text, budget=60)
    assert len(out) == 3
    assert out[0] == para_a
    assert out[1] == para_b
    assert out[2] == para_c


def test_oversized_paragraph_is_hard_sliced():
    big = "X" * 250
    out = _split_chapter_into_chunks(big, budget=100)
    assert len(out) == 3
    assert out[0] == "X" * 100
    assert out[1] == "X" * 100
    assert out[2] == "X" * 50


def test_oversized_paragraph_flushes_buffered_small_ones():
    small = "small paragraph."
    big = "Y" * 250
    text = f"{small}\n\n{big}"
    out = _split_chapter_into_chunks(text, budget=100)
    # First chunk is the buffered small paragraph, then three
    # hard-sliced chunks of the big one.
    assert out[0] == small
    assert out[1] == "Y" * 100
    assert out[2] == "Y" * 100
    assert out[3] == "Y" * 50


def test_k15_9_r2_crlf_line_endings_split_paragraphs():
    """K15.9-R2/I1: Windows-authored chapters use \\r\\n\\r\\n between
    paragraphs. The chunker must normalize before splitting so each
    paragraph is still a separate chunk candidate — otherwise the
    whole body collapses to one run and hits the hard-slice path."""
    para_a = "Kai met Zhao."
    para_b = "Drake watched from the trees."
    para_c = "Phoenix arrived at dawn."
    text = f"{para_a}\r\n\r\n{para_b}\r\n\r\n{para_c}"
    out = _split_chapter_into_chunks(text, budget=35)
    assert len(out) == 3
    assert out[0] == para_a
    assert out[1] == para_b
    assert out[2] == para_c


def test_k15_9_r2_bare_cr_line_endings_normalized():
    """Old Mac-style `\\r`-only separators should also normalize,
    not because anyone ships text with them but because mixed
    `\\r\\n` + `\\r` stragglers shouldn't break chunking."""
    text = "Para one.\rPara two.\r\rPara three."
    out = _split_chapter_into_chunks(text, budget=50)
    # After normalization: "Para one.\nPara two.\n\nPara three."
    # That's two paragraphs: "Para one.\nPara two." and "Para three."
    assert len(out) == 1 or len(out) == 2
    joined = "\n\n".join(out)
    assert "Para one." in joined
    assert "Para two." in joined
    assert "Para three." in joined


def test_no_content_loss_across_normal_chapter():
    paragraphs = [f"Paragraph {i} about Kai." for i in range(20)]
    text = "\n\n".join(paragraphs)
    out = _split_chapter_into_chunks(text, budget=100)
    joined = "\n\n".join(out)
    for para in paragraphs:
        assert para in joined
