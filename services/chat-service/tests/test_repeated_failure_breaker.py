"""The repeated-identical-FAILURE breaker (2026-07-26).

The no-op-write breaker catches a SUCCESSFUL write that changed nothing; the read breaker
catches a SUCCESSFUL identical read. Neither catches the mirror case a weak model actually
loops on: the SAME (tool, args) call FAILING with the same error, over and over. Measured
live in the newcomer scenario step 8: book_get_chapter ×13 on "no active chapter with that
chapter_id" and book_update_details ×16 on "no fields to update" — the model blind-retrying a
call it cannot fix, with no breaker to stop it.

These drive the REAL loop through `_stream_with_tools` (a breaker green in isolation but not
wired into the loop is worthless), mirroring the no-op/read breaker tests. A FAILED call with
FIXED args stays legitimate — only an IDENTICAL repeat is the loop.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.stream_service import REPEATED_FAILURE_CAP
from tests.test_repeated_read_breaker import _fake_client_repeating, _tool_calls
from tests.test_spend_gate import _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"


def _tool(name: str = "book_get_chapter", tier: str = "R") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "read a chapter",
            "parameters": {"type": "object", "properties": {"chapter_id": {"type": "string"}}},
            "_meta": {"tier": tier},
        },
    }


async def _drive(*, times: int, envelope: dict, tool_name: str = "book_get_chapter", tier: str = "R"):
    """Drive a model that calls the SAME tool, same args, `times` times; every execution
    returns `envelope` (via the knowledge client mock)."""
    import app.services.stream_service as ss

    tool = _tool(tool_name, tier)
    kc = _kc()
    kc.mcp_execute_tool.return_value = envelope
    chunks = []
    with patch.object(ss, "Client", _fake_client_repeating(tool_name, times)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "write the opening scene"}],
            gen_params={"max_tokens": 100}, tools=[tool],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return chunks, kc


_FAIL = {"success": False, "error": "no active chapter with that chapter_id — call book_list kind=chapters for valid ids"}


class TestRepeatedFailureBreaker:
    @pytest.mark.asyncio
    async def test_a_single_failure_is_untouched(self):
        """One failed call is a legitimate attempt — never taxed."""
        chunks, kc = await _drive(times=1, envelope=_FAIL)
        assert kc.mcp_execute_tool.await_count == 1
        assert _tool_calls(chunks)[0]["ok"] is False

    @pytest.mark.asyncio
    async def test_repeated_identical_failure_is_short_circuited(self):
        """THE test. The same (tool, args) failing the same way is a loop — stopped after
        the cap, not run 13 times."""
        chunks, kc = await _drive(times=8, envelope=_FAIL)
        # only REPEATED_FAILURE_CAP calls actually execute; the rest are short-circuited
        assert kc.mcp_execute_tool.await_count == REPEATED_FAILURE_CAP, (
            "the identical-failure loop must be broken after the cap"
        )
        tc = _tool_calls(chunks)
        blocked = [t for t in tc if not t["ok"]]
        assert len(blocked) > REPEATED_FAILURE_CAP, "the short-circuited calls must be VISIBLE"
        steer = blocked[-1]["error"]
        # the steer echoes the tool's own error (which names the fix) and says STOP
        assert "book_get_chapter" in steer
        assert "call book_list" in steer          # the original error's guidance survives
        assert "STOP" in steer or "Do NOT" in steer

    @pytest.mark.asyncio
    async def test_a_success_is_never_blocked(self):
        """A tool that SUCCEEDS every time is not a failure loop — untouched by this breaker."""
        chunks, kc = await _drive(
            times=3, envelope={"success": True, "result": {"chapter_id": "c1", "title": "x"}},
        )
        # 3 identical SUCCESSFUL reads are bounded by the READ breaker, not this one; the point
        # here is this breaker does not fire on success. Assert none carried the failure steer.
        for t in _tool_calls(chunks):
            assert "FAILED" not in (t.get("error") or "")

    @pytest.mark.asyncio
    async def test_a_failing_write_loop_is_also_caught(self):
        """The book_update_details ×16 case — a Tier-A write failing 'no fields to update'."""
        chunks, kc = await _drive(
            times=6, tool_name="book_update_details", tier="A",
            envelope={"success": False, "error": "no fields to update"},
        )
        assert kc.mcp_execute_tool.await_count == REPEATED_FAILURE_CAP
        blocked = [t for t in _tool_calls(chunks) if not t["ok"]]
        assert any("no fields to update" in (t["error"] or "") for t in blocked)

    @pytest.mark.asyncio
    async def test_varying_args_same_error_is_caught(self):
        """THE live case: the weak model sends a DIFFERENT hallucinated chapter_id each time
        (varying args) but hits the IDENTICAL error. An (tool,args) key would never repeat; the
        (tool,ERROR) key catches it. Proves the breaker keys on the error, not the args."""
        import app.services.stream_service as ss
        from loreweave_llm import DoneEvent, ToolCallEvent, TokenEvent

        passes = {"n": 0}

        class VaryingArgsClient:
            def __init__(self, **kw): pass
            async def aclose(self): pass
            def stream(self, request):
                i = passes["n"]; passes["n"] += 1
                async def gen():
                    if i < 8:
                        # a DIFFERENT chapter_id every call — distinct args, same error
                        yield ToolCallEvent(index=0, id=f"c{i}", name="book_get_chapter",
                                            arguments_delta=f'{{"chapter_id": "wrong-{i}"}}')
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="ok"); yield DoneEvent(finish_reason="stop")
                return gen()

        kc = _kc()
        kc.mcp_execute_tool.return_value = _FAIL
        with patch.object(ss, "Client", VaryingArgsClient):
            n = 0
            async for _ in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "write chapter 1"}],
                gen_params={"max_tokens": 100}, tools=[_tool()],
                knowledge_client=kc, session_id="s", project_id=None, permission_mode="write",
            ):
                n += 1
                if n > 60: break
        # despite 8 DISTINCT-arg calls, the breaker stops execution after the cap
        assert kc.mcp_execute_tool.await_count == REPEATED_FAILURE_CAP
