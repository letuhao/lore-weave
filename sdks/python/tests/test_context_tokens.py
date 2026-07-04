"""Kernel token-estimator tests (T3.3a) — script-aware, not 4-8x wrong on CJK/VN."""
from loreweave_context import estimate_messages_tokens, estimate_tokens


def test_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_messages_tokens([]) == 0
    assert estimate_messages_tokens(None) == 0


def test_cjk_and_vietnamese_denser_than_latin():
    # 10 chars each, but CJK ≈ 1 tok/char, VN denser than plain ASCII.
    ascii_t = estimate_tokens("a" * 40)
    vn_t = estimate_tokens("ự" * 40)      # VN precomposed vowel
    cjk_t = estimate_tokens("万" * 40)     # Han
    assert cjk_t > vn_t > ascii_t
    assert cjk_t >= 40                     # ~1 tok/glyph
    assert ascii_t <= 12                   # ~chars/4


def test_messages_counts_content_toolcalls_and_overhead():
    msgs = [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"function": {"name": "memory_search", "arguments": '{"q":"Kai"}'}}]},
        {"role": "system", "content": [{"type": "text", "text": "block one"},
                                       {"type": "text", "text": "block two"}]},
    ]
    total = estimate_messages_tokens(msgs)
    # content + tool-call name/args + 4/message overhead, all counted (non-zero, bounded)
    assert total >= estimate_tokens("hello there") + 4 + 4 + 4
