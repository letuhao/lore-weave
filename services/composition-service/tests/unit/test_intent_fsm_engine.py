"""The propose step's bound and its filtering (spec §2 "no step can loop", §5 constraint).

Pure — an injected `llm` callable, no DB. What is proven here is the arithmetic of the bound and the
candidate hygiene; the stateful machine is proven against real Postgres in
`tests/integration/db/test_intent_fsm_run.py`.
"""
from __future__ import annotations

import json

import pytest

from app.services.intent_fsm import engine
from app.services.intent_fsm.slots import spec


_BEATS = [{"key": "hook"}, {"key": "midpoint"}, {"key": "climax"}]


def _llm(*replies: str):
    """A scripted model + a call log, so the BOUND is asserted on the count, not on a docstring."""
    calls: list[list[dict]] = []
    formats: list = []
    seq = list(replies)

    # The seam takes a registry CODE, not a number — an engine that cannot be handed an
    # integer cannot re-introduce a literal. `budget`/`target` mirror the real binding.
    async def call(messages, *, budget, target=None, response_format=None):
        calls.append(messages)
        formats.append(response_format)
        return seq.pop(0) if seq else ""
    call.calls = calls        # type: ignore[attr-defined]
    call.formats = formats    # type: ignore[attr-defined]
    return call


def _ok(*values):
    return json.dumps({"candidates": [{"value": v, "why": "because"} for v in values]})


