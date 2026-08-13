"""D-FJ-17 — the stalled-write nudge must not drag a turn onto a rail the user did not ask about.

🔴 MEASURED LIVE 2026-08-13, session 019ff929, throwaway book 019ff8f5-ae59-71f9-acb9-ad607b363ef7.

The author asked, in plain prose, *"What canon rules have I declared for this book? List them for
me."* That deterministically pinned the `canon-check` rail, whose next step is
`composition_list_canon_rules` — a READ, and one of the 34 tools advertised in BOTH passes of that
turn. The model called nothing and wrote *"I checked the consistency rules for this book, and you
haven't declared any canon rules yet"* while the owning store held one active rule.

Then the guard made it worse. `_pinned_slugs` is `binding + intent`, so the standing mode
binding's rail sorts FIRST, and `_rail_write_step_stalled` returned the first WRITE-tier step it
found: `kg_add_nodes`, the outstanding step of the STALE `vision-to-book` rail (7/9) from an
earlier journey. The directive built from it sent pass 2 to answer THAT instead, and the persisted
message ends:

    …I can help you set them up.I did not make the change. I cannot call `kg_add_nodes`
    because I do not have the `entity_id` for Vela Ostrand…

A paragraph about a character the author had not mentioned, appended to a fabricated answer to the
question they did ask.

A guard that redirects a turn to work the user did not ask about is worse than one that stays
quiet, so when this turn's own words pinned a rail, only that rail may claim the nudge.
"""
import pytest


class _Step:
    def __init__(self, tool):
        self.tool = tool


class _Prog:
    def __init__(self, slug, tool):
        self.slug = slug
        self.next_step = _Step(tool)


# The catalogue shape tool_tier actually reads: `_meta` lives INSIDE `function`.
CATALOG = {
    "kg_add_nodes": {"function": {"_meta": {"tier": "W"}}},
    "composition_list_canon_rules": {"function": {"_meta": {"tier": "R"}}},
    "translation_start_job": {"function": {"_meta": {"tier": "A"}}},
}

# Exactly the turn's rail_progress, in the order `_pinned_slugs` produced: binding rail first.
LIVE_RAILS = [
    _Prog("vision-to-book", "kg_add_nodes"),
    _Prog("canon-check", "composition_list_canon_rules"),
]


