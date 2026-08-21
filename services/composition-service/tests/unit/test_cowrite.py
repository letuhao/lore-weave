"""Unit tests for the co-write stream + token metering."""

from __future__ import annotations

from loreweave_llm import ReasoningDirective
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


# ── T3.2 selection-edit dispatch (the LOOM-39 missing-enum regression-lock) ──

import pytest


def _profile(voice: str = "", lang: str = "en") -> BookProfile:
    return BookProfile(source_language=lang, voice=voice)


def test_each_selection_operation_dispatches_its_own_instruction():
    """Every selection operation must get its OWN instruction — a shared
    default would let a typo'd op silently behave like another (or draft a scene)."""
    seen = {}
    for op in ("rewrite", "expand", "describe", "scene_plan"):
        msgs = cowrite.build_selection_messages("the gate of ash", _profile(), op)
        user = msgs[1]["content"]
        assert cowrite._SELECTION_INSTRUCTIONS[op] in user
        assert "the gate of ash" in user  # the SELECTED passage is fed in
        seen[op] = user
    # Every instruction is distinct (no accidental aliasing).
    assert len({cowrite._SELECTION_INSTRUCTIONS[o] for o in ("rewrite", "expand", "describe", "scene_plan")}) == 4


def test_scene_plan_operation_requires_json_only():
    msgs = cowrite.build_selection_messages("a turning point", _profile(), "scene_plan")
    assert "Output ONLY valid JSON" in msgs[0]["content"]
    assert '"scenes"' in msgs[1]["content"]


def test_unregistered_selection_operation_raises_not_falls_back():
    """An unknown op RAISES — it must NOT fall back to a scene-draft default
    (dict.get(key, DEFAULT)-hides-a-missing-enum, LOOM-39)."""
    with pytest.raises(ValueError):
        cowrite.build_selection_messages("x", _profile(), "draft_scene")
    with pytest.raises(ValueError):
        cowrite.build_selection_messages("x", _profile(), "summarize")


def test_selection_messages_carry_voice_and_grounding():
    msgs = cowrite.build_selection_messages(
        "sel", _profile(voice="terse, noir"), "rewrite", guide="terser", grounding="<canon>X</canon>")
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "terse, noir" in system           # BookProfile voice steers the system prompt
    assert "Output ONLY the revised passage" in system
    assert "<canon>X</canon>" in user        # scene grounding precedes the instruction
    assert "Author guidance: terser" in user


# ── reasoning knob ──

def _ok_events():
    return [TokenEvent(delta="x"), UsageEvent(input_tokens=1, output_tokens=1), DoneEvent()]


