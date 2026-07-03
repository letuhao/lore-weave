"""Wave A4 — provider-agnostic compaction (micro → full → fail)."""
from __future__ import annotations

import pytest

from app.services.compaction import (
    COMPACT_TRIGGER_RATIO,
    CompactionReport,
    compact_messages,
    _PLACEHOLDER,
)

pytestmark = pytest.mark.asyncio


class TestW1ReportSurface:
    async def test_trigger_ratio_named_constant_is_the_default(self):
        # W1 — until_compact_pct reuses THIS constant; the default trigger must
        # be the same number (no duplicated 0.75 anywhere).
        import inspect

        sig = inspect.signature(compact_messages)
        assert sig.parameters["trigger_ratio"].default == COMPACT_TRIGGER_RATIO == 0.75

    async def test_did_work_false_when_nothing_changed(self):
        assert CompactionReport().did_work is False
        assert CompactionReport(triggered=True).did_work is False  # no-op pass

    async def test_did_work_true_per_tier(self):
        assert CompactionReport(tool_results_cleared=1).did_work is True
        assert CompactionReport(summarized=True).did_work is True
        assert CompactionReport(turns_truncated=3).did_work is True


def _big(n: int) -> str:
    return "word " * n  # ~ n*1.25 tokens (ASCII)


def _tool(name: str, size: int = 400) -> dict:
    return {"role": "tool", "name": name, "tool_call_id": f"c_{name}", "content": _big(size)}


