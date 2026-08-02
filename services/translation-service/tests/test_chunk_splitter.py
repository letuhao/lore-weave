"""
Unit tests for chunk_splitter — S11 kernel-aligned token estimation.

Several assertions here used to RESTATE the module's own constants (`== 100` for 150 CJK
chars, `expected = 100/1.5 + 200/4.0`, `== 2` chunks). A test that recomputes the code's
arithmetic cannot notice when that arithmetic is wrong, and it did not: measured against
tiktoken `o200k_base` the estimator under-counted CJK by 33%. They now assert BANDS against
the measurement, and `split_chapter` is asserted on the property it promises — no chunk over
its budget — rather than on a chunk count derived from the constant under test.

Covers:
- estimate_tokens: the kernel's script-aware estimator, vs tiktoken as ground truth
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

def test_estimate_tokens_cjk_does_not_UNDER_count_the_real_tokenizer():
    """S11. This asserted `== 100` for 150 CJK chars, restating the old 1.5 chars/token
    constant. Measured against tiktoken `o200k_base`, 150 CJK chars really cost **150**
    tokens — so the assertion pinned a 33% UNDER-count, and under-counting is the direction
    that overflows a context window.

    Now asserted as a BAND against the measurement rather than as a restatement of whatever
    constant the implementation happens to use, because a test that recomputes the code's own
    arithmetic cannot fail when that arithmetic is wrong.
    """
    text = "中" * 150
    got = estimate_tokens(text)
    assert got >= 150, f"under-counts the real tokenizer ({got} < 150) — the old bug"
    assert got <= 180, f"over-counts enough to waste a third of the window ({got})"

def test_estimate_tokens_mixed_scripts_stay_above_the_measurement():
    """Same rewrite, mixed script. The old version computed `expected` from the module's own
    constants — it would have passed for ANY value those constants produced."""
    text = "中" * 100 + "a" * 200
    got = estimate_tokens(text)
    # tiktoken measures this fixture at 125; 200 identical Latin chars compress far better
    # than prose does, so the over-count here is an artefact of a degenerate fixture and the
    # floor is what matters.
    assert got >= 125, f"under-counts the real tokenizer ({got} < 125)"

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

def test_estimate_tokens_cjk_3000_chars_reaches_the_REAL_token_count():
    """The history of this one assertion is the whole S11 slice.

    v1 divided everything by 3.5 → 857 tokens for 3000 CJK chars, "catastrophically
    underestimated" in its own words. v2 fixed it to 1.5 chars/token → 2000, and this test
    was written to pin 2000 as correct. Measured against tiktoken `o200k_base`, 3000 CJK
    chars really cost **3000** tokens — so v2 closed two thirds of the gap and the test
    froze the remaining third as though it were the answer.

    A chunk this splitter believed was 2000 tokens reached the model at 3000. That is the
    same context-window overflow the v2 fix was written for, and it survived because the test
    restated the fix's constant instead of measuring against the tokenizer.
    """
    text = "中" * 3000
    tokens = estimate_tokens(text)
    assert tokens >= 3000, f"still under-counts the real 3000 tokens ({tokens})"
    assert tokens <= 3600, f"over-counts by more than 20% ({tokens})"


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

def test_split_cjk_chapter_keeps_every_chunk_INSIDE_the_token_budget():
    """This asserted `== 2` chunks: 300 CJK chars cut at 150 chars each, because the splitter
    sized windows with `_CJK_CHARS_PER_TOKEN = 1.5`.

    Those chunks are ~150 REAL tokens against a 100-token budget — 50% over — and the test
    froze that as the expected shape. It is the same class as the estimator tests above: an
    assertion that restates the implementation's constant cannot notice the constant is wrong.

    The property that actually matters is the one the module promises, so that is what is
    asserted now: no chunk exceeds the budget it was given. The chunk COUNT is an output of
    that promise, not the promise itself.
    """
    cjk_text = "中" * 300
    result = split_chapter(cjk_text, 100)
    assert result, "the splitter returned nothing"
    assert "".join(result) == cjk_text, "characters were lost or duplicated"
    for i, chunk in enumerate(result):
        assert estimate_tokens(chunk) <= 100, (
            f"chunk {i} is {estimate_tokens(chunk)} tokens against a 100-token budget"
        )


def test_a_LATIN_chapter_is_not_over_split_by_the_same_rule():
    """The control. The assertion above is satisfiable by a splitter that cuts everything into
    single characters, so pin that Latin text — which genuinely fits more chars per token —
    still gets the larger window."""
    latin = "a" * 300
    cjk = "中" * 300
    assert len(split_chapter(latin, 100)) < len(split_chapter(cjk, 100))

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


# ── S11: this module must not grow a FIFTH token convention ──────────────────────────────

def test_the_estimator_IS_the_kernels_not_a_local_copy():
    """The repo had FOUR `estimate_tokens` implementations. This one is now the kernel's.

    Asserted by EFFECT — identical output across scripts — rather than by inspecting the
    import, because a future edit that re-inlines the arithmetic would keep the import and
    still diverge. Vietnamese is in the set deliberately: it is the script this module had no
    class for at all, in the service that translates Vietnamese novels.
    """
    from loreweave_context import estimate_tokens as kernel

    for s in ("The sword left its sheath and the moonlight caught the steel.",
              "Lạc Viên rút kiếm khỏi vỏ, ánh thép loé lên dưới trăng.",
              "剑落下，庭院像往常一样安静了下来。",
              "中" * 150,
              ""):
        assert estimate_tokens(s) == kernel(s), f"diverged from the kernel on {s[:24]!r}"


def test_vietnamese_is_no_longer_counted_at_the_LATIN_ratio():
    """The structural half of the bug. This module classified characters as CJK or "other",
    so Vietnamese — whose diacritics tokenize far denser than English — fell through to the
    Latin ratio of 4.0 chars/token.

    The control is English: if the two came back equal per character, the Vietnamese class
    would not be doing anything and this test would be pinning a coincidence.
    """
    vi = "Lạc Viên rút kiếm khỏi vỏ, ánh thép loé lên dưới trăng đêm nay"
    en = "The sword left its sheath and moonlight caught the steel tonight"
    vi_per_char = estimate_tokens(vi) / len(vi)
    en_per_char = estimate_tokens(en) / len(en)
    assert vi_per_char > en_per_char, (
        f"Vietnamese ({vi_per_char:.3f} tok/char) is still counted no denser than English "
        f"({en_per_char:.3f}) — the missing script class is back"
    )
