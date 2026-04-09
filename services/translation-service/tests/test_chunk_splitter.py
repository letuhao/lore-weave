"""
Unit tests for chunk_splitter — V2 CJK-aware token estimation.

Covers:
- estimate_tokens: CJK-aware (CJK chars at 1.5 c/t, Latin at 4.0 c/t)
- _is_cjk: character classification
- split_chapter: empty text, short text (1 chunk), paragraph-break split,
  Latin sentence-end split, CJK sentence-end split,
  whitespace fallback, hard-split fallback
- CJK-specific: split_chapter respects CJK chars-per-token ratio
- Invariants: no empty chunks, every chunk within budget tolerance
"""
import pytest

from app.workers.chunk_splitter import (
    estimate_tokens,
    split_chapter,
    _is_cjk,
    _CJK_CHARS_PER_TOKEN,
    _LATIN_CHARS_PER_TOKEN,
)

# ── _is_cjk ──────────────────────────────────────────────────────────────────

def test_is_cjk_chinese():
    assert _is_cjk("中") is True
    assert _is_cjk("国") is True

def test_is_cjk_japanese():
    assert _is_cjk("あ") is True   # Hiragana
    assert _is_cjk("カ") is True   # Katakana

def test_is_cjk_korean():
    assert _is_cjk("한") is True   # Hangul

def test_is_cjk_punctuation():
    assert _is_cjk("。") is True   # CJK period
    assert _is_cjk("「") is True   # CJK bracket

def test_is_cjk_latin():
    assert _is_cjk("a") is False
    assert _is_cjk("Z") is False
    assert _is_cjk(".") is False


# ── estimate_tokens ──────────────────────────────────────────────────────────

def test_estimate_tokens_latin():
    """Pure Latin text: 400 chars / 4.0 = 100 tokens."""
    text = "a" * 400
    assert estimate_tokens(text) == 100

def test_estimate_tokens_cjk():
    """Pure CJK text: 150 chars / 1.5 = 100 tokens."""
    text = "中" * 150
    assert estimate_tokens(text) == 100

def test_estimate_tokens_mixed():
    """Mixed CJK + Latin: 100 CJK (66.7 tok) + 200 Latin (50 tok) = 116 tokens."""
    text = "中" * 100 + "a" * 200
    expected = int(100 / _CJK_CHARS_PER_TOKEN + 200 / _LATIN_CHARS_PER_TOKEN)
    assert estimate_tokens(text) == expected

def test_estimate_tokens_minimum_is_one():
    """A single Latin character must return at least 1 token."""
    assert estimate_tokens("x") == 1

def test_estimate_tokens_single_cjk():
    """A single CJK character must return at least 1 token."""
    assert estimate_tokens("中") == 1

def test_estimate_tokens_empty_returns_zero():
    """Empty string returns 0 tokens (no content)."""
    assert estimate_tokens("") == 0

def test_estimate_tokens_cjk_vs_latin_comparison():
    """CJK text should estimate MORE tokens than same-length Latin text."""
    text_cjk = "中" * 100
    text_latin = "a" * 100
    assert estimate_tokens(text_cjk) > estimate_tokens(text_latin)

def test_estimate_tokens_cjk_3000_chars():
    """3000 CJK chars should estimate ~2000 tokens (not ~857 like the old bug)."""
    text = "中" * 3000
    tokens = estimate_tokens(text)
    assert tokens == 2000  # 3000 / 1.5 = 2000
    # Old bug: 3000 / 3.5 = 857 — catastrophically underestimated


# ── split_chapter — edge cases ───────────────────────────────────────────────

def test_split_empty_text_returns_empty_list():
    assert split_chapter("", 100) == []

def test_split_whitespace_only_returns_empty_list():
    assert split_chapter("   \n\n\t  ", 100) == []

def test_split_short_chapter_returns_single_chunk():
    text = "Hello world. This is a short chapter."
    result = split_chapter(text, 1000)
    assert result == [text]