class TestTheNudgeStaysOnTheRailTheUserPinned:
    def test_the_LIVE_defect_the_stale_rails_write_is_no_longer_returned(self):
        """THE FALSIFIER. Before the fix this returned 'kg_add_nodes' and the author got an answer
        about Vela Ostrand. The pinned rail's own next step is a read, and this guard is
        deliberately writes-only — so the honest outcome is no nudge at all."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(
            LIVE_RAILS, catalog_index=CATALOG, attempted=set(),
            intent_slugs=frozenset({"canon-check"}),
        ) is None

    def test_the_pinned_rails_OWN_write_step_is_still_caught(self):
        """The fix must narrow WHICH rail may claim the nudge, never disable the guard: when the
        rail the user pinned is itself waiting on a write, that write is still nudged."""
        from app.services.stream_service import _rail_write_step_stalled
        rails = [
            _Prog("vision-to-book", "kg_add_nodes"),
            _Prog("translate-book", "translation_start_job"),
        ]
        assert _rail_write_step_stalled(
            rails, catalog_index=CATALOG, attempted=set(),
            intent_slugs=frozenset({"translate-book"}),
        ) == "translation_start_job"

    def test_with_NO_intent_pin_the_original_behaviour_is_byte_for_byte_unchanged(self):
        """The 2026-08-12 translation case that created this guard had no intent pin, and must
        still fire. A fix that also silenced THAT would trade one silent failure for another."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(
            LIVE_RAILS, catalog_index=CATALOG, attempted=set(),
        ) == "kg_add_nodes"

    def test_an_intent_pin_naming_a_rail_that_is_not_in_progress_nudges_nothing(self):
        """An empty intersection must mean "no nudge", not "fall back to every rail" — falling
        back is exactly the behaviour this defect is made of."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(
            LIVE_RAILS, catalog_index=CATALOG, attempted=set(),
            intent_slugs=frozenset({"entity-triage"}),
        ) is None


class TestTheIntentPinIsActuallyWiredToTheGuard:
    """A guard-level fix that is never threaded to the call site stays green and dead — this loop
    has already shipped that mistake once."""

    @pytest.mark.parametrize("needle", [
        # the selector receives it
        "intent_slugs=rail_intent_slugs,",
        # _stream_with_tools accepts it
        "rail_intent_slugs: frozenset[str] = frozenset(),",
        # _emit_chat_turn forwards it to the tool loop
        "rail_intent_slugs=rail_intent_slugs,",
        # stream_response supplies the value from THIS turn's intent pin
        "rail_intent_slugs=frozenset(_intent_slugs),",
    ])
    def test_the_chain_from_the_user_message_to_the_guard_is_present(self, needle):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert needle in src


class TestATurnThatCalledNothingCanStillBeRescued:
    """D-FJ-18 — the read-side twin, found on the SAME live turn once D-FJ-17 was fixed.

    With the stale-rail hijack gone, the turn was clean — and still wrong: `canon-check` was
    pinned, `composition_list_canon_rules` was advertised, the store held one active rule, and the
    model answered *"I checked the consistency rules for this book, and you haven't declared any
    canon rules yet"* having called nothing at all.

    Nothing could rescue it. `_rail_is_in_flight` required the model to have reached for
    something — `resumed_mid_rail`, a succeeded step tool, or an attempted-and-failed one — and
    the D-FJ-8 narrated-write arm is deliberately writes-only, so a READ step had no arm at all.
    The guard's own docstring already quoted the hole it was closing ("it cannot rescue a model
    that cannot start"); this is the rest of it.

    A fabricated absence is worse than a fabricated write in one respect: the author is told their
    own data is not there, and so has no reason to go and look.
    """

    def test_the_LIVE_defect_a_zero_call_turn_on_a_rail_the_user_asked_for_is_in_flight(self):
        """THE FALSIFIER. False before the fix — the step-runner logged
        `SKIPPED — held by: in_flight` and the author got the fabricated 'no canon rules'."""
        from app.services.stream_service import _rail_is_in_flight
        assert _rail_is_in_flight(
            resumed_mid_rail=False, step_tools_succeeded=[], step_tools_attempted=[],
            asked_for_it_and_called_nothing=True,
        ) is True

    def test_an_ordinary_conversation_that_pinned_no_rail_is_still_not_in_flight(self):
        """The opening must be the narrowest possible one: no pin ⇒ no drive, exactly as before.
        A widened gate that fires on any quiet turn would re-steer ordinary chat."""
        from app.services.stream_service import _rail_is_in_flight
        assert _rail_is_in_flight(
            resumed_mid_rail=False, step_tools_succeeded=[], step_tools_attempted=[],
            asked_for_it_and_called_nothing=False,
        ) is False

    def test_the_three_original_clauses_are_untouched(self):
        from app.services.stream_service import _rail_is_in_flight
        assert _rail_is_in_flight(
            resumed_mid_rail=True, step_tools_succeeded=[], step_tools_attempted=[]) is True
        assert _rail_is_in_flight(
            resumed_mid_rail=False, step_tools_succeeded=["kg_build"],
            step_tools_attempted=[]) is True
        assert _rail_is_in_flight(
            resumed_mid_rail=False, step_tools_succeeded=[],
            step_tools_attempted=["kg_build"]) is True

    def test_the_new_clause_is_wired_AND_the_drive_is_confined_to_the_pinned_rail(self):
        """Opening the gate without confining the drive would reproduce D-FJ-17 one layer down —
        the turn would be re-steered onto `vision-to-book`'s outstanding kg_add_nodes instead of
        the rail the author actually asked about."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "asked_for_it_and_called_nothing=_asked_and_called_nothing," in src
        assert "_asked_and_called_nothing = bool(rail_intent_slugs) and not turn_attempted" in src
        assert "spec for spec in (rail_specs or ()) if spec[0] in rail_intent_slugs" in src
        # the confined list, not the raw one, is what the decision actually receives
        assert "rail_specs=_drive_specs, book_id=rail_book_id, user_id=user_id," in src


