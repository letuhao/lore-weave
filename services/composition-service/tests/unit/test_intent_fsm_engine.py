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

pytestmark = pytest.mark.asyncio

_BEATS = [{"key": "hook"}, {"key": "midpoint"}, {"key": "climax"}]


def _llm(*replies: str):
    """A scripted model + a call log, so the BOUND is asserted on the count, not on a docstring."""
    calls: list[list[dict]] = []
    seq = list(replies)

    async def call(messages, max_tokens):
        calls.append(messages)
        return seq.pop(0) if seq else ""
    call.calls = calls  # type: ignore[attr-defined]
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