# ── split_chapter — CJK awareness ───────────────────────────────────────────

def test_split_cjk_chapter_uses_smaller_chunks():
    """CJK text should be split into smaller character windows."""
    # 300 CJK chars = 200 tokens at 1.5 c/t
    cjk_text = "中" * 300
    # Budget of 100 tokens → max_chars = 100 * 1.5 = 150 chars
    result = split_chapter(cjk_text, 100)
    assert len(result) == 2  # 300 chars / 150 max = 2 chunks

def test_split_latin_chapter_uses_larger_chunks():
    """Latin text should use the full 4.0 chars-per-token ratio."""
    latin_text = "a" * 400
    # Budget of 100 tokens → max_chars = 100 * 4.0 = 400 chars
    result = split_chapter(latin_text, 100)
    assert len(result) == 1  # fits in one chunk


# ── split_chapter — paragraph break (priority 1) ────────────────────────────

def test_split_prefers_paragraph_break():
    # Each paragraph ~50 Latin chars ≈ 12.5 tokens
    paragraph_a = "A" * 50
    paragraph_b = "B" * 50
    text = paragraph_a + "\n\n" + paragraph_b
    # Budget: 15 tokens → max_chars = 60, fits para_a but not both
    result = split_chapter(text, 15)
    assert len(result) == 2
    assert paragraph_a in result[0]
    assert paragraph_b in result[1]


# ── split_chapter — sentence-end (priority 2) ───────────────────────────────

def test_split_on_latin_sentence_end():
    sentence_a = "This is sentence one."
    padding = "x" * 40
    sentence_b = "This is sentence two."
    text = sentence_a + " " + padding + " " + sentence_b
    max_tokens = int((len(sentence_a) + 1 + len(padding) + 3) / _LATIN_CHARS_PER_TOKEN)
    result = split_chapter(text, max_tokens)
    assert len(result) >= 2
    assert result[0][-1] in ".!?。！？…"

def test_split_on_cjk_sentence_end():
    cjk_sent_a = "这是第一句话。"
    filler = "甲" * 60
    cjk_sent_b = "这是第二句话。"
    text = cjk_sent_a + filler + cjk_sent_b
    # CJK: budget in tokens → max_chars uses 1.5 c/t
    max_tokens = int((len(cjk_sent_a) + len(filler) + 2) / _CJK_CHARS_PER_TOKEN)
    result = split_chapter(text, max_tokens)
    assert len(result) >= 2
    assert result[0][-1] in "。！？…"


# ── split_chapter — whitespace and hard fallbacks ────────────────────────────

def test_split_on_whitespace_when_no_sentence_end():
    words = ["longword" + str(i) for i in range(30)]
    text = " ".join(words)
    max_tokens = 10
    result = split_chapter(text, max_tokens)
    assert len(result) > 1
    for chunk in result:
        assert chunk == chunk.strip()

def test_hard_split_when_no_whitespace():
    text = "a" * 1000
    max_tokens = 50
    result = split_chapter(text, max_tokens)
    assert len(result) > 1
    max_chars = int(max_tokens * _LATIN_CHARS_PER_TOKEN)
    for chunk in result:
        assert len(chunk) <= max_chars + 1


# ── Invariants ───────────────────────────────────────────────────────────────

def test_no_empty_chunks_produced():
    text = "\n\n".join(["chunk " + str(i) for i in range(20)])
    result = split_chapter(text, 5)
    assert result
    assert all(c for c in result)

def test_all_content_preserved():
    import re
    text = "Hello world. This is a test. " * 10
    result = split_chapter(text, 5)
    combined = "".join(result)
    orig_words = re.sub(r"\s+", "", text)
    chunk_words = re.sub(r"\s+", "", combined)
    assert orig_words == chunk_words

def test_single_very_long_word_still_produces_chunks():
    text = "a" * 500
    result = split_chapter(text, 10)
    assert len(result) > 1
    assert all(c for c in result)