async def test_a_resolved_directive_puts_BOTH_knobs_on_the_wire():
    """`reasoning_effort` alone is not the decision. `chat_template_kwargs` is the knob
    LM Studio / llama.cpp / vLLM actually honour, so sending one without the other applies
    the author's choice to some backends and not others."""
    sdk = FakeSDK(_ok_events())
    await _collect(sdk, reasoning=ReasoningDirective(effort="none", passthrough=False, source="user"))
    body = sdk.last_req.to_request_body()
    assert body["reasoning_effort"] == "none"
    assert body["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}


async def test_a_missing_directive_SUPPRESSES_rather_than_inheriting_the_template():
    """REGRESSION LOCK — this test previously asserted the exact opposite ("not passed →
    absent from the wire"), and that assertion is what the empty-draft incident was made of:
    with no knobs sent, a local drafter the platform had misclassified as non-reasoning kept
    its chat template's thinking ON, spent 800 output tokens on hidden reasoning, and returned
    `text=""` with status `completed`. A forgotten directive must fail SAFE."""
    sdk = FakeSDK(_ok_events())
    await _collect(sdk)  # no directive threaded at all
    body = sdk.last_req.to_request_body()
    assert body["reasoning_effort"] == "none"
    assert body["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}


async def test_a_passthrough_directive_still_sends_nothing():
    """The one case where silence IS the decision: a self-orchestrating model (Anthropic) has
    no such knob, and suppressing it would be out-thinking a model that decides for itself."""
    sdk = FakeSDK(_ok_events())
    await _collect(sdk, reasoning=ReasoningDirective(effort=None, passthrough=True, source="adaptive"))
    body = sdk.last_req.to_request_body()
    assert "reasoning_effort" not in body and "chat_template_kwargs" not in body


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


def test_regenerate_to_beat_is_a_REGISTERED_operation_not_the_generic_fallback():
    """W6 — the conformance drift retry must reach the drafter as its own instruction.

    `_OPERATION_INSTRUCTIONS` is a `.get(op, "Write the next passage of the scene.")`, so an
    UNREGISTERED operation silently degrades to that generic line instead of failing. This repo has
    already paid for that once: `useWhatIfTakes` sent a made-up `'diverge'` and got the weak
    fallback, caught only by a review. So the assertion is not "some instruction came back" — it is
    that this operation's OWN wording is present and the fallback's is not.
    """
    user = cowrite.build_messages("ctx", NEUTRAL, "regenerate_to_beat")[1]["content"]
    assert "did NOT realize its planned beat" in user
    assert "Write the next passage of the scene." not in user


def test_regenerate_to_beat_keeps_the_plan_and_changes_only_the_EXECUTION():
    """The retry must not drift into re-planning. A model told merely to 'try again' is free to
    pick an easier beat, which would make the conformance verdict pass by moving the goalposts."""
    user = cowrite.build_messages("ctx", NEUTRAL, "regenerate_to_beat")[1]["content"]
    assert "not which beat it is" in user
    assert "dramatised" in user.lower()          # landed on the page, not asserted


def test_regenerate_to_beat_still_carries_the_AUTHOR_guide():
    """Server-authored instruction and author guidance are different things; the retry keeps both."""
    user = cowrite.build_messages("ctx", NEUTRAL, "regenerate_to_beat", guide="colder, less dialogue")[1]["content"]
    assert "did NOT realize its planned beat" in user
    assert "colder, less dialogue" in user


def test_build_messages_neutral_no_forced_language():
    msgs = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")
    assert "language with code" not in msgs[0]["content"]


def test_build_messages_length_steer_fires_with_target_and_is_generic():
    # Fix #3 (2026-07-26): a whole-chapter draft passes a chapter-level target_words
    # (previously the chapter path passed none → free-runs short → pacing dips). The
    # LENGTH directive must fire on any target, and be worded GENERICALLY (not "FULL
    # scene") so it reads correctly for the chapter path too.
    user = cowrite.build_messages("ctx", NEUTRAL, "draft_chapter", "", target_words=2400)[1]["content"]
    assert "LENGTH:" in user and "2400" in user
    assert "FULL passage" in user            # generic — works for scene AND chapter
    assert "FULL scene of approximately" not in user  # the old scene-only wording is gone


def test_draft_scene_states_its_boundary_and_the_chapter_path_keeps_none():
    """SCENE-BOUNDARY (Mị Đế, 2026-07-30). The plan block shows the WHOLE chapter, so
    "draft this scene" alone let the drafter run straight through its neighbours: scene
    1's draft came back carrying scene 3's and scene 4's material. The boundary must be
    stated in the SCENE operation — and must NOT leak into the chapter operation, where
    covering every scene is the entire point."""
    scene = cowrite.build_messages("ctx", NEUTRAL, "draft_scene", target_words=900)[1]["content"]
    assert "ONLY this scene" in scene
    assert "do NOT write them" in scene

    chapter = cowrite.build_messages("ctx", NEUTRAL, "draft_chapter", target_words=2400)[1]["content"]
    assert "ONLY this scene" not in chapter
    assert "ENTIRE chapter" in chapter


def test_length_steer_never_tells_the_model_to_widen_its_scope():
    """The length directive is SHARED by the scene and chapter paths, so the boundary
    cannot live in it — but it must not fight the boundary either. Its old tail ("keep
    writing until the planned beats are fully played out", plural and unscoped) was the
    more concrete instruction and so it won over the singular "this scene"."""
    for op, target in (("draft_scene", 900), ("draft_chapter", 2400)):
        user = cowrite.build_messages("ctx", NEUTRAL, op, target_words=target)[1]["content"]
        assert "planned beats are fully played out" not in user
        assert "never by extending past the material you were asked to write" in user
        # Still generic: one wording that reads correctly for both paths.
        assert "FULL passage" in user


def test_build_messages_no_length_steer_without_target():
    # selection/revise/no-target callers stay unchanged (no LENGTH directive).
    user = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")[1]["content"]
    assert "LENGTH:" not in user
    user0 = cowrite.build_messages("ctx", NEUTRAL, "draft_scene", target_words=0)[1]["content"]
    assert "LENGTH:" not in user0


def test_build_messages_has_anti_reestablishment_instruction():
    # LOOM-36: the draft prompt must tell the drafter the context is ALREADY
    # established and to continue forward, not re-narrate prior scenes (the
    # cross-chapter re-establishment lever). Lock it against accidental removal.
    sys = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")[0]["content"]
    assert "ALREADY happened" in sys and "do NOT re-introduce" in sys


def test_build_messages_has_anti_repetition_instruction():
    # LOOM-69d: the diagnostic found the local drafter reuses distinctive images /
    # openings across scenes (recurring weather/colour motifs). The prompt must push
    # for surface variety — lock the clause against accidental removal.
    sys = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")[0]["content"]
    assert "Vary your prose" in sys and "do NOT reuse a distinctive image" in sys


def test_build_messages_has_pacing_craft_instruction():
    # Fix #5 (2026-07-26 pacing diagnostic): mid-arc chapters dipped on "fit to the beat"
    # for three concrete reasons — crammed/whiplash beats, uniform action-reaction cadence,
    # and stated-not-dramatised turns. The prompt must steer all three; lock it in.
    sys = cowrite.build_messages("ctx", NEUTRAL, "draft_scene")[0]["content"]
    assert "Control the PACING" in sys
    assert "BREATHE" in sys                         # anti-whiplash (let a rising beat breathe)
    assert "Vary your sentence rhythm" in sys       # anti-uniform-cadence
    assert "DRAMATISE emotional turning points" in sys and "do NOT state them" in sys  # show-at-turns


def test_char_estimate_over_estimates_and_clamps():
    assert cowrite.char_estimate("") == 0
    assert cowrite.char_estimate("abc") >= 1