def _asst_call(call_id: str, name: str = "propose_edit", args: str = "{}") -> dict:
    """An assistant turn that made a tool call (OpenAI/Anthropic shape)."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function",
                        "function": {"name": name, "arguments": args}}],
    }


def _tool_result(call_id: str, size: int = 400) -> dict:
    """A tool result answering a specific tool_call id (resume-path shape)."""
    return {"role": "tool", "tool_call_id": call_id, "content": _big(size)}


def _has_orphan_tool(msgs: list[dict]) -> bool:
    """A provider (OpenAI/Anthropic) rejects a messages array where a tool result
    has no preceding assistant tool_call of the same id, OR an assistant tool_call
    has no following tool result. Either is an orphan."""
    call_ids = {tc.get("id") for m in msgs for tc in (m.get("tool_calls") or [])}
    result_ids = {m.get("tool_call_id") for m in msgs
                  if m.get("role") == "tool" or "tool_call_id" in m}
    # orphan tool result (no matching call)
    for m in msgs:
        if (m.get("role") == "tool" or "tool_call_id" in m) and m.get("tool_call_id") not in call_ids:
            return True
    # orphan tool call (no matching result)
    for m in msgs:
        for tc in (m.get("tool_calls") or []):
            if tc.get("id") not in result_ids:
                return True
    return False


class TestNoTrigger:
    async def test_under_trigger_is_unchanged(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, rep = await compact_messages(msgs, effective_limit=10_000)
        assert out is msgs
        assert rep.triggered is False

    async def test_null_limit_is_noop(self):
        msgs = [_tool("web_search"), {"role": "user", "content": _big(9999)}]
        out, rep = await compact_messages(msgs, effective_limit=None)
        assert rep.triggered is False


class TestMicrocompact:
    async def test_evicts_old_tool_results_keeps_last_n(self):
        msgs = [
            {"role": "system", "content": "sys"},
            _tool("a"), _tool("b"), _tool("c"), _tool("d"), _tool("e"),
            {"role": "user", "content": "now"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=1_000, keep_tool_results=2)
        assert rep.triggered and rep.tool_results_cleared == 3  # 5 tools - keep 2
        cleared = [m for m in out if m.get("role") == "tool" and m["content"] == _PLACEHOLDER]
        assert len(cleared) == 3
        # the last two tool results are kept verbatim
        kept = [m for m in out if m.get("role") == "tool" and m["content"] != _PLACEHOLDER]
        assert len(kept) == 2

    async def test_never_evicts_excluded_tool(self):
        msgs = [
            _tool("web_search"), _tool("web_search"), _tool("web_search"),
            _tool("web_search"), {"role": "user", "content": "q"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        # web_search is excluded → none cleared even though 4 > keep 1
        assert rep.tool_results_cleared == 0
        assert all(m["content"] != _PLACEHOLDER for m in out if m.get("role") == "tool")

    async def test_does_not_mutate_caller_messages(self):
        msgs = [_tool("a"), _tool("b"), _tool("c"), _tool("d"), {"role": "user", "content": "x"}]
        original_first = msgs[0]["content"]
        await compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        assert msgs[0]["content"] == original_first  # caller's list untouched


class TestFullCompactAndFailure:
    async def test_summarize_used_when_micro_insufficient(self):
        # one huge non-tool turn micro-compact can't shrink → summarizer runs.
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1,
            summarize=lambda _m: "compressed summary of the discussion",
        )
        assert rep.summarized is True
        assert any("<summary>" in (m.get("content") or "") for m in out)

    async def test_async_summarizer_is_awaited_and_used(self):
        # the production summarizer is an async LLM call — prove the await path.
        async def async_summarize(_m):
            return "async-compressed synopsis"

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=async_summarize,
        )
        assert rep.summarized is True
        assert any("async-compressed synopsis" in (m.get("content") or "") for m in out)

    async def test_summarize_failure_falls_through_to_truncate(self):
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
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=bad_summarize,
        )
        assert rep.summarize_failed is True
        assert rep.summarized is False
        assert rep.turns_truncated > 0  # fell through to the deterministic backstop
        assert "hard_truncate" in rep.steps


class TestHardTruncateAndOverflow:
    async def test_hard_truncate_keeps_pinned_and_recent(self):
        msgs = [{"role": "system", "content": "SYS"}] + [
            {"role": "user", "content": _big(2000)} for _ in range(6)
        ] + [{"role": "user", "content": "LAST"}]
        out, rep = await compact_messages(msgs, effective_limit=1_500, keep_recent=2)
        assert out[0]["content"] == "SYS"           # pinned kept, leads the prompt
        assert out[-1]["content"] == "LAST"          # recent tail kept
        assert rep.turns_truncated > 0

    async def test_overflow_when_pinned_alone_exceed_budget(self):
        # edge #4: non-evictable system messages alone blow the budget.
        msgs = [
            {"role": "system", "content": _big(5000)},
            {"role": "user", "content": "x"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=1_000, keep_recent=1)
        assert rep.overflowed is True


class TestToolPairSafety:
    """The resume path (agent→GUI 2nd pass) feeds a `working` array that CONTAINS
    assistant `tool_calls` + `role:tool` results into compaction. Structural
    truncation (hard-truncate, and the summarize tail-slice) must never split a
    tool-call/tool-result pair — an orphan makes the provider reject the turn 400."""

    def _resume_shaped(self) -> list[dict]:
        # system (pinned) + several tool exchanges + a trailing pending→answered pair.
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(600)},
            _asst_call("c_1"), _tool_result("c_1", 600),
            {"role": "assistant", "content": _big(600)},
            {"role": "user", "content": _big(600)},
            _asst_call("c_2"), _tool_result("c_2", 600),
            _asst_call("c_3"), _tool_result("c_3", 600),  # most recent exchange
        ]

    async def test_hard_truncate_never_orphans_a_tool_pair(self):
        # keep_recent=1 would slice the tail to a lone tool result (orphan) pre-fix;
        # keep_tool_results high so microcompact clears nothing → hard-truncate runs.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(
            msgs, effective_limit=1_500, keep_recent=1, keep_tool_results=99,
        )
        assert rep.triggered and rep.turns_truncated > 0
        assert "hard_truncate" in rep.steps
        assert not _has_orphan_tool(out), f"orphaned tool pair after truncate: {[m.get('role') for m in out]}"

    async def test_summarize_tail_slice_never_orphans(self):
        # summarize succeeds → work = pinned + summary + tail[-keep_recent:];
        # that slice must also land on a safe boundary.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(
            msgs, effective_limit=1_500, keep_recent=1, keep_tool_results=99,
            summarize=lambda _m: "the story so far",
        )
        assert rep.triggered
        assert not _has_orphan_tool(out), f"orphaned after summarize slice: {[m.get('role') for m in out]}"

    async def test_microcompact_preserves_pairing(self):
        # microcompact only blanks tool CONTENT (keeps the message + tool_call_id),
        # so pairing is intact even when it clears old results.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(msgs, effective_limit=2_000, keep_tool_results=1)
        assert not _has_orphan_tool(out)