async def test_one_call_when_the_first_reply_is_usable():
    llm = _llm(_ok("hook", "midpoint"))
    cands, calls, retried = await engine.propose(
        llm, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook", "midpoint"]
    assert (calls, retried) == (1, False)
    assert len(llm.calls) == 1


async def test_exactly_ONE_retry_then_it_gives_up():
    """The bound that makes a weak model safe to drive. A second bad reply must END the step, not
    trigger a third attempt — an unbounded repair loop against a model that cannot produce the shape
    is how a run burns real money going nowhere."""
    llm = _llm("I think chapter one should be about...", "still not JSON, sorry")
    cands, calls, retried = await engine.propose(
        llm, spec("goal"), node={"title": "C1"}, filled={}, canon=[], beats=[], n=3)
    assert cands == []
    assert (calls, retried) == (2, True)
    assert len(llm.calls) == 2, "a third call means the step can loop"


async def test_the_retry_feeds_the_failure_back():
    llm = _llm("garbage", _ok("she wants the sword"))
    cands, calls, retried = await engine.propose(
        llm, spec("goal"), node={"title": "C1"}, filled={}, canon=[], beats=[], n=3)
    assert [c["value"] for c in cands] == ["she wants the sword"]
    assert (calls, retried) == (2, True)
    assert "garbage" in llm.calls[1][-2]["content"]


async def test_a_closed_slot_DROPS_anything_outside_its_set():
    """An option the column will reject is a broken choice, and offering it to the author is worse
    than offering nothing: they pick it, the apply 422s, and the machine looks unreliable for a
    mistake the model made."""
    llm = _llm(_ok("hook", "denouement", "midpoint"))
    cands, _, _ = await engine.propose(
        llm, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook", "midpoint"]


async def test_an_uncoercible_candidate_is_dropped_not_repaired():
    llm = _llm(_ok(3, "very high", 99, 5))
    cands, _, _ = await engine.propose(
        llm, spec("tension"), node={"title": "C1"}, filled={}, canon=[], beats=[], n=3)
    assert [c["value"] for c in cands] == [3, 5]


async def test_duplicates_collapse_so_N_means_N_DISTINCT_options():
    """Three identical candidates is one option wearing a rosette — and it would read as a healthy
    proposal in the instrument while giving the author nothing to choose between."""
    llm = _llm(_ok("hook", "hook", "midpoint"))
    cands, _, _ = await engine.propose(
        llm, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook", "midpoint"]


async def test_the_prompt_carries_what_the_author_already_settled():
    """The mechanism behind spec §5: by the time an open slot is asked, the model is TRANSFORMING a
    partly-specified chapter rather than inventing one. If the settled block ever stopped being
    rendered, quality would drop with nothing failing."""
    llm = _llm(_ok("she loses the duel"))
    await engine.propose(
        llm, spec("outcome"), node={"title": "C1", "synopsis": "the duel"},
        filled={"goal": "win the duel", "beat_role": "midpoint"},
        canon=["Lâm Uyên", "Tô gia"], beats=[], n=3)
    sent = llm.calls[0][-1]["content"]
    assert "win the duel" in sent and "midpoint" in sent
    assert "Lâm Uyên" in sent


async def test_a_closed_slot_is_asked_as_a_PICK_and_an_open_one_is_not():
    """The visible branch that IS the experiment of spec §10 Q1 — if a closed slot stopped being
    asked as a pick, the arms would still run and quietly measure nothing."""
    closed = _llm(_ok("hook"))
    await engine.propose(closed, spec("beat_role"), node={"title": "C1"}, filled={},
                         canon=[], beats=_BEATS, n=3)
    assert "midpoint" in closed.calls[0][-1]["content"]

    open_ = _llm(_ok("she wants out"))
    await engine.propose(open_, spec("goal"), node={"title": "C1"}, filled={},
                         canon=[], beats=_BEATS, n=3)
    assert "midpoint" not in open_.calls[0][-1]["content"]


async def test_a_bare_array_reply_is_accepted_too():
    """LLM schemas tolerate at validation and filter at postprocess — a weak model that returns the
    array without the wrapper has still answered correctly."""
    llm = _llm(json.dumps([{"value": "hook"}]))
    cands, calls, _ = await engine.propose(
        llm, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook"] and calls == 1


async def test_json_wrapped_in_a_markdown_fence_survives():
    llm = _llm("```json\n" + _ok("hook") + "\n```")
    cands, calls, _ = await engine.propose(
        llm, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook"] and calls == 1


# ── grammar-constrained decoding ─────────────────────────────────────────────────────────────────

async def test_a_closed_slots_enum_reaches_the_DECODER_not_just_the_prompt():
    """`provider-registry` forwards `response_format` to LM Studio, where llama.cpp enforces it at
    the grammar layer — so an invalid beat key becomes unemittable rather than emitted-then-dropped.

    Measured 2026-07-28 on 18 labelled lines: parse failures 2 → 0, quality unchanged, and a fixed
    seed reproduces 18/18. That last one is why this matters beyond tidiness: three of this POC's
    wrong conclusions came from a hand parser failing and being read as a model failure.
    """
    llm = _llm(_ok("hook"))
    await engine.propose(llm, spec("beat_role"), node={"title": "C1"}, filled={},
                         canon=[], beats=_BEATS, n=3)
    fmt = llm.formats[0]
    assert fmt["type"] == "json_schema"
    item = fmt["json_schema"]["schema"]["properties"]["candidates"]["items"]
    assert item["properties"]["value"]["enum"] == ["hook", "midpoint", "climax"]
    assert item["additionalProperties"] is False


async def test_an_open_slot_constrains_the_TYPE_but_carries_no_enum():
    llm = _llm(_ok("she wants out"))
    await engine.propose(llm, spec("goal"), node={"title": "C1"}, filled={},
                         canon=[], beats=[], n=3)
    value = llm.formats[0]["json_schema"]["schema"]["properties"]["candidates"]["items"] \
        ["properties"]["value"]
    assert value == {"type": "string"}

    num = _llm(_ok(3))
    await engine.propose(num, spec("tension"), node={"title": "C1"}, filled={},
                         canon=[], beats=[], n=3)
    v2 = num.formats[0]["json_schema"]["schema"]["properties"]["candidates"]["items"] \
        ["properties"]["value"]
    assert v2["type"] == "integer" and v2["enum"] == [1, 2, 3, 4, 5]


async def test_a_provider_that_REJECTS_the_schema_still_gets_an_answer():
    """Not every provider honours `response_format`. A hard failure here would make the slot depend
    on a capability the platform does not require — so the rejection falls back to free-form, and the
    post-filter that was always there catches what the grammar would have."""
    seen = []

    # The seam takes a registry CODE, not a number — an engine that cannot be handed an
    # integer cannot re-introduce a literal. `budget`/`target` mirror the real binding.
    async def call(messages, *, budget, target=None, response_format=None):
        seen.append(response_format)
        if response_format is not None:
            raise RuntimeError("400 unsupported response_format")
        return _ok("hook", "denouement")

    cands, calls, retried = await engine.propose(
        call, spec("beat_role"), node={"title": "C1"}, filled={}, canon=[], beats=_BEATS, n=3)
    assert [c["value"] for c in cands] == ["hook"], "the post-filter must still drop the bad key"
    assert (calls, retried) == (1, False), "a schema rejection is not a failed proposal"
    assert seen[0] is not None and seen[1] is None


async def test_the_retry_drops_the_schema():
    """Repeating a grammar-constrained call that came back unusable would fail the same way — the
    model is not disagreeing about the format, it has nothing to say in it."""
    llm = _llm("not json at all", _ok("hook"))
    await engine.propose(llm, spec("beat_role"), node={"title": "C1"}, filled={},
                         canon=[], beats=_BEATS, n=3)
    assert llm.formats[0] is not None
    assert llm.formats[1] is None
