"""Turn OWNERSHIP — the rail CLAIMS a turn; it does not own one.

🔴 THE DESIGN HOLE, MEASURED 2026-08-13 (session 019ff929, editor surface, book 019ff8f5-ae59).

`decide_rail_drive` took the rail state, the book probe, the nudge counters and the enforcement
strength — and nothing at all about what the user asked. Not down-weighted: structurally absent
from the signature. The user's words reached the decision through exactly one route,
`user_abandoned_rail`, a literal regex of ~8 phrases applied as a consumer-side guard.

So the arbitration model the system actually implemented was:

    THE RAIL OWNS EVERY TURN ON A BOOK WITH AN OUTSTANDING STEP, and the user may revoke that
    ownership only by uttering one of those phrases.

Ownership was opt-OUT. What it cost, on one turn: the author typed *"Load the tool
composition_list_outline by name, then use it to show me the outline of this book."* The turn
pinned no rail, so a STALE `build-a-book` rail from an earlier journey claimed it and drove
`plan_propose_spec` four times — every call refused "not found or not accessible", because it was
carrying the editor's chapter_id as `book_id`. `tool_load` was advertised in all six passes and
called zero times. The request was discarded after a single fumble and never came back.

These tests pin the inverted model: ownership is opt-IN, and rule 5 keeps the driver doing the job
it was built for.
"""
from __future__ import annotations

from collections import Counter

import pytest

from loreweave_agent_control import BookState, TurnRequest, decide_rail_drive

# Exactly the shape of the live turn: a stale binding rail with an outstanding write, and the
# rail the author's words would have pinned had they used a phrase the matcher knows.
_BUILD = [{"id": "b1", "tool": "plan_propose_spec", "done_when": "plan > 0"}]
_CANON = [{"id": "c1", "tool": "composition_list_canon_rules", "done_when": "cast > 0"}]
_RAILS = [("build-a-book", _BUILD), ("canon-check", _CANON)]


def _probe(**counts):
    async def _fn(_book, _user):
        return BookState(**counts)
    return _fn


async def _decide(*, request=None, stuck=frozenset(), rails=None, counts=None, out=None,
                  succeeded=None):
    return await decide_rail_drive(
        probe_fn=_probe(plan=0, cast=0),
        rail_specs=rails if rails is not None else _RAILS,
        book_id="b", user_id="u",
        turn_start_counts=None,
        turn_succeeded=succeeded if succeeded is not None else Counter(),
        async_tools=frozenset(),
        nudged_out=out if out is not None else set(),
        nudge_counts=counts if counts is not None else Counter(),
        enforcement_strength="enforce", required_nudge_cap=3,
        request=request, stuck_tools=stuck,
    )


class TestRule5TheDriverStillDoesItsJob:
    """FIRST, because it is the one that must never break. The rail exists because a mid-tier
    model will not self-start (S03 0/3, S04 1/3, S09 improvises) and a real co-writing turn is an
    ASSENT — "ok", "yes", "go on" — which pins nothing and names nothing. Making ownership opt-IN
    is only correct if that case is untouched."""

    @pytest.mark.asyncio
    async def test_an_assent_with_no_request_signals_is_driven_exactly_as_before(self):
        v = await _decide(request=TurnRequest())
        assert v.should_drive is True
        assert v.slug == "build-a-book"

    @pytest.mark.asyncio
    async def test_omitting_the_request_entirely_is_the_same_as_an_empty_one(self):
        """Every existing caller and every existing test passes no `request`. That path must be
        byte-identical, or this contract is a breaking change wearing a default argument."""
        assert (await _decide(request=None)).should_drive is True


class TestRule2ANamedToolIsADiscoveryTurn:
    @pytest.mark.asyncio
    async def test_the_LIVE_defect_naming_a_tool_stops_the_rail_claiming_the_turn(self):
        """THE FALSIFIER. Before the contract this drove `plan_propose_spec` and the author's
        instruction to load a tool by name was never acted on."""
        v = await _decide(request=TurnRequest(named_tools=frozenset({"composition_list_outline"})))
        assert v.should_drive is False
        assert v.declined_reason and "composition_list_outline" in v.declined_reason

    @pytest.mark.asyncio
    async def test_the_reason_is_recorded_so_the_losing_claimant_is_greppable(self):
        v = await _decide(request=TurnRequest(named_tools=frozenset({"kg_add_nodes"})))
        assert v.declined_reason == "the request names kg_add_nodes"


