"""Wave A1/A2 — script-aware token estimate + context budget."""
from __future__ import annotations

from app.services.token_budget import (
    compute_budget,
    estimate_messages_tokens,
    estimate_tokens,
)


class TestScriptAwareEstimate:
    def test_english_is_roughly_chars_over_four(self):
        text = "the quick brown fox jumps over the lazy dog" * 4  # ~172 chars ASCII
        est = estimate_tokens(text)
        # ~chars/4 band (the classic English heuristic still holds for Latin).
        assert 0.2 * len(text) <= est <= 0.35 * len(text)

    def test_chinese_is_NOT_chars_over_four(self):
        # 万古神帝 — Chinese tokenizes ~1 token/char; chars/4 would 4x under-count.
        text = "万古神帝魔女逆天诸天神魔仙侠世界" * 5  # ~80 Han chars
        est = estimate_tokens(text)
        flat_chars_over_4 = len(text) // 4
        assert est >= 0.8 * len(text)          # ~1 token/char, not chars/4
        assert est > 3 * flat_chars_over_4     # decisively above the broken heuristic

    def test_vietnamese_denser_than_plain_english(self):
        # Vietnamese with diacritics tokenizes denser than the same-length English.
        vi = "Ma Nữ Nghịch Thiên — nàng tiểu thư bị phản bội, tái sinh với ma công nghịch thiên"
        en_same_len = "x" * len(vi)
        assert estimate_tokens(vi) > estimate_tokens(en_same_len)

    def test_empty_and_none(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_messages_include_overhead(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        assert estimate_messages_tokens(msgs) > 0
        # content-parts form (text blocks) is summed too.
        parts = [{"role": "user", "content": [{"type": "text", "text": "万古神帝"}]}]
        assert estimate_messages_tokens(parts) >= estimate_tokens("万古神帝")

    def test_assistant_tool_calls_args_are_counted(self):
        # a tool-call turn (content=None) carries its weight in the arguments JSON;
        # ignoring it under-counts the resume / tool-loop path.
        big_args = '{"selection": "' + ("x" * 2000) + '"}'
        with_call = [{
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "propose_edit", "arguments": big_args}}],
        }]
        empty = [{"role": "assistant", "content": None}]
        # the big arguments blob must dominate the estimate, not the +4 overhead.
        assert estimate_messages_tokens(with_call) > estimate_messages_tokens(empty) + 100


class TestComputeBudget:
    def test_pct_against_effective_limit(self):
        b = compute_budget(used_tokens=10_000, context_length=40_000, max_output_tokens=4_000)
        # effective = 40000 - 4000 - 512 = 35488; pct = 10000/35488 ≈ 0.2818
        assert b.effective_limit == 40_000 - 4_000 - 512
        assert 0.28 <= (b.pct or 0) <= 0.29
        assert b.to_event()["pct"] is not None

    def test_null_context_length_is_unknown(self):
        b = compute_budget(used_tokens=10_000, context_length=None, max_output_tokens=4_000)
        assert b.pct is None
        assert b.effective_limit is None
        assert b.to_event()["context_length"] is None

    def test_overflowed_pct_exceeds_one(self):
        b = compute_budget(used_tokens=40_000, context_length=40_000, max_output_tokens=4_000)
        assert (b.pct or 0) > 1.0  # over budget → meter goes red
