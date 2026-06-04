"""C1 token-metering primitives (DEFERRED-052) — the in-branch mirror of the
platform token convention (provider-registry billing/estimate.go).

Proves: the script-aware char→token estimate matches the platform formula (CJK
divisor 1.0 / Latin 3.5, ceil), TokenUsage arithmetic, and the sequential
UsageMeter delta the runner reconciles against.
"""

from __future__ import annotations

import math

from app.jobs.tokens import (
    CJK_DIVISOR,
    LATIN_DIVISOR,
    NON_ASCII_SHARE_THRESHOLD,
    TokenUsage,
    UsageMeter,
    estimate_tokens,
)


# ── estimate_tokens — platform script-aware divisor ───────────────────────────

def test_estimate_tokens_empty_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_cjk_is_one_per_char():
    # 封神演义 place names tokenize ~1 token/char → ceil(chars / 1.0).
    text = "昆侖山玉虛宮"  # 6 CJK chars, non-ASCII share = 1.0 >= 0.2 → CJK divisor
    assert estimate_tokens(text) == math.ceil(len(text) / CJK_DIVISOR) == 6


def test_estimate_tokens_latin_is_under_four_chars_per_token():
    text = "the quick brown fox"  # all ASCII → Latin divisor 3.5
    assert estimate_tokens(text) == math.ceil(len(text) / LATIN_DIVISOR)


def test_estimate_tokens_mixed_above_threshold_uses_cjk():
    # A short label + CJK name: non-ASCII share crosses the 0.2 threshold → CJK.
    text = "X 昆侖山"  # 5 chars, 3 non-ASCII → share 0.6 >= 0.2 → CJK divisor
    non_ascii = sum(1 for c in text if ord(c) > 127)
    assert non_ascii / len(text) >= NON_ASCII_SHARE_THRESHOLD
    assert estimate_tokens(text) == math.ceil(len(text) / CJK_DIVISOR)


def test_estimate_tokens_mostly_latin_below_threshold_uses_latin():
    text = "abcdefghij昆"  # 11 chars, 1 non-ASCII → share ~0.09 < 0.2 → Latin
    assert estimate_tokens(text) == math.ceil(len(text) / LATIN_DIVISOR)


# ── TokenUsage arithmetic ─────────────────────────────────────────────────────

def test_token_usage_total_and_add():
    a = TokenUsage(input_tokens=10, output_tokens=20)
    assert a.total == 30
    b = TokenUsage(input_tokens=1, output_tokens=2)
    summed = a + b
    assert summed == TokenUsage(input_tokens=11, output_tokens=22)
    assert summed.total == 33


def test_token_usage_defaults_zero():
    z = TokenUsage()
    assert z.input_tokens == 0 and z.output_tokens == 0 and z.total == 0


# ── UsageMeter — sequential per-gap delta the runner reconciles ───────────────

def test_usage_meter_accumulates():
    m = UsageMeter()
    assert m.total_tokens == 0
    m.add(TokenUsage(input_tokens=5, output_tokens=7))
    m.add(TokenUsage(input_tokens=1, output_tokens=2))
    assert m.total_tokens == 15
    assert m.usage == TokenUsage(input_tokens=6, output_tokens=9)


def test_usage_meter_delta_is_per_gap_spend():
    """The runner snapshots total before a gap and reads it after; the delta is
    that gap's real spend (sequential-run invariant)."""
    m = UsageMeter()
    m.add(TokenUsage(input_tokens=100, output_tokens=200))  # gap 1
    before = m.total_tokens
    m.add(TokenUsage(input_tokens=10, output_tokens=40))     # gap 2's seam calls
    gap2_spend = m.total_tokens - before
    assert gap2_spend == 50