class TestTheStepRunnerDrivesOnlyTheRailTheUserAskedFor:
    """D-FJ-17, step-runner arm — found by re-running the SAME live turn after the first two fixes.

    The pinned `canon-check` step finally ran and answered the question correctly. Then the turn
    kept going: with a step tool now hit, the zero-call confinement lifted, the full spec list came
    back, and redrives 2, 3 and 4 all went to `vision-to-book → kg_add_nodes` — the rail the
    standing mode binding pinned, not the author. The reply the author actually received ended:

        …**Magic always costs lifespan** (Sat khi luon tieu hao tuoi tho)I cannot add the nodes
        to the knowledge graph yet. To do this, I first need to save the characters…

    They asked one question about canon rules and got two paragraphs about knowledge-graph nodes
    they never mentioned. Confining only the ENTRY was not enough; the confinement has to hold for
    the whole turn.
    """

    def test_the_confinement_is_keyed_on_the_pin_alone_not_on_the_zero_call_entry(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "                if rail_intent_slugs:" in src
        assert "spec for spec in (rail_specs or ()) if spec[0] in rail_intent_slugs" in src
        # THE FALSIFIER for this arm: the confinement must NOT be re-gated on the zero-call
        # entry condition, which is what let redrives 2-4 escape to the stale rail.
        assert "if _asked_and_called_nothing and not (" not in src


class TestTwoPassesAreNotWeldedIntoOneSentence:
    """D-FJ-19 — a multi-pass turn persists ONE assistant message, and the passes were joined
    with nothing at all. Measured live 2026-08-13, three separate turns:

        …I can help you set them up.I did not make the change…
        …I can help you set them up.I checked your consistency rules…
        …(Sat khi luon tieu hao tuoi tho)I cannot add the nodes…

    Every rail re-drive produces a multi-pass turn, so this is the normal shape of a driven
    turn, not a rare edge case — and to a reader the seam falls mid-sentence.

    🔴 THE FIRST FIX WAS TOO BROAD AND THE SUITE CAUGHT IT. Separating every later pass also
    split an ordinary tool round-trip, where the model streams "Let me check.", calls a tool,
    and continues " Kai is a knight." — one sentence across two passes, already joined
    correctly (test_one_tool_pass_then_text_pass, test_call_dispatches_locally_with_session_
    scope). The distinguishing signal is not "a later pass" but "a pass that was handed a NEW
    synthetic instruction": a rail re-drive or a narrated-write nudge appends a role=user
    directive, and the prose that answers it is a separate answer. Tool results are not.
    """

    def test_the_seam_is_gated_on_a_preceding_DIRECTIVE_not_merely_a_later_pass(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "                            and _directive_before_this_pass" in src
        assert '_delta = "' + chr(92) + 'n' + chr(92) + 'n" + _delta.lstrip()' in src
        # both injection sites must arm it, or the seam is dead for one of them
        assert src.count("_directive_before_this_pass = True  # D-FJ-19") == 2

    def test_the_seam_rule_itself(self):
        """The rule as a pure function of its inputs, so the intent is pinned independently of
        where it lives."""
        def needs_break(prior, delta, first_of_pass, after_directive):
            return bool(
                first_of_pass and after_directive and delta.strip() and prior.strip()
                and not prior.endswith(chr(10))
            )
        # the live case — a rail re-drive handed the model a new instruction
        assert needs_break("…set them up.", "I checked your rules", True, True) is True
        # 🔴 the over-broad first fix: an ordinary tool round-trip must stay one sentence
        assert needs_break("Let me check.", " Kai is a knight.", True, False) is False
        # a single-pass turn is untouched
        assert needs_break("", "I checked", True, True) is False
        # mid-pass deltas are untouched
        assert needs_break("…set them up.", "I checked", False, True) is False
        # prose that already ends in a break does not get another
        assert needs_break("…set them up." + chr(10), "I checked", True, True) is False
        # a whitespace-only delta is not the start of a new answer
        assert needs_break("…set them up.", "  ", True, True) is False
