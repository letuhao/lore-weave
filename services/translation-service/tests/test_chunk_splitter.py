"""
Unit tests for chunk_splitter — Plan §9 (Verification).

Covers:
- estimate_tokens: basic math
- split_chapter: empty text, short text (1 chunk), paragraph-break split,
  Latin sentence-end split, CJK sentence-end split,
  whitespace fallback, hard-split fallback
- Invariants: no empty chunks, every chunk within max_chars tolerance
"""
import pytest

from app.workers.chunk_splitter import (
    TOKEN_CHAR_RATIO,
    estimate_tokens,
    split_chapter,
)

# ── estimate_tokens ────────────────────────────────────────────────────────────

def test_estimate_tokens_basic():
    """estimate_tokens = max(1, len(text) / TOKEN_CHAR_RATIO)."""
    text = "a" * 350   # 350 / 3.5 = 100 tokens
    assert estimate_tokens(text) == 100


def test_estimate_tokens_minimum_is_one():
    """Even a single character must return at least 1 token."""
    assert estimate_tokens("x") == 1


def test_estimate_tokens_empty_returns_one():
    """Empty string: max(1, 0) = 1 — avoids divide-by-zero downstream."""
    assert estimate_tokens("") == 1


# ── split_chapter — edge cases ─────────────────────────────────────────────────

def test_split_empty_text_returns_empty_list():
    """Empty input → empty list (no empty-string chunks)."""
    assert split_chapter("", 100) == []


def test_split_whitespace_only_returns_empty_list():
    """Whitespace-only input strips to nothing → empty list."""
    assert split_chapter("   \n\n\t  ", 100) == []


def test_split_short_chapter_returns_single_chunk():
    """Text that fits in one chunk must be returned as-is."""
    text = "Hello world. This is a short chapter."
    result = split_chapter(text, 1000)
    assert result == [text]


def test_split_text_exactly_at_limit_returns_single_chunk():
    """Text whose char length == max_chars should not be split."""
    max_tokens = 10
    max_chars = int(max_tokens * TOKEN_CHAR_RATIO)      # 35 chars
    text = "a" * max_chars
    result = split_chapter(text, max_tokens)
    assert len(result) == 1
    assert result[0] == text


# ── split_chapter — paragraph break (priority 1) ──────────────────────────────

def test_split_prefers_paragraph_break():
    """Paragraph break (\\n\\n) must be the highest-priority split point."""
    chunk_tokens = 20
    chunk_chars = int(chunk_tokens * TOKEN_CHAR_RATIO)  # 70 chars

    paragraph_a = "A" * (chunk_chars - 5)               # fits in one chunk
    paragraph_b = "B" * (chunk_chars - 5)               # would overflow combined
    text = paragraph_a + "\n\n" + paragraph_b

    result = split_chapter(text, chunk_tokens)
    assert len(result) == 2
    assert paragraph_a in result[0]
    assert paragraph_b in result[1]


def test_split_paragraph_break_with_spaces_around_newlines():
    """Paragraph break with trailing spaces (\\n   \\n) is still detected."""
    para_a = "X" * 60
    para_b = "Y" * 60
    text = para_a + "\n   \n" + para_b

    # max tokens = enough for one paragraph + overhead but not both
    max_tokens = int(len(para_a + "\n   \n") / TOKEN_CHAR_RATIO) + 2
    result = split_chapter(text, max_tokens)
    assert len(result) == 2


# ── split_chapter — sentence-end (priority 2) ─────────────────────────────────

