"""D-RAIL-PINNED-TURN-NEVER-COMPLETES — the turn that hangs forever, cut where it happens.

    THE INVARIANT. A single response stream may not emit the same (tool, arguments) without
    bound. Past the cap the pass is aborted through the loop path that already exists.

CAPTURED LIVE 2026-08-30 from LM Studio's own server log, the first time this stall was seen in
front of it rather than inferred:

    translation_update_settings mentions in ONE turn   555
    identical argument strings                         274 x {"book_id":"current_book",
                                                              "target_language":["vi"]}
    highest output_index                               137
    slot n_tokens across repeats            27141 -> 27222 -> 27303 -> 27384  (+81 each)

The chat-service dispatched NONE of them: zero rows with tool_calls. That is the whole mechanism.
Every breaker this service owns — the repeat-breaker, H7's write cap, the turn ceiling, the
tool_list caps — acts on a call that has been DISPATCHED, and nothing is dispatched until the
response stream ends. The stream never ends, so no guard is ever consulted and the turn is pinned
open. `llm_stream_idle_read_timeout_s = 0.0` is deliberate and is not the cause; it is why nothing
else trips either, since frames keep arriving and there is no idle to time out.

The mechanism to reuse was already there and merely EMPTY: `ReasoningLoopDetector` is fed only by
TokenEvent and ReasoningEvent deltas, so it watches the two TEXT channels and is blind to the tool
channel one branch away. `tool_frags` was an unbounded dict keyed by the provider's own index.

WHY THE BAR IS 8 AND NOT A ROUND NUMBER. Over 16,554 (tool, arguments) groups within a pass in the
live store: p50 = 1, p99 = 3, p99.9 = 8, max = 540. A flat CALL-COUNT cap was measured first and
REJECTED — one legitimate pass made 30 calls across 10 DISTINCT tools, so volume does not
discriminate. Repetition does: every group above 8 is a pathology (tool_list{"category":"book"}
x540, glossary_list_chapter_links x178, book_get on one id x63) and the 43 groups in the 5-to-8
band are ordinary reads, left untouched.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.stream_service import IDENTICAL_TOOL_CALL_CAP
from tests.test_spend_gate import _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"

# The arguments from the captured turn, byte for byte.
_LIVE_ARGS = '{"book_id":"current_book","target_language":["vi"]}'


def _tool(name: str = "translation_update_settings") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "set the translation target language",
            "parameters": {"type": "object", "properties": {"book_id": {"type": "string"}}},
            "_meta": {"tier": "R"},
        },
    }


def _client_repeating(n: int, args: str = _LIVE_ARGS, name: str = "translation_update_settings"):
    """One stream that emits the same call `n` times and only then finishes.

    This is the shape of the captured stall. The DoneEvent at the end is a KINDNESS the real
    provider did not extend — live, the stream simply never ended. A test cannot hang forever and
    still be a test, so the generator terminates; what is asserted below is that the service
    stopped ITSELF well before reaching it, which is the property that matters.

    🔴 IT COUNTS WHAT IT YIELDED, and every assertion in this file reads that counter rather than
    the dispatch count. The first draft asserted on `mcp_execute_tool.call_count` and its own
    anti-vacuity control refuted it: the service ALREADY collapses byte-identical calls after the
    stream ends (`D-TOOLCALL-DUP-IDENTICAL`, and 274 repeats dispatched 3), and TIER_A_AGGREGATE_CAP
    trims the distinct case. Those guards are real and they are downstream — they are exactly the
    guards the live stall never reaches, because reaching them requires the stream to END. So
    dispatch count cannot see this defect at all, and consumption is the only observable that
    isolates it.
    """
    # PER PASS, not per turn. A turn makes several passes and pooling them would report 1370 for
    # a 274-event stream and hide which pass was bounded — the same denominator mistake this loop
    # has made before. The cut is a property of ONE stream, so the deepest single pass is what is
    # asserted on.
    yielded = {"n": 0, "max": 0}
    from loreweave_llm import DoneEvent, ToolCallEvent

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def aclose(self):
            pass

        def stream(self, request):
            yielded["n"] = 0

            async def gen():
                for i in range(n):
                    yielded["n"] += 1
                    yielded["max"] = max(yielded["max"], yielded["n"])
                    # args=None means DISTINCT arguments per call — the legitimate shape.
                    _a = args if args is not None else '{"book_id":"b' + str(i) + '"}'
                    yield ToolCallEvent(index=i, id=f"c{i}", name=name, arguments_delta=_a)
                yield DoneEvent(finish_reason="tool_calls")

            return gen()

    FakeClient.yielded = yielded
    return FakeClient


async def _drive(n: int, **kw):
    import app.services.stream_service as ss

    kc = _kc()
    kc.mcp_execute_tool.return_value = {"success": True, "result": {"ok": True}}
    chunks = []
    fake = _client_repeating(n, **kw)
    with patch.object(ss, "Client", fake):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "dich sach nay sang tieng Viet"}],
            gen_params={"max_tokens": 100}, tools=[_tool()],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return fake.yielded["max"], "".join(c.get("content") or "" for c in chunks)


class TestTheStreamIsBounded:
    @pytest.mark.asyncio
    async def test_the_repeating_stream_is_ABANDONED_not_drained(self):
        """THE captured turn, and the whole defect in one assertion. Live this stream had no end,
        so 'the service reads it all and then decides' is not a strategy — the deciding never
        happens. The pass must let go of the stream itself."""
        consumed, _ = await _drive(274)
        assert consumed <= IDENTICAL_TOOL_CALL_CAP + 4, (
            f"the service read {consumed} of 274 repeats before letting go — against a provider "
            "that does not stop, that is an unbounded read and the turn stays pinned open")

    @pytest.mark.asyncio
    async def test_the_turn_still_ENDS(self):
        """A cut that produced no reply would trade a hang for a silence. The turn must come back
        with something a reader can act on."""
        _, text = await _drive(274)
        assert text.strip(), "the turn ended with no text at all — a silent stop is not a fix"

    @pytest.mark.asyncio
    async def test_an_ORDINARY_repeat_is_read_to_the_END(self):
        """🔴 THE HALF THAT MUST NOT BE TRADED, and the reason the bar was measured rather than
        picked. 8 identical reads is p99.9 of real traffic — 43 live groups sit in the 5-to-8 band
        on ordinary tools. Cutting them would break working turns to fix a broken one."""
        consumed, _ = await _drive(8)
        assert consumed == 8, (
            f"a legitimate 8-repeat pass was cut after {consumed} — the cap is reaching into "
            "measured, ordinary traffic")

    @pytest.mark.asyncio
    async def test_DISTINCT_calls_are_never_cut_however_many(self):
        """Volume is not the discriminator. A pass making many calls with different arguments is
        doing work — one measured legitimate pass made 30 calls across 10 distinct tools. Only
        repetition is the signal, so 30 distinct calls must be read to the end."""
        consumed, _ = await _drive(30, args=None)
        assert consumed == 30, (
            f"{consumed} of 30 DISTINCT calls were read before the cut — the cap is counting "
            "volume, which the measurement says does not discriminate")


class TestItIsTheCapDoingTheWork:
    """🔴 ANTI-VACUITY, and it doubles as the RED proof against the original.

    Raising the cap out of reach restores the code exactly as it was before this fix: the settle
    bookkeeping has no observable effect when the threshold is never crossed, so a stream drained
    to its end under an unreachable cap IS the pre-fix service, reproduced. If this goes green,
    the cut above comes from something else and this file is testing nothing.

    This control has already earned its place once. It refuted the first draft of this file, whose
    assertions read the dispatch count — and showed that the pre-fix service dispatched 3, not 274,
    because a downstream dedup was doing work the stall never reaches.
    """

    @pytest.mark.asyncio
    async def test_with_the_cap_out_of_reach_the_whole_stream_is_drained(self):
        import app.services.stream_service as ss

        with patch.object(ss, "IDENTICAL_TOOL_CALL_CAP", 10 ** 9):
            consumed, _ = await _drive(274)
        assert consumed == 274, (
            f"only {consumed} of 274 were read with the cap made unreachable — something OTHER "
            "than the cap is bounding this stream, and the mechanism named here is not the one "
            "doing the work")
