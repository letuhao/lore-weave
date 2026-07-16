"""Phase G · G1 / ACP A2 — the rail DRIVE decision, now via the SDK harness.

The stream loop's drive+enforcement decision moved to `loreweave_agent_control.decide_rail_drive`
(ACP A2, RW-3) — it unifies the fresh-probe drive selection with the enforcement (nudge cap /
strength / honest give-up). The probe is INJECTED, so these tests pass a fixed probe directly
instead of monkeypatching. This covers: given a FRESH book-state, it drives the next step; it SKIPS
a step enforcement has given up on (`nudged_out`); and it drives NOTHING when the rail is complete.

The full hold/release effect (a REQUIRED unmet step holding a live turn, an explicit "skip"
releasing it) is proven live in the in-container S06 run — the stream generator is not unit-driven.
"""
from __future__ import annotations

from collections import Counter

from loreweave_agent_control import decide_rail_drive
from loreweave_agent_control.rail import BookState

PLANNING = [
    {"id": "propose", "tool": "plan_propose_spec", "done_when": "plan > 0"},
    {"id": "compile", "tool": "plan_compile", "done_when": "structure_fresh > 0"},
]


def _fixed_probe(state: BookState):
    async def _p(book_id, caller_user_id):
        return state
    return _p


async def _decide(state, *, nudged_out, turn_succeeded):
    return await decide_rail_drive(
        probe_fn=_fixed_probe(state),
        rail_specs=[("planning", PLANNING)], book_id="book", user_id="user",
        turn_start_counts={}, turn_succeeded=turn_succeeded,
        async_tools=frozenset(), nudged_out=nudged_out, nudge_counts=Counter(),
        enforcement_strength="enforce", required_nudge_cap=3,
    )


async def test_redrive_picks_the_compile_step_when_propose_is_done():
    # Propose landed (plan=1) but nothing compiled (structure_fresh=0) — the drivable next step is
    # the compile, exactly the S06 gap the rail must now push through.
    v = await _decide(
        BookState(plan=1, structure_fresh=0),
        nudged_out=set(), turn_succeeded=Counter({"plan_propose_spec": 1}),
    )
    assert v.should_drive is True
    assert v.slug == "planning" and v.step.step_id == "compile" and v.step.tool == "plan_compile"
    assert not v.giving_up


async def test_redrive_skips_a_step_that_enforcement_gave_up_on():
    # Same state, but the compile step is in nudged_out (the bounded auto-release already fired) —
    # the redrive must NOT return it again, so the turn ends honestly instead of looping forever.
    v = await _decide(
        BookState(plan=1, structure_fresh=0),
        nudged_out={"compile"}, turn_succeeded=Counter({"plan_propose_spec": 1}),
    )
    assert v.should_drive is False


async def test_redrive_returns_none_when_the_rail_is_complete():
    # Both effects satisfied → nothing to drive.
    v = await _decide(
        BookState(plan=1, structure_fresh=2),
        nudged_out=set(), turn_succeeded=Counter({"plan_propose_spec": 1, "plan_compile": 1}),
    )
    assert v.should_drive is False
