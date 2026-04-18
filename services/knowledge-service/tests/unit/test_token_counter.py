"""D-T2-01 — tiktoken-backed estimate_tokens tests.

The module now delegates to tiktoken's cl100k_base encoding (with a
`len/4` fallback only when tiktoken can't be imported). Tests target
observable behavior — defensives, non-zero for non-empty input, CJK
now counted proportionally to bytes rather than at 0.25 tokens/char.
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


def test_cjk_counted_at_least_one_per_char():
    # A crude lower bound that catches regressions toward the old
    # heuristic without locking in tiktoken's exact BPE output.
    text = "中文测试句子"  # 6 CJK chars
    assert estimate_tokens(text) >= len(text)


def test_monotonic_with_length():
    # Longer English text produces more-or-equal tokens than shorter.
    short = estimate_tokens("The quick brown fox.")
    longer = estimate_tokens("The quick brown fox jumps over the lazy dog.")
    assert longer >= short
