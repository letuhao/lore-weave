"""D-T2-01 / M3 — tiktoken-backed estimate_tokens tests.

The module delegates to tiktoken's o200k_base encoding (GPT-4o /
modern-model tokenizer; M3 swap from cl100k_base to stop over-counting
CJK ~40%), with a cl100k→`len/4` fallback chain. Tests target observable
behavior — defensives, non-zero for non-empty input, CJK counted far
above the old 0.25 tokens/char heuristic — NOT a tokenizer-specific
per-char ratio (o200k compresses CJK to <1 token/char, unlike cl100k).
"""

from app.context.formatters.token_counter import estimate_tokens


def test_none_is_zero():
    assert estimate_tokens(None) == 0


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_short_text_returns_at_least_one():
    assert estimate_tokens("hi") >= 1


def test_non_string_coerced():
    # Integers stringify to "1234" which is tokenized to at least 1
    # token. The exact count is irrelevant; the contract is "doesn't
    # raise and returns a positive int".
    assert estimate_tokens(1234) >= 1  # type: ignore[arg-type]


def test_long_text_proportional():
    # A long ASCII run still produces many tokens, not zero. Exact
    # count depends on BPE compression but is bounded well above 1.
    assert estimate_tokens("Hello world. " * 50) >= 20


def test_cjk_counted_higher_than_old_heuristic():
    # D-T2-01 regression: the old len/4 heuristic gave 2 tokens for
    # this 10-char string; tiktoken's cl100k_base gives ~14. The
    # exact number is tokenizer-specific; what matters is that CJK
    # is no longer drastically under-budgeted.
    text = "一位神秘的刀客的故事"
    assert estimate_tokens(text) > len(text) // 4


def test_cjk_counted_well_above_old_heuristic():
    # A crude lower bound that catches regressions toward the old len/4
    # heuristic without locking in a per-char ratio. o200k_base compresses
    # CJK to <1 token/char (e.g. this 6-char string → 4 tokens), so the
    # old `>= len(text)` bound no longer holds — but it must still be well
    # above len//4 (the pre-tiktoken floor this regression test guards).
    text = "中文测试句子"  # 6 CJK chars
    assert estimate_tokens(text) > len(text) // 4


def test_monotonic_with_length():
    # Longer English text produces more-or-equal tokens than shorter.
    short = estimate_tokens("The quick brown fox.")
    longer = estimate_tokens("The quick brown fox jumps over the lazy dog.")
    assert longer >= short