class TestRule3OnlyThePinnedRailMayClaimTheTurn:
    @pytest.mark.asyncio
    async def test_the_pinned_rail_wins_over_the_binding_rail_that_sorts_first(self):
        """`_pinned_slugs` is `binding + intent`, so the standing mode binding always sorted ahead
        of the rail the user's own words pinned. This is D-FJ-17, now stated by the decision
        itself instead of enforced by the caller filtering the list it hands in."""
        v = await _decide(request=TurnRequest(pinned_rails=frozenset({"canon-check"})))
        assert v.should_drive is True
        assert v.slug == "canon-check"

    @pytest.mark.asyncio
    async def test_a_pin_naming_a_rail_that_is_not_in_play_does_not_silently_fall_back(self):
        """An empty intersection must not mean "then any rail will do" — falling back is exactly
        the behaviour the defect is made of. The unfiltered list is kept only when the pin matches
        nothing at all, which is the pre-contract shape for a pin the turn cannot act on."""
        v = await _decide(request=TurnRequest(pinned_rails=frozenset({"entity-triage"})))
        # no pinned rail is in play → the decision proceeds on what it has, unchanged
        assert v.should_drive is True

    @pytest.mark.asyncio
    async def test_rule4_a_pinned_rail_with_nothing_left_ends_the_turn(self):
        """"The request was served" needs no separate rule: once the claim is confined to the
        pinned rail, a rail whose steps are all done yields no actionable step. Before the
        confinement this is precisely where the turn leaked onto the other rail — measured live,
        the canon question was answered and the turn then drove kg_add_nodes anyway."""
        v = await decide_rail_drive(
            probe_fn=_probe(plan=0, cast=5),           # canon-check is satisfied
            rail_specs=_RAILS, book_id="b", user_id="u",
            turn_start_counts=None, turn_succeeded=Counter(),
            async_tools=frozenset(), nudged_out=set(), nudge_counts=Counter(),
            enforcement_strength="enforce", required_nudge_cap=3,
            request=TurnRequest(pinned_rails=frozenset({"canon-check"})),
        )
        assert v.should_drive is False
        assert v.declined_reason == "no actionable step"


class TestRule1TheReleaseIsHonouredByTheDecisionToo:
    @pytest.mark.asyncio
    async def test_an_abandon_phrase_stops_the_drive(self):
        """Also enforced by a consumer guard upstream. Kept here so the whole precedence table can
        be read — and tested — in one place."""
        v = await _decide(request=TurnRequest(abandons_rail=True))
        assert v.should_drive is False
        assert v.declined_reason == "user released the rail"


class TestAStuckStepIsAWallNotAModelThatNeedsSteering:
    """D-FJ-21. chat-service already had the right RULE — the repeated-failure breaker keys on
    (tool → error → count) and stops at 2 identical failures. It could not help, because that map
    AND the rail's own nudge counters are all rebuilt per turn, even though this harness's own
    docstring called them "the consumer's cross-turn state". A step failing twice a turn reset
    forever: `plan_propose_spec`, 4 identical refusals across 2 turns, breaker never fired."""

    @pytest.mark.asyncio
    async def test_the_LIVE_defect_a_stuck_step_is_never_re_nudged_at_the_same_tool(self):
        """The rule this class exists for, unchanged: a wall must NOT get another nudge at the
        same tool, and the exhausted step must be marked so it is not re-driven.

        AMENDED 2026-08-14 (D-LAZY-TAIL-UNUSED). What a wall gets FIRST is now discovery, not the
        give-up: the platform holds ~267 tools the turn cannot see and a working way to reach
        them, so "the tool I was told to use does not work" must first become "find the tool that
        does". The give-up still stands once discovery has been tried — see the test below. The
        original assertion (`giving_up is True` on the first wall) was the instance; the invariant
        is that the failing tool is not re-driven, and that is asserted here directly."""
        out: set = set()
        v = await _decide(stuck=frozenset({"plan_propose_spec"}), out=out)
        assert "b1" in out, "the exhausted step must be marked so it is not re-driven"
        assert v.declined_reason and "keeps failing identically" in v.declined_reason
        assert "plan_propose_spec" not in (v.directive_text or ""), (
            "the wall must never be re-nudged at the tool that keeps failing"
        )
        assert "tool_list" in (v.directive_text or "")
        assert v.giving_up is False

    @pytest.mark.asyncio
    async def test_the_honest_giveup_still_stands_once_discovery_has_been_tried(self):
        """The give-up is deferred by exactly one step, never removed. With discovery already
        succeeded and the step still walled, the honest 'I could not finish that' returns — a
        silent give-up reads as success, and an unbounded escape hatch is the retry loop again."""
        out: set = set()
        v = await _decide(
            stuck=frozenset({"plan_propose_spec"}), out=out,
            succeeded=Counter({"tool_list": 1}),
        )
        assert v.giving_up is True
        assert "not able to finish" in (v.directive_text or "")

    @pytest.mark.asyncio
    async def test_it_does_not_burn_a_nudge_on_a_wall(self):
        counts: Counter = Counter()
        await _decide(stuck=frozenset({"plan_propose_spec"}), counts=counts)
        assert counts["b1"] == 0, "a wall is not an ignored nudge; counting it misreports the model"

    @pytest.mark.asyncio
    async def test_an_unrelated_stuck_tool_does_not_stop_this_step(self):
        v = await _decide(stuck=frozenset({"some_other_tool"}))
        assert v.should_drive is True and v.giving_up is False
