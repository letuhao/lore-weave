"""ACP A2 / RW-3 / RV-H3 — the drive harness verdict, in isolation.

Proves the UNIFIED drive+enforcement decision (was `_maybe_redrive_rail` + the inline block at
stream_service:1806-1853): a fresh probe drives the next step; the multi-turn nudge→nudge→give-up
sequence flips to an honest give-up at the deploy cap; a degraded probe ends the turn; and the
escape-hatch (`nudged_out`) skips a step. The probe is INJECTED (RW-11) — no chat import.
"""
from __future__ import annotations

from collections import Counter

import pytest

from loreweave_agent_control import BookState, decide_rail_drive
from loreweave_agent_control.rail import honest_giveup_directive

_STEPS = [
    {"id": "s1", "tool": "t1", "done_when": "cast > 0"},
    {"id": "s2", "tool": "t2", "done_when": "plan > 0"},  # REQUIRED (no optional flag)
]
_RAIL = [("demo", _STEPS)]


def _probe(**counts):
    async def _fn(_book, _user):
        return BookState(**counts)
    return _fn


async def _decide(nudge_counts, nudged_out, strength="enforce", cap=3, state=None, mode="interactive"):
    return await decide_rail_drive(
        probe_fn=_probe(**(state or {"cast": 3, "plan": 0})),
        rail_specs=_RAIL, book_id="b", user_id="u",
        turn_start_counts=None, turn_succeeded=Counter(),
        async_tools=frozenset(), nudged_out=nudged_out, nudge_counts=nudge_counts,
        enforcement_strength=strength, required_nudge_cap=cap, mode=mode,
    )


@pytest.mark.asyncio
async def test_autonomous_mode_parks_an_exhausted_step_instead_of_reprompting():
    # ACP-10: an AUTONOMOUS runtime has no user to re-prompt — an exhausted REQUIRED step PARKS
    # (escalate + move on), never a hold-and-reprompt. The interactive path (elsewhere) re-prompts.
    counts, out = Counter(), set()
    v1 = await _decide(counts, out, cap=2, mode="autonomous")
    v2 = await _decide(counts, out, cap=2, mode="autonomous")
    assert v1.should_drive and not v1.parked            # nudge 1: still drivable
    assert v2.should_drive is False and v2.parked is True  # nudge 2 == cap: PARK, don't hold
    assert v2.park_reason and "parked" in v2.park_reason
    assert v2.directive_text is None                    # no user-facing directive in autonomous mode
    assert "s2" in out                                  # still marked exhausted


@pytest.mark.asyncio
async def test_drives_the_first_not_done_step():
    v = await _decide(Counter(), set())
    assert v.should_drive is True
    assert v.step.step_id == "s2"           # s1 done (cast=3>0), s2 next (plan=0)
    assert not v.giving_up
    assert "call `t2`" in v.directive_text  # the forceful nudge


@pytest.mark.asyncio
async def test_multi_turn_nudge_then_honest_giveup_at_cap():
    # RV-H3: the cross-turn nudge counter drives the hold; at the deploy cap an ENFORCED step
    # flips to the honest give-up (never a silent drop).
    counts, out = Counter(), set()
    v1 = await _decide(counts, out, cap=2)
    v2 = await _decide(counts, out, cap=2)
    assert v1.should_drive and not v1.giving_up          # nudge 1
    assert v2.should_drive and v2.giving_up              # nudge 2 == cap → give up
    assert v2.directive_text == honest_giveup_directive(v2.step)
    assert "s2" in out                                   # marked to stop re-driving


@pytest.mark.asyncio
async def test_nudge_strength_gentle_never_honest_giveup():
    # Under "nudge" strength a required step is NOT enforced (optional cap = 1): it is nudged
    # ONCE, gently (never the honest give-up), then dropped from re-driving — byte-identical to
    # stream_service's pre-extraction behavior. The property: it NEVER emits an honest give-up.
    counts, out = Counter(), set()
    v1 = await _decide(counts, out, strength="nudge", cap=2)
    assert v1.should_drive and not v1.giving_up          # gentle nudge, not a hold
    assert "s2" in out                                   # optional cap=1 → not re-driven again
    v2 = await _decide(counts, out, strength="nudge", cap=2)
    assert v2.should_drive is False                      # already nudged out → end the turn


@pytest.mark.asyncio
async def test_all_done_ends_the_turn():
    v = await _decide(Counter(), set(), state={"cast": 3, "plan": 1})
    assert v.should_drive is False


@pytest.mark.asyncio
async def test_escape_hatch_skips_a_nudged_out_step():
    # A step already in `nudged_out` is not re-driven — the turn ends.
    v = await _decide(Counter(), {"s2"})
    assert v.should_drive is False


@pytest.mark.asyncio
async def test_degraded_probe_ends_the_turn_never_raises():
    async def _boom(_b, _u):
        raise RuntimeError("probe down")
    v = await decide_rail_drive(
        probe_fn=_boom, rail_specs=_RAIL, book_id="b", user_id="u",
        turn_start_counts=None, turn_succeeded=Counter(), async_tools=frozenset(),
        nudged_out=set(), nudge_counts=Counter(), enforcement_strength="enforce", required_nudge_cap=3,
    )
    assert v.should_drive is False  # degraded → end the turn, no raise
