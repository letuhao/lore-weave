"""Kernel token-estimator tests (T3.3a) — script-aware, not 4-8x wrong on CJK/VN."""
from loreweave_context import (
    estimate_messages_tokens,
    estimate_tokens,
    split_to_token_budget,
)


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


# ── split_to_token_budget (C1) ────────────────────────────────────────────────


def test_split_edge_cases():
    assert split_to_token_budget("", 100) == []
    assert split_to_token_budget(None, 100) == []
    # non-positive budget → whole text as one slice, never an infinite loop / dropped text
    assert split_to_token_budget("abc", 0) == ["abc"]


def test_split_reassembles_losslessly_and_respects_budget():
    for text in ("x" * 5000, "万" * 5000, "ự" * 5000, "hello 世界 " * 400):
        pieces = split_to_token_budget(text, 200)
        assert "".join(pieces) == text, "no character may be dropped or reordered"
        # every slice is within budget, except a slice may be a single char whose own factor
        # already exceeds the budget (impossible here — budget 200 ≫ any single-char factor).
        assert all(estimate_tokens(p) <= 200 for p in pieces)


def test_split_lone_char_over_budget_is_emitted_not_dropped():
    # The one documented over-budget exception: a char whose OWN factor already exceeds a tiny
    # budget must still be emitted as its own slice (never dropped). CJK factor 1.05 > budget 1.
    pieces = split_to_token_budget("万" * 3, 1)
    assert pieces == ["万", "万", "万"]
    assert "".join(pieces) == "万" * 3
    assert all(estimate_tokens(p) <= 1 for p in pieces)  # round(1.05)=1, so still ≤ budget


def test_split_is_script_aware_cjk_cut_shorter_than_latin():
    # The DBT-12 fix: for the SAME token budget, a CJK string is cut into MORE (shorter) slices
    # than a Latin string of the same char count — because CJK ≈ 1 tok/char, Latin ≈ 0.25.
    budget = 500
    latin_pieces = split_to_token_budget("a" * 8000, budget)
    cjk_pieces = split_to_token_budget("万" * 8000, budget)
    assert len(cjk_pieces) > len(latin_pieces)
