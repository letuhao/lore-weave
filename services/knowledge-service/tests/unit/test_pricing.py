"""T2-close-5 — unit tests for `app.pricing.cost_per_token`."""
from __future__ import annotations

from decimal import Decimal

from app.pricing import cost_per_token


def test_exact_match_gpt_4o():
    assert cost_per_token("gpt-4o") == Decimal("0.000005")


def test_exact_match_claude_opus_4():
    assert cost_per_token("claude-opus-4") == Decimal("0.000030")


def test_prefix_match_versioned_gpt_4o():
    """Versioned model names like `gpt-4o-2024-08-06` must resolve
    to the base `gpt-4o` rate — otherwise every provider's version
    bumps would silently fall through to the legacy default."""
    assert cost_per_token("gpt-4o-2024-08-06") == Decimal("0.000005")


def test_prefix_match_versioned_claude_sonnet():
    """`claude-sonnet-4-5-20250929` → `claude-sonnet-4` rate, not
    `claude-3-5-sonnet` (accidental substring hit) — tests that the
    prefix match is startswith, not contains."""
    assert cost_per_token("claude-sonnet-4-5-20250929") == Decimal("0.000006")


def test_longest_prefix_wins_over_shorter():
    """REVIEW-DESIGN nail — `gpt-4o-mini` is a longer prefix of
    `gpt-4o-mini-2024-07-18` than `gpt-4o`, so the mini rate wins.
    Without length-sorted iteration this test fails depending on
    dict insertion order."""
    assert cost_per_token("gpt-4o-mini-2024-07-18") == Decimal("0.00000030")
    assert cost_per_token("gpt-4o-mini") == Decimal("0.00000030")


def test_local_models_free():
    """Self-hosted models (Ollama / LM Studio) have zero marginal
    cost. Preview dialog should show $0 so users aren't falsely
    warned about hosted-model rates."""
    assert cost_per_token("bge-m3") == Decimal("0")
    assert cost_per_token("bge-small") == Decimal("0")
    assert cost_per_token("nomic-embed-text") == Decimal("0")
    assert cost_per_token("llama-3.3-70b") == Decimal("0")
    assert cost_per_token("qwen2.5-7b-instruct") == Decimal("0")
    assert cost_per_token("mistral-nemo") == Decimal("0")


def test_unknown_model_falls_back():
    """Unknown model → legacy ~$2/M default. Preview shows a
    non-zero "probably pay for this" estimate so the user knows
    to check their provider's real pricing."""
    assert cost_per_token("some-new-model-vendor-hasnt-priced") == Decimal("0.000002")
    assert cost_per_token("gibberish") == Decimal("0.000002")


def test_empty_string_falls_back():
    """Empty / None-ish inputs don't raise — preview is non-critical."""
    assert cost_per_token("") == Decimal("0.000002")


def test_embedding_models_have_distinct_rates():
    """text-embedding-3-small and -large are priced differently;
    ensure we don't collapse them to one rate."""
    small = cost_per_token("text-embedding-3-small")
    large = cost_per_token("text-embedding-3-large")
    assert small != large
    assert large > small  # large is more expensive


def test_openai_versioned_embedding_prefix():
    """`text-embedding-3-small-2024-02` (hypothetical versioned
    release) still resolves to the small rate via prefix match."""
    assert cost_per_token("text-embedding-3-small-2024") == Decimal("0.00000002")


def test_case_insensitive_match():
    """Review-impl: `llm_model` is a free-text Pydantic field so
    callers can send mixed-case. Normalize before matching so
    `"GPT-4o"` doesn't silently hit the fallback."""
    assert cost_per_token("GPT-4o") == Decimal("0.000005")
    assert cost_per_token("Claude-Sonnet-4") == Decimal("0.000006")
    assert cost_per_token("BGE-M3") == Decimal("0")


def test_whitespace_normalization():
    """Same reason as case normalization — leading/trailing
    whitespace from a sloppy caller shouldn't force the fallback."""
    assert cost_per_token("  gpt-4o  ") == Decimal("0.000005")
    assert cost_per_token("\tclaude-opus-4\n") == Decimal("0.000030")
    # Whitespace-only also hits fallback (not exact `"" in map`).
    assert cost_per_token("   ") == Decimal("0.000002")
