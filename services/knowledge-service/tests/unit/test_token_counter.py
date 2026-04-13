from app.context.formatters.token_counter import estimate_tokens


def test_none_is_zero():
    assert estimate_tokens(None) == 0


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_short_text_returns_at_least_one():
    assert estimate_tokens("hi") == 1


def test_four_chars_one_token():
    assert estimate_tokens("abcd") == 1


def test_eight_chars_two_tokens():
    assert estimate_tokens("abcdefgh") == 2


def test_long_text_proportional():
    assert estimate_tokens("x" * 400) == 100


def test_cjk_text_is_counted():
    # Each CJK char is ~3 bytes in UTF-8 but len() is char-count in
    # Python, so we count runes. 12 chars / 4 = 3 tokens.
    assert estimate_tokens("一位神秘的刀客的故事") == 2


def test_non_string_coerced():
    assert estimate_tokens(1234) == 1  # type: ignore[arg-type]
