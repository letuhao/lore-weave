"""Unit tests for the co-write stream + token metering."""

from __future__ import annotations

from loreweave_llm.errors import LLMError
from loreweave_llm.models import DoneEvent, TokenEvent, UsageEvent

from app.engine import cowrite
from app.packer.profile import NEUTRAL, BookProfile


class FakeSDK:
    def __init__(self, events, raise_after=None):
        self._events = events
        self._raise_after = raise_after
        self.last_user = None

    async def stream(self, req, *, user_id):
        self.last_user = user_id
        self.last_req = req
        for i, ev in enumerate(self._events):
            if self._raise_after is not None and i == self._raise_after:
                raise LLMError("gateway dropped")
            yield ev


import uuid as _uuid


async def _collect(sdk, **kw):
    params = dict(user_id="u", model_source="user_model", model_ref=str(_uuid.uuid4()),
                  messages=[{"role": "user", "content": "hi"}], prompt_token_estimate=40,
                  max_output_tokens=256)
    params.update(kw)
    return [e async for e in cowrite.stream_draft(sdk, **params)]


# ── reasoning knob ──

async def test_reasoning_effort_threaded_into_stream_request():
    sdk = FakeSDK([TokenEvent(delta="x"), UsageEvent(input_tokens=1, output_tokens=1), DoneEvent()])
    await _collect(sdk, reasoning_effort="none")
    assert sdk.last_req.reasoning_effort == "none"


async def test_reasoning_effort_defaults_to_model_default():
    sdk = FakeSDK([TokenEvent(delta="x"), UsageEvent(input_tokens=1, output_tokens=1), DoneEvent()])
    await _collect(sdk)  # not passed → None (model default), absent from the wire
    assert sdk.last_req.reasoning_effort is None
    assert "reasoning_effort" not in sdk.last_req.to_request_body()


# ── metering ──

async def test_real_usage_frame_is_used():
    sdk = FakeSDK([TokenEvent(delta="Hello "), TokenEvent(delta="world"),
                   UsageEvent(input_tokens=50, output_tokens=2), DoneEvent()])
    out = await _collect(sdk)
    usage = out[-1]
    assert usage["type"] == "usage" and usage["text"] == "Hello world"
    assert usage["metering"].measured is True
    assert usage["metering"].input_tokens == 50 and usage["metering"].output_tokens == 2
    assert sdk.last_user == "u"  # user_id threaded per-call (internal auth)


async def test_absent_usage_frame_falls_back_never_zero():
    sdk = FakeSDK([TokenEvent(delta="abcdef"), DoneEvent()])  # no UsageEvent
    out = await _collect(sdk)
    m = out[-1]["metering"]
    assert m.measured is False
    assert m.output_tokens == cowrite.char_estimate("abcdef") > 0  # never 0
    assert m.input_tokens == 40  # falls back to the prompt estimate


async def test_zero_usage_frame_is_treated_as_unmeasured():
    sdk = FakeSDK([TokenEvent(delta="abcdef"), UsageEvent(input_tokens=0, output_tokens=0), DoneEvent()])
    out = await _collect(sdk)
    m = out[-1]["metering"]
    assert m.measured is False and m.output_tokens > 0  # zero frame → over-estimate, not 0


async def test_input_only_frame_falls_back_on_output():
    # /review-impl M6 #3: a frame with input>0 but output=0 must NOT meter
    # output as 0 — fall back to the char estimate (never 0 with prose present).
    sdk = FakeSDK([TokenEvent(delta="some prose here"),
                   UsageEvent(input_tokens=80, output_tokens=0), DoneEvent()])
    m = (await _collect(sdk))[-1]["metering"]
    assert m.measured is False
    assert m.output_tokens == cowrite.char_estimate("some prose here") > 0
    assert m.input_tokens == 80  # the real input frame is still used


async def test_mid_stream_cap_stops_and_partial_saves():
    big = [TokenEvent(delta="x" * 30) for _ in range(10)]  # each ~10 est tokens
    out = await _collect(FakeSDK(big + [DoneEvent()]), hard_cap_output=15)
    assert any(e["type"] == "capped" for e in out)
    assert out[-1]["capped"] is True
    # partial text is preserved
    assert len(out[-1]["text"]) > 0


async def test_llm_error_emits_error_event_and_still_meters():
    # yields "partial" (i=0), then raises at i=1 before the 2nd event
    sdk = FakeSDK([TokenEvent(delta="partial"), TokenEvent(delta="never")], raise_after=1)
    out = await _collect(sdk)
    assert any(e["type"] == "error" for e in out)
    assert out[-1]["type"] == "usage"  # still terminates with a metering frame


# ── prompt building (de-bias) ──

def test_build_messages_threads_language_and_voice():
    msgs = cowrite.build_messages("<canon>x</canon>", BookProfile(source_language="vi", voice="terse"), "continue", guide="be tense")
    sys = msgs[0]["content"]
    assert "'vi'" in sys and "terse" in sys
    assert "be tense" in msgs[1]["content"] and "Continue the scene" in msgs[1]["content"]


def test_build_messages_neutral_no_forced_language():
    msgs = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")
    assert "language with code" not in msgs[0]["content"]


def test_build_messages_has_anti_reestablishment_instruction():
    # LOOM-36: the draft prompt must tell the drafter the context is ALREADY
    # established and to continue forward, not re-narrate prior scenes (the
    # cross-chapter re-establishment lever). Lock it against accidental removal.
    sys = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")[0]["content"]
    assert "ALREADY happened" in sys and "do NOT re-introduce" in sys


def test_char_estimate_over_estimates_and_clamps():
    assert cowrite.char_estimate("") == 0
    assert cowrite.char_estimate("abc") >= 1
