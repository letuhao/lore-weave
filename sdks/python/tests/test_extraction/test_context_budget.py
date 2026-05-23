"""Tests for the ContextBudget calculator + token estimators."""

from __future__ import annotations

import pytest

from loreweave_extraction.context_budget import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL_CONTEXT,
    ContextBudget,
    estimate_paragraph_count,
    estimate_text_tokens,
)


# ── estimate_text_tokens ────────────────────────────────────────────


def test_estimate_text_tokens_empty():
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens(None) == 0  # type: ignore[arg-type]


def test_estimate_text_tokens_english_short():
    # 40-char string ≈ 10 tokens at 4 chars/token
    text = "Alice followed the rabbit down the hole. "
    assert 8 <= estimate_text_tokens(text, "en") <= 14


def test_estimate_text_tokens_chinese_pack_more_tokens_per_char():
    """Same character count, but CJK density triggers higher token estimate."""
    en = estimate_text_tokens("Alice met the white rabbit and they talked." * 5, "en")
    zh = estimate_text_tokens("爱丽丝遇见了白兔他们交谈了很久关于花园里的事情" * 5, "zh")
    # Chinese roughly the same length should produce ~5× more tokens
    assert zh > en * 3


def test_estimate_text_tokens_autodetects_cjk():
    """Auto-detect: a mostly-Chinese string returns the CJK token count
    even when caller passes no lang."""
    zh_text = "天命之子穿越异界发现了千年古城里的秘密。" * 10
    assert estimate_text_tokens(zh_text) > len(zh_text) / 2


# ── estimate_paragraph_count ────────────────────────────────────────


def test_estimate_paragraph_count_empty():
    assert estimate_paragraph_count("") == 0
    assert estimate_paragraph_count("   ") == 0


def test_estimate_paragraph_count_simple():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    assert estimate_paragraph_count(text) == 3


def test_estimate_paragraph_count_skips_blank():
    """Trailing blank line shouldn't count as an extra paragraph."""
    text = "First.\n\nSecond.\n\n\n"
    assert estimate_paragraph_count(text) == 2


# ── ContextBudget construction ──────────────────────────────────────


def test_budget_rejects_zero_context():
    with pytest.raises(ValueError, match="model_context must be > 0"):
        ContextBudget(model_context=0)


def test_budget_rejects_negative_max_output():
    with pytest.raises(ValueError, match="max_output_tokens must be > 0"):
        ContextBudget(model_context=8192, max_output_tokens=0)


def test_budget_rejects_safety_margin_one():
    with pytest.raises(ValueError, match="safety_margin_pct must be in"):
        ContextBudget(model_context=8192, safety_margin_pct=1.0)


def test_budget_defaults():
    """Default ContextBudget uses 15% safety + 4096 max_output."""
    b = ContextBudget(model_context=32_000)
    assert b.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
    assert b.safety_margin_pct == 0.15
    assert b.safety_margin == int(32_000 * 0.15)


# ── input_budget_for ────────────────────────────────────────────────


def test_input_budget_subtracts_system_max_safety():
    """input_budget = model_context − system_prompt − max_output − safety."""
    b = ContextBudget(model_context=10_000, max_output_tokens=1024)
    # safety = 10000 * 0.15 = 1500
    # input = 10000 - 2000 (sys) - 1024 (max) - 1500 (safety) = 5476
    assert b.input_budget_for(2000) == 5476


def test_input_budget_floors_at_zero_when_overcommitted():
    """When system+max+safety > context → return 0, not negative."""
    b = ContextBudget(model_context=4000, max_output_tokens=4000)
    # safety = 600; system 2000; max 4000 → 6600 used, 4000 budget → 0
    assert b.input_budget_for(2000) == 0


# ── max_paragraphs_per_chunk ────────────────────────────────────────


def test_max_paragraphs_english_32k_model():
    """32K context + 2K system + 4K output + 4.8K safety = ~21K input
    English ≈ 110 tok/para → ~191 paragraphs per chunk."""
    b = ContextBudget(model_context=32_000)
    n = b.max_paragraphs_per_chunk(system_prompt_tokens=2000, lang="en")
    assert 150 <= n <= 220


def test_max_paragraphs_chinese_smaller_than_english():
    """Same budget, denser Chinese → fewer paragraphs per chunk."""
    b = ContextBudget(model_context=32_000)
    en = b.max_paragraphs_per_chunk(2000, "en")
    zh = b.max_paragraphs_per_chunk(2000, "zh")
    assert zh < en, "Chinese should chunk smaller than English at same budget"


def test_max_paragraphs_floors_at_one():
    """Even when budget is microscopic, never return 0 (chunk_size=0
    is meaningless — chunker would emit no chunks)."""
    b = ContextBudget(model_context=4500, max_output_tokens=4000)
    # input_budget == 0 → still 1
    assert b.max_paragraphs_per_chunk(2000, "en") == 1


def test_max_paragraphs_tight_context_local_model():
    """24K context (typical local 35B): English ≈ 13K input / 110 ≈ 119
    paragraphs. Generous but not unbounded."""
    b = ContextBudget(model_context=24_000)
    n = b.max_paragraphs_per_chunk(2000, "en")
    assert 100 <= n <= 150


# ── max_parallel_slots ──────────────────────────────────────────────


def test_max_parallel_slots_capped_at_3():
    """Even a 200K cloud-model context caps at 3 (orchestrator only
    needs 3-way R/E/F gather)."""
    b = ContextBudget(model_context=200_000)
    assert b.max_parallel_slots() == 3


def test_max_parallel_slots_24k_local_model_fits_2():
    """24K context + 4K max_output + 3K input + 1K KV overhead = 8120/slot
    → 24000/8120 = 2 slots (integer division, conservative)."""
    b = ContextBudget(model_context=24_000)
    assert b.max_parallel_slots() == 2


def test_max_parallel_slots_32k_local_model_fits_3():
    """32K context loaded → 3 slots fit comfortably (cap)."""
    b = ContextBudget(model_context=32_000)
    assert b.max_parallel_slots() == 3


def test_max_parallel_slots_tight_context_floors_at_1():
    """Tiny model_context → always at least 1 (sequential extraction)."""
    b = ContextBudget(model_context=4_000)
    assert b.max_parallel_slots() == 1


# ── fits_input predicate ────────────────────────────────────────────


def test_fits_input_true_when_under_budget():
    b = ContextBudget(model_context=10_000)
    # input_budget_for(2000) computed: 10000-2000-4096-1500=2404
    assert b.fits_input(input_tokens=2000, system_prompt_tokens=2000)


def test_fits_input_false_when_over_budget():
    b = ContextBudget(model_context=10_000)
    assert not b.fits_input(input_tokens=5000, system_prompt_tokens=2000)


def test_fits_input_uses_zero_system_prompt_by_default():
    b = ContextBudget(model_context=10_000)
    # 10000-0-4096-1500=4404 budget → 4000 fits
    assert b.fits_input(input_tokens=4000)
