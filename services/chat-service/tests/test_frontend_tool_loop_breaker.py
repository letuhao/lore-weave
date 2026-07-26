"""D-FE-TOOL-LOOP — frontend tools must not bypass the repeated-failure breaker.

Measured live (Mị Đế author-dogfood, 2026-07-26, session 019f9f2e): gemma emitted
~205 identical malformed `glossary_propose_entity_edit` calls in ONE turn —
`{"base_version":"1","book_id":",changes:[{field_label:"}` every single time — and the
turn never converged; the user had to press Stop after ~4 minutes. The backend sibling
(`glossary_propose_entities`) tripped its breaker at 2 failures the same turn.

Root cause: the frontend-tool branch in `_stream_with_tools` sits ABOVE every loop
guard. Validation failures were fed back to the model but never recorded into
`fail_by_tool_error`, and the blank-args cap is only checked on the backend dispatch
path — so an invalid frontend call looped unbounded.

These drive the REAL loop (a breaker green in isolation but not wired in is worthless),
mirroring test_repeated_failure_breaker.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.frontend_tools import GLOSSARY_PROPOSE_EDIT_TOOL
from app.services.stream_service import REPEATED_FAILURE_CAP
from tests.test_spend_gate import _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"

# the EXACT malformed args gemma looped on, live (valid JSON, garbage values,
# missing the required entity_id + changes)
_LIVE_MALFORMED_ARGS = '{"base_version":"1","book_id":",changes:[{field_label:"}'

_FE_TOOL_NAME = "glossary_propose_entity_edit"


def _fake_client_fe_looping(times: int, arguments: str = _LIVE_MALFORMED_ARGS):
    """A model that re-emits the SAME frontend tool call `times` times, then stops."""
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
                    yield ToolCallEvent(
                        index=0, id=f"c{i}", name=_FE_TOOL_NAME, arguments_delta=arguments
                    )
                    yield DoneEvent(finish_reason="tool_calls")
                else:
                    yield TokenEvent(delta="done")
                    yield DoneEvent(finish_reason="stop")

            return gen()

    return FakeClient


def _tool_calls(chunks: list[dict]) -> list[dict]:
    return [c["tool_call"] for c in chunks if "tool_call" in c]


async def _drive(times: int):
    import app.services.stream_service as ss

    kc = _kc()
    chunks = []
    with patch.object(ss, "Client", _fake_client_fe_looping(times)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "set up my main character"}],
            gen_params={"max_tokens": 100}, tools=[GLOSSARY_PROPOSE_EDIT_TOOL],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return chunks, kc


class TestFrontendToolLoopBreaker:
    @pytest.mark.asyncio
    async def test_single_invalid_call_gets_the_raw_validation_error(self):
        """One invalid call is a legitimate mistake — the model gets the specific
        validation error it knows how to repair, not a STOP steer."""
        chunks, kc = await _drive(times=1)
        tc = _tool_calls(chunks)
        assert len(tc) == 1 and tc[0]["ok"] is False
        assert "STOP" not in (tc[0]["error"] or "")
        assert kc.mcp_execute_tool.await_count == 0  # frontend tool never hits the backend

    @pytest.mark.asyncio
    async def test_identical_invalid_frontend_loop_is_steered_and_bounded(self):
        """THE live case. The same invalid frontend call over and over must flip to the
        STOP steer after the cap instead of feeding the same raw error 200 times."""
        chunks, kc = await _drive(times=8)
        tc = _tool_calls(chunks)
        assert all(t["ok"] is False for t in tc)
        assert kc.mcp_execute_tool.await_count == 0
        raw = [t for t in tc if "STOP" not in (t["error"] or "")]
        steered = [t for t in tc if "STOP" in (t["error"] or "")]
        # the first CAP failures get the repairable raw error; every later one is steered
        # (the de-advertise escalation may end the turn before all 8 re-emits land —
        # FEWER passes than the model attempted is the point, more raw ones is the bug)
        assert len(raw) == REPEATED_FAILURE_CAP
        assert len(steered) >= 1
        assert _FE_TOOL_NAME in steered[0]["error"]
        # steer echoes the underlying validation error so the model can still self-repair
        assert "FAILED" in steered[0]["error"]

    @pytest.mark.asyncio
    async def test_turn_still_terminates_with_final_text(self):
        """After the loop is steered, a model that recovers can still land its plain-text
        reply (3 failures leaves passes inside the MAX_TOOL_ITERATIONS ceiling)."""
        chunks, _ = await _drive(times=3)
        text = "".join(c["content"] for c in chunks if "content" in c)
        assert "done" in text

    @pytest.mark.asyncio
    async def test_a_model_that_never_recovers_is_still_bounded(self):
        """A model that re-emits the invalid call forever is cut off by the pass ceiling —
        the live failure ran ~205 calls; anything ≤ the ceiling proves the bound."""
        from app.services.stream_service import MAX_TOOL_ITERATIONS

        chunks, _ = await _drive(times=50)
        tc = _tool_calls(chunks)
        assert 0 < len(tc) <= MAX_TOOL_ITERATIONS