def test_split_on_latin_sentence_end():
    """Falls back to last '.', '!', or '?' when no paragraph break is available."""
    # One big blob, no paragraph breaks — has sentence ends
    sentence_a = "This is sentence one."        # ends with '.'
    padding = "x" * 40                          # make it overflow
    sentence_b = "This is sentence two."
    text = sentence_a + " " + padding + " " + sentence_b

    # max_tokens just barely covers sentence_a + padding
    max_tokens = int((len(sentence_a) + 1 + len(padding) + 3) / TOKEN_CHAR_RATIO)
    result = split_chapter(text, max_tokens)
    assert len(result) >= 2
    # First chunk must end at a sentence boundary
    assert result[0][-1] in ".!?。！？…", f"Bad split boundary: {result[0][-3:]!r}"


def test_split_on_cjk_sentence_end():
    """CJK period (。) and exclamation (！) are valid sentence split points."""
    cjk_sent_a = "这是第一句话。"
    filler = "甲" * 60
    cjk_sent_b = "这是第二句话。"
    text = cjk_sent_a + filler + cjk_sent_b

    # max_tokens fits cjk_sent_a + filler but not everything
    max_tokens = int((len(cjk_sent_a) + len(filler) + 2) / TOKEN_CHAR_RATIO)
    result = split_chapter(text, max_tokens)
    assert len(result) >= 2
    assert result[0][-1] in "。！？…", f"CJK split boundary not found: {result[0][-3:]!r}"


# ── split_chapter — whitespace fallback (priority 3) ──────────────────────────

def test_split_on_whitespace_when_no_sentence_end():
    """When no sentence-end char exists within the window, split at last space."""
    # Long word-like tokens separated only by spaces, no punctuation
    words = ["longword" + str(i) for i in range(30)]
    text = " ".join(words)   # contains spaces but no sentence-end chars

    max_tokens = 10   # 35 chars — forces splitting
    result = split_chapter(text, max_tokens)
    assert len(result) > 1
    # All chunks should not start or end with spaces
    for chunk in result:
        assert chunk == chunk.strip()


# ── split_chapter — hard cut fallback (priority 4) ────────────────────────────

def test_hard_split_when_no_whitespace_or_sentence_end():
    """Continuous string with no whitespace or punctuation → hard cut at max_chars."""
    text = "a" * 1000
    max_tokens = 50   # 175 chars per chunk
    result = split_chapter(text, max_tokens)

    assert len(result) > 1
    max_chars = int(max_tokens * TOKEN_CHAR_RATIO)
    for chunk in result:
        # Hard split: chunks should be at most max_chars long (strip may trim by 0)
        assert len(chunk) <= max_chars + 1   # +1 tolerance for strip edge


# ── Invariants ─────────────────────────────────────────────────────────────────

def test_no_empty_chunks_produced():
    """split_chapter must never return empty strings."""
    text = "\n\n".join(["chunk " + str(i) for i in range(20)])
    result = split_chapter(text, 5)
    assert result  # at least one chunk
    assert all(c for c in result), "Empty chunk found"


def test_all_content_preserved():
    """Concatenating all chunks must reproduce all non-whitespace content."""
    import re
    text = "Hello world. This is a test. " * 10   # ~290 chars
    result = split_chapter(text, 5)
    combined = "".join(result)
    # Strip whitespace from both and compare character sets
    orig_words  = re.sub(r"\s+", "", text)
    chunk_words = re.sub(r"\s+", "", combined)
    assert orig_words == chunk_words


def test_multiple_chunks_each_within_limit():
    """Every chunk must stay within the estimated token budget (±1 token tolerance)."""
    text = "The quick brown fox jumps over the lazy dog. " * 20
    max_tokens = 15
    result = split_chapter(text, max_tokens)
    max_chars = int(max_tokens * TOKEN_CHAR_RATIO)
    for chunk in result:
        assert len(chunk) <= max_chars + 5   # small tolerance: sentence splits may be slightly over


def test_single_very_long_word_still_produces_chunks():
    """Even a single word longer than max_chars must be emitted as a chunk (hard cut)."""
    text = "a" * 500
    result = split_chapter(text, 10)   # 10 * 3.5 = 35 chars per chunk
    assert len(result) > 1
    assert all(c for c in result)
