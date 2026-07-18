"""Track C Phase 2 — the repeated-read breaker.

H7 caps runaway WRITES. Nothing capped a runaway READ, on the theory that a read is harmless.

Measured live: gemma called `glossary_list_system_standards` TWENTY-FOUR times in one S01 run.
Its result was 44,000 chars (~11k tokens) — a THIRD of the turn's whole budget — so each repeat
pushed the previous copy of the same answer further out of the window. The model could never see
what it had already fetched, so it fetched it again. 24 tool calls; zero artifacts built.

A read that eats a third of the context window is not harmless.

(This file also exists because the first cut of the breaker referenced an undefined
REPEAT_READ_CAP and crashed EVERY chat turn with a NameError. The unit suite was green — because
nothing in it drove a real tool call through this branch. So these drive the real loop.)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.stream_service import REPEAT_READ_CAP
from tests.test_spend_gate import _fake_client, _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"


def _read_tool(name: str = "glossary_list_system_standards") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "list the standards",
            "parameters": {"type": "object", "properties": {}},
            "_meta": {"tier": "R"},
        },
    }


def _fake_client_repeating(tool_name: str, times: int):
    """A model that calls the SAME read, with the SAME args, `times` times in a row."""
    from loreweave_llm import DoneEvent, TokenEvent, ToolCallEvent

    passes = {"n": 0}

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def aclose(self):
            pass

        def stream(self, request):
            i = passes["n"]
            passes["n"] += 1

            async def gen():
                if i < times:
                    yield ToolCallEvent(index=0, id=f"c{i}", name=tool_name, arguments_delta="{}")
                    yield DoneEvent(finish_reason="tool_calls")
                else:
                    yield TokenEvent(delta="done")
                    yield DoneEvent(finish_reason="stop")

            return gen()

    return FakeClient


async def _drive(times: int):
    import app.services.stream_service as ss

    tool = _read_tool()
    name = tool["function"]["name"]
    kc = _kc()
    chunks = []
    with patch.object(ss, "Client", _fake_client_repeating(name, times)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "set up my world"}],
            gen_params={"max_tokens": 100}, tools=[tool],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return chunks, kc


def _tool_calls(chunks):
    return [c["tool_call"] for c in chunks if "tool_call" in c]


class TestRepeatedReadBreaker:
    @pytest.mark.asyncio
    async def test_a_normal_single_read_is_untouched(self):
        """The guard must not tax the common case."""
        chunks, kc = await _drive(times=1)
        tc = _tool_calls(chunks)
        assert len(tc) == 1
        assert tc[0]["ok"] is True
        kc.mcp_execute_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_unchanging_read_is_short_circuited(self):
        """THE test. The answer is already in the context and it has not moved; re-fetching it
        can only bury it. (It takes REPEAT_READ_CAP unchanged results to conclude that — the
        breaker must be sure the answer is STUCK, not merely repeated, or it would kill a
        legitimate poll. See TestPollingIsNotALoop.)"""
        chunks, kc = await _drive(times=8)
        tc = _tool_calls(chunks)

        assert kc.mcp_execute_tool.await_count < 8, "the loop must be broken"
        assert tc[0]["ok"] is True

        blocked = [t for t in tc if not t["ok"]]
        assert blocked, "the short-circuited calls must be VISIBLE, not silently dropped"
        for r in blocked:
            # no silent no-op: the model is told exactly why, and what to do instead
            assert "IDENTICAL result" in r["error"]
            assert "take the NEXT step" in r["error"]

    @pytest.mark.asyncio
    async def test_the_24_call_loop_actually_terminates(self):
        """24 identical calls is literally what the live S01 run did."""
        chunks, kc = await _drive(times=24)
        assert kc.mcp_execute_tool.await_count <= REPEAT_READ_CAP + 1


# ── the HIGH I shipped and caught: a poll is a repeated identical read ────────

class TestPollingIsNotALoop:
    """`jobs_get`, `translation_job_status`, `composition_get_generation_job` are all Tier-R,
    and the workflow rails DEPEND on watching an async job to completion ("do NOT begin a
    dependent step until it has finished").

    The first cut of this breaker counted CALLS. It would have blocked the second poll and
    stranded every async step in the catalogue — turning a fix for one broken tool into a
    break of the whole async-job contract. It now counts UNCHANGED RESULTS: a poll whose
    status moves is not a loop; a read that keeps handing back the byte-identical answer is.
    """

    @pytest.mark.asyncio
    async def test_a_poll_whose_result_CHANGES_is_never_blocked(self):
        import app.services.stream_service as ss

        tool = _read_tool("jobs_get")
        kc = _kc()
        # each poll returns a DIFFERENT status — this is a job progressing, not a loop
        statuses = [
            {"status": "queued"}, {"status": "running"},
            {"status": "running", "pct": 50}, {"status": "succeeded"},
        ]
        kc.mcp_execute_tool.side_effect = [
            {"success": True, "result": s} for s in statuses
        ]
        chunks = []
        with patch.object(ss, "Client", _fake_client_repeating("jobs_get", 4)):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "is it done?"}],
                gen_params={"max_tokens": 100}, tools=[tool],
                knowledge_client=kc, session_id="s", project_id=None,
                permission_mode="write",
            ):
                chunks.append(ch)

        # every poll went through — none was short-circuited
        assert kc.mcp_execute_tool.await_count == 4
        assert all(tc["ok"] for tc in _tool_calls(chunks))

    @pytest.mark.asyncio
    async def test_a_poll_STUCK_on_the_identical_answer_is_eventually_stopped(self):
        """The other half: if the status never moves, it IS a loop, and the model must be
        told to stop rather than spin the turn away."""
        import app.services.stream_service as ss

        tool = _read_tool("jobs_get")
        kc = _kc()
        kc.mcp_execute_tool.return_value = {"success": True, "result": {"status": "running"}}
        chunks = []
        with patch.object(ss, "Client", _fake_client_repeating("jobs_get", 8)):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "is it done?"}],
                gen_params={"max_tokens": 100}, tools=[tool],
                knowledge_client=kc, session_id="s", project_id=None,
                permission_mode="write",
            ):
                chunks.append(ch)

        assert kc.mcp_execute_tool.await_count < 8, "an unchanging poll must eventually stop"
        errs = [tc["error"] for tc in _tool_calls(chunks) if not tc["ok"]]
        assert any("IDENTICAL result" in (e or "") for e in errs)
