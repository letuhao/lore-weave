"""D-LAZY-TAIL-UNUSED — discovery is a RAIL STEP, driven, not hoped for.

MEASURED 2026-08-14 (docs/eval/toolloop/2026-08-14/batch2.json, 30 runs of five ordinary
authoring requests): `tool_list` was called on 1 run and `tool_load` on 0 — while BOTH were
advertised on every single run, a premise that was verified rather than assumed. The model works
from the ~48 tools already on the surface and, when the right one is not there, uses the nearest
one that is. So the lazy tail is not a fallback; it is dead weight, and whatever the deterministic
pre-filter puts on the wire is the entire reachable catalogue for that turn.

A discovery SCENT in the prompt was tried and REVERTED: it demonstrably reached the model (the
context breakdown shows the note growing 166 -> 293 tokens) and moved `tool_list` not at all.

Owner's decision: make discovery a RAIL STEP, because rails already drive reliably. The stated
limit is that it covers only turns that have a rail.

WHERE IT GOES, AND WHY NOT WHERE IT LOOKS LIKE IT SHOULD. A discovery step over the rail's OWN
step tools would be INERT — `pinned_step_tools` are exempted from the intent gate and
re-advertised every turn, so their schemas are already on the wire and loading them fetches what
the model already has. The place a rail turn genuinely lacks a tool is when its declared one is a
WALL: measured, `plan_propose_spec` returned four identical "not found or not accessible" refusals
across two turns. Until now that went straight to the honest give-up.

THE INVARIANT: "the tool I was told to use does not work" must first become "find the tool that
does" — the platform holds ~267 tools this turn cannot see and a working way to reach them.
Giving up is right eventually; it is wrong as the FIRST response.
"""
from __future__ import annotations

from collections import Counter

from loreweave_agent_control import decide_rail_drive
from loreweave_agent_control.rail import (
    DISCOVERY_TOOL,
    BookState,
    discovery_directive,
    honest_giveup_directive,
)

PLANNING = [
    {"id": "propose", "tool": "plan_propose_spec", "done_when": "plan > 0"},
    {"id": "compile", "tool": "plan_compile", "done_when": "structure_fresh > 0"},
]


def _fixed_probe(state: BookState):
    async def _p(book_id, caller_user_id):
        return state
    return _p


async def _decide(*, turn_succeeded, stuck_tools):
    """The walled-step case: `propose` is the next step and its tool keeps failing identically."""
    return await decide_rail_drive(
        probe_fn=_fixed_probe(BookState(plan=0, structure_fresh=0)),
        rail_specs=[("planning", PLANNING)], book_id="book", user_id="user",
        turn_start_counts={}, turn_succeeded=turn_succeeded,
        async_tools=frozenset(), nudged_out=set(), nudge_counts=Counter(),
        enforcement_strength="enforce", required_nudge_cap=3,
        stuck_tools=frozenset(stuck_tools),
    )


async def test_a_walled_step_drives_discovery_instead_of_giving_up():
    """THE FALSIFIER. Before this, a wall went straight to the honest give-up and the ~267 tools
    off the surface were never reached — the lazy tail existing but never firing."""
    v = await _decide(turn_succeeded=Counter(), stuck_tools={"plan_propose_spec"})
    assert v.should_drive is True
    assert v.giving_up is False, (
        "a wall is not the end of the rail until discovery has been tried once"
    )
    assert DISCOVERY_TOOL in v.directive_text
    assert v.directive_text == discovery_directive(v.step)


async def test_discovery_fires_at_most_once_then_the_give_up_stands():
    """BOUNDED BY CONSTRUCTION. If discovery already succeeded and the step is STILL walled, the
    honest give-up returns. A discovery step that can fire twice is the retry loop it replaces."""
    v = await _decide(
        turn_succeeded=Counter({DISCOVERY_TOOL: 1}), stuck_tools={"plan_propose_spec"},
    )
    assert v.should_drive is True
    assert v.giving_up is True
    assert v.directive_text == honest_giveup_directive(v.step)
    assert DISCOVERY_TOOL not in v.directive_text


async def test_a_healthy_step_is_never_sent_to_discovery():
    """Discovery is the WALL's escape hatch, not the rail's normal mode. A step that has simply
    not run yet must get the ordinary redrive — sending every step through discovery would spend
    a pass of every rail turn on a listing nobody needed."""
    v = await _decide(turn_succeeded=Counter(), stuck_tools=set())
    assert v.should_drive is True
    assert DISCOVERY_TOOL not in v.directive_text
    assert v.step.tool == "plan_propose_spec"


def test_the_directive_forbids_repeating_the_failing_call():
    """The measured failure is four IDENTICAL refusals. A directive that only suggests an
    alternative, without forbidding the repeat, leaves the loop it exists to break."""
    text = discovery_directive(None)
    assert "Do NOT call it again" in text
    assert "SUBSET" in text, (
        "the model must be told the visible tools are not the whole catalogue — that is the "
        "belief which makes it settle for the nearest tool on the surface"
    )


def test_the_directive_still_refuses_to_claim_success():
    """The escape hatch must not become a new way to end a turn dishonestly: if discovery finds
    nothing, the answer is still 'I could not finish that', never a silent success."""
    text = discovery_directive(None)
    assert "do not claim it worked" in text.lower()
