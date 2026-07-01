"""Wave A4 — provider-agnostic compaction (micro → full → fail)."""
from __future__ import annotations

from app.services.compaction import compact_messages, _PLACEHOLDER


def _big(n: int) -> str:
    return "word " * n  # ~ n*1.25 tokens (ASCII)


def _tool(name: str, size: int = 400) -> dict:
    return {"role": "tool", "name": name, "tool_call_id": f"c_{name}", "content": _big(size)}


class TestNoTrigger:
    def test_under_trigger_is_unchanged(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, rep = compact_messages(msgs, effective_limit=10_000)
        assert out is msgs
        assert rep.triggered is False

    def test_null_limit_is_noop(self):
        msgs = [_tool("web_search"), {"role": "user", "content": _big(9999)}]
        out, rep = compact_messages(msgs, effective_limit=None)
        assert rep.triggered is False


class TestMicrocompact:
    def test_evicts_old_tool_results_keeps_last_n(self):
        msgs = [
            {"role": "system", "content": "sys"},
            _tool("a"), _tool("b"), _tool("c"), _tool("d"), _tool("e"),
            {"role": "user", "content": "now"},
        ]
        out, rep = compact_messages(msgs, effective_limit=1_000, keep_tool_results=2)
        assert rep.triggered and rep.tool_results_cleared == 3  # 5 tools - keep 2
        cleared = [m for m in out if m.get("role") == "tool" and m["content"] == _PLACEHOLDER]
        assert len(cleared) == 3
        # the last two tool results are kept verbatim
        kept = [m for m in out if m.get("role") == "tool" and m["content"] != _PLACEHOLDER]
        assert len(kept) == 2

    def test_never_evicts_excluded_tool(self):
        msgs = [
            _tool("web_search"), _tool("web_search"), _tool("web_search"),
            _tool("web_search"), {"role": "user", "content": "q"},
        ]
        out, rep = compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        # web_search is excluded → none cleared even though 4 > keep 1
        assert rep.tool_results_cleared == 0
        assert all(m["content"] != _PLACEHOLDER for m in out if m.get("role") == "tool")

    def test_does_not_mutate_caller_messages(self):
        msgs = [_tool("a"), _tool("b"), _tool("c"), _tool("d"), {"role": "user", "content": "x"}]
        original_first = msgs[0]["content"]
        compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        assert msgs[0]["content"] == original_first  # caller's list untouched


class TestFullCompactAndFailure:
    def test_summarize_used_when_micro_insufficient(self):
        # one huge non-tool turn micro-compact can't shrink → summarizer runs.
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = compact_messages(
            msgs, effective_limit=2_000, keep_recent=1,
            summarize=lambda _m: "compressed summary of the discussion",
        )
        assert rep.summarized is True
        assert any("<summary>" in (m.get("content") or "") for m in out)

    def test_summarize_failure_falls_through_to_truncate(self):
        # edge #2: a broken summarizer must NOT poison context — fall to hard-truncate.
        def bad_summarize(_m):
            raise RuntimeError("local model timed out")

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=bad_summarize,
        )
        assert rep.summarize_failed is True
        assert rep.summarized is False
        assert rep.turns_truncated > 0  # fell through to the deterministic backstop
        assert "hard_truncate" in rep.steps


class TestHardTruncateAndOverflow:
    def test_hard_truncate_keeps_pinned_and_recent(self):
        msgs = [{"role": "system", "content": "SYS"}] + [
            {"role": "user", "content": _big(2000)} for _ in range(6)
        ] + [{"role": "user", "content": "LAST"}]
        out, rep = compact_messages(msgs, effective_limit=1_500, keep_recent=2)
        assert out[0]["content"] == "SYS"           # pinned kept, leads the prompt
        assert out[-1]["content"] == "LAST"          # recent tail kept
        assert rep.turns_truncated > 0

    def test_overflow_when_pinned_alone_exceed_budget(self):
        # edge #4: non-evictable system messages alone blow the budget.
        msgs = [
            {"role": "system", "content": _big(5000)},
            {"role": "user", "content": "x"},
        ]
        out, rep = compact_messages(msgs, effective_limit=1_000, keep_recent=1)
        assert rep.overflowed is True
