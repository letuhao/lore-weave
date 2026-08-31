"""A turn's reply may not be the only account of what the turn did.

    THE INVARIANT. When a turn holds a call that did NOT happen, the server states that fact in
    the message the author reads, from the turn's own record. The model's recollection is not the
    only account, and the server never states an outcome it did not observe.

OWNER, 2026-08-31: "b -> is it a defect and we need to fix by return brief or something?"

IT IS A DEFECT, trigger-scoped both ways:

    the call REFUSED and the reply says it succeeded   26 of 307 turns that hit a refusal  8.5%
    the call LANDED  and the reply says it failed      28 of 581 carded writes             4.8%

The pooled 1.3-1.7% the question was filed with averaged both directions over ~1,300 runs that
could not trigger either — a run where nothing was refused cannot claim past a refusal.

🔴 THE BRIEF IS COMPOSED, NOT INFERRED. Every call record already carries a typed `call_outcome`
(done / failed / refused / deferred), written by `instrument`; the brief reads it. A second
implementation of "did this call fail?" would be a second rule, and this loop has already paid
for one of those — an inline re-derivation of a shipped detector returned NEGATIVE deltas.

WHAT IS DELIBERATELY NOT BUILT HERE: a brief on a turn where everything succeeded. There is no
refusal to overstate, and a line appended to every reply in the product is a voice change nobody
asked for. The gate is a non-`done` call, which is precisely the 8.5%'s trigger population.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.services import stream_service as ss


def _call(tool, outcome, error=None, wrote=False, created=None):
    r = {"tool": tool, "call_outcome": outcome}
    if error is not None:
        r["error"] = error
    if created is not None:
        r["result"] = {"created": created}
    if wrote:
        # The H16 activity block a Tier-A auto-write attaches - the record's own marker that
        # something CHANGED, as opposed to a call that merely succeeded.
        r["activity"] = {"kind": "write", "undo": True}
    return r


def _registered_markers() -> tuple:
    """`fe_runner._SERVER_APPENDED_LINES`, read from the file rather than imported — the harness
    module pulls in the whole runner stack, and this test needs one tuple of strings.

    🔴 IT RETURNS THE MARKERS AND THE TEST APPLIES THEM IN THE DIRECTION THE HARNESS DOES:
    `marker in sentence`, because the detector's own line is `text.replace(_line, " ")`. My first
    version generated every 3+ word run of the emitted sentence and asked whether any appeared in
    fe_runner.py — which let the generic fragment "in this turn:" match the OTHER marker, so the
    guard stayed green while the shipped wording drifted from "completed" to "noted". A guard
    that matches on a fragment common to both sentences is not identifying either.
    """
    src = (pathlib.Path(__file__).resolve().parents[3]
           / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    i = src.index("_SERVER_APPENDED_LINES = (")
    block = src[i + len("_SERVER_APPENDED_LINES = "):]
    depth, end = 0, 0
    for n, ch in enumerate(block):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = n + 1
                break
    lines = [ln.split("#")[0] for ln in block[:end].splitlines()]
    return ast.literal_eval("\n".join(lines))


class TestTheBriefSaysOnlyWhatHappened:
    def test_a_refused_call_is_named_with_its_own_reason(self):
        brief = ss._turn_brief([_call("plan_validate", "refused", "plan not found")])
        assert "plan_validate" in brief
        assert "plan not found" in brief
        assert "did not run" in brief

    def test_a_turn_where_everything_worked_gets_no_brief(self):
        """The silence is the design, not an oversight: nothing to correct, nothing appended."""
        assert ss._turn_brief([_call("glossary_search", "done")]) == ""
        assert ss._turn_brief([]) == ""
        assert ss._turn_brief(None) == ""

    def test_a_deferred_call_is_not_reported_as_a_failure(self):
        """`deferred` is the pending card — a SUCCESS state (asking the user is not a stall), and
        the suspend line already speaks for it. Counting it here would tell the author their
        confirm card failed."""
        assert ss._turn_brief([_call("glossary_propose_entities", "deferred")]) == ""

    def test_the_error_text_goes_through_the_shipped_sanitiser(self):
        """REUSE, NOT RE-IMPLEMENT: an internal trace must never be pasted at an author, and the
        rule for that already exists and is used by the silent-turn fallback."""
        src = inspect.getsource(ss._turn_brief)
        assert "_client_safe_error" in src

    def test_a_long_turn_is_summarised_rather_than_listed(self):
        brief = ss._turn_brief([_call(f"tool_{i}", "failed", "nope") for i in range(7)])
        assert "and 4 more" in brief
        assert brief.count("tool_") == ss._BRIEF_MAX_NAMED

    def test_the_count_in_the_lead_matches_the_calls(self):
        one = ss._turn_brief([_call("a", "failed", "x")])
        two = ss._turn_brief([_call("a", "failed", "x"), _call("b", "refused", "y")])
        assert "One action" in one
        assert "2 actions" in two


class TestTheCardNamesWhatAlreadyLanded:
    def test_a_write_that_landed_is_named_beside_the_card(self):
        """DQ-T73's cheap half. "Nothing has been saved yet" is true of the CARD and false of a
        write this turn already made -- which is the 4.8% direction."""
        text = ss._completed_in_this_turn([_call("glossary_propose_entities", "done", wrote=True),
                                           _call("composition_arc_apply", "deferred")])
        assert "glossary_propose_entities" in text
        assert "composition_arc_apply" not in text, "a PENDING call was reported as completed"

    def test_a_successful_READ_is_not_reported_as_something_that_happened(self):
        """🔴 THE FIRST VERSION SHIPPED SAYING IT WAS, and five live carded turns read
        "Already completed in this turn: composition_arc_template_list" -- a LIST. Telling an
        author a read changed their book is a smaller copy of the defect this exists to remove.

        `done` means THE CALL SUCCEEDED. The record's marker for a landed write is the H16
        `activity` block: 591 of 7,818 done calls carry one over 20 days, and zero failed,
        refused or deferred calls do."""
        assert ss._completed_in_this_turn([_call("composition_arc_template_list", "done")]) == ""
        assert ss._completed_in_this_turn([_call("glossary_search", "done"),
                                           _call("composition_get_work", "done")]) == ""

    def test_a_create_or_get_that_found_it_already_there_is_not_an_application(self):
        """🔴 THE SECOND OVERSTATEMENT, caught live. A real carded turn read "Already applied in
        this turn: kg_project_create" while knowledge_projects was rows:1 before AND after with
        the same timestamp -- the call returned `created: false` and still carried an activity
        block, because that block means "a Tier-A write tool ran", not "the world changed".

        The platform already knew: the idempotent-no-op-write breaker keys on this exact field
        and its comment says COMMITTED NOTHING in those words."""
        assert ss._completed_in_this_turn(
            [_call("kg_project_create", "done", wrote=True, created=False)]) == ""
        # ABSENT is a real write -- most write results carry no `created` field at all, and only
        # an explicit False is the no-op. Same discipline as the breaker.
        assert "kg_add_nodes" in ss._completed_in_this_turn(
            [_call("kg_add_nodes", "done", wrote=True)])
        assert "glossary_propose_entities" in ss._completed_in_this_turn(
            [_call("glossary_propose_entities", "done", wrote=True, created=True)])

    def test_nothing_is_claimed_when_nothing_completed(self):
        assert ss._completed_in_this_turn([_call("x", "deferred")]) == ""
        assert ss._completed_in_this_turn([]) == ""


class TestItReadsAnUNSTAMPEDCall:
    """🔴 THE DEFECT THAT SURVIVED TWO CORRECT-LOOKING FIXES, found by logging inside the running
    container. A carded turn's history AT THE MOMENT OF SUSPENSION read

        [('glossary_book_ontology_read', 'done', activity=False),
         ('glossary_list_system_standards', None,  activity=False),
         ('glossary_propose_entities',     None,  activity=True )]

    -- the write that had just landed carried NO `call_outcome`. It gets one later, when
    stamp_tool_call infers it, so the PERSISTED record shows `done` and every check against the
    store agreed the field was there. Driving the container's own helper on that stored record
    returned the right sentence while the live turn produced nothing: the record is not the
    runtime.

    Measured live before this: 5 of 5 turns wrote glossary_entities, carded, and named nothing.
    """

    def test_a_landed_write_is_named_even_before_it_is_stamped(self):
        unstamped = {"tool": "glossary_propose_entities", "ok": True,
                     "activity": {"kind": "write"}}
        assert "glossary_propose_entities" in ss._completed_in_this_turn([unstamped])

    def test_an_unstamped_failure_still_reaches_the_brief(self):
        assert "plan_validate" in ss._turn_brief(
            [{"tool": "plan_validate", "ok": False, "error": "not found"}])

    def test_the_rule_has_one_home(self):
        """Both readers ask `instrument`, and `stamp_tool_call` asks the same function -- so a
        change to what 'succeeded' means cannot land in one of the three."""
        import inspect as _i
        from app.services import instrument as _ins
        src = pathlib.Path(ss.__file__).read_text(encoding="utf-8")
        assert src.count("instrument.effective_call_outcome(tc)") == 2
        # The inference lives in `ensure_tool_call_instrumented`, which stamp_tool_call
        # funnels into -- named explicitly rather than guessed, because asserting it against
        # the wrong function is how a guard passes while proving nothing.
        assert "effective_call_outcome(chunk)" in _i.getsource(
            _ins.ensure_tool_call_instrumented)


class TestBothSitesActuallyAppendIt:
    """GUARD THE CALL SITE. A helper returning the right string is worth nothing if the two
    paths that end a turn never call it -- and those two paths are the whole point: the carded
    finish carries one direction of this defect and the non-carded finish carries the other,
    which is 1.8x larger and reached by no existing mechanism."""

    def test_the_non_carded_finish_appends_the_brief(self):
        src = pathlib.Path(ss.__file__).read_text(encoding="utf-8")
        assert "_brief = _turn_brief(tool_calls_history)" in src
        # It must land INSIDE the assistant message: after close_message() the FE renders it
        # outside the frame, which is a silent turn with extra steps.
        body = src[src.index("_brief = _turn_brief(tool_calls_history)"):]
        assert body.index("full_content.append(_brief)") < body.index("emitter.close_message()")

    def test_the_carded_finish_names_both_halves(self):
        src = pathlib.Path(ss.__file__).read_text(encoding="utf-8")
        i = src.index("_suspend_text = (")
        window = src[i:i + 400]
        assert "_NOTHING_SAVED_YET_LINE" in window
        assert "_completed_in_this_turn(tool_calls_history)" in window
        assert "_turn_brief(tool_calls_history)" in window

    def test_the_harness_knows_these_are_the_servers_words(self):
        """The line that shipped 2026-08-28 was read as the MODEL's claim by this loop's own
        detector and produced a 13-run phantom regression at p = 0.0000. A new server-authored
        sentence registers in the same commit that ships it.

        🔴 CROSS-DERIVED FROM WHAT THE SERVER ACTUALLY EMITS, not typed a second time. This test
        first asserted the literal "Already completed in this turn:" in both places and stayed
        GREEN while the shipped wording changed to "applied" — a guard comparing my copy of a
        string against my other copy of the same string proves only that I typed it twice. It now
        generates the sentences and looks for THEM.
        """
        markers = _registered_markers()
        assert len(markers) >= 4, markers
        emitted = [
            ss._completed_in_this_turn([_call("kg_add_nodes", "done", wrote=True)]),
            ss._turn_brief([_call("kg_add_nodes", "failed", "nope")]),
        ]
        for sentence in emitted:
            assert any(m in sentence for m in markers), (
                f"the server emits {sentence.strip()!r} and NO registered marker is a substring "
                "of it — the detectors strip by `text.replace(marker, ' ')`, so this loop will "
                "read the platform's own words as the model's claim"
            )


class TestACardIsNotAWrite:
    """🔴 THE SENTENCE CORROBORATED A CLAIM THAT WAS FALSE, WHICH IS THE DEFECT THIS WHOLE
    MECHANISM EXISTS TO REMOVE — shipped by me, caught live the same day.

    Measured 2026-08-31 (c-planapply2, K=5, serial, real provider): `plan_bootstrap_apply`
    returned a `confirm_token` and the record stamped it

        call_outcome = "done",  activity = {"summary": "Did plan_bootstrap_apply",
                                            "undo": {"available": false}}

    so the brief closed the reply with "Already applied in this turn: plan_bootstrap_apply."
    The store had NO chapters on any of the five runs, and the model's own "The chapters have
    been successfully created!" was then backed by the server's own line.

    `done` means THE CALL RETURNED. It never meant the world changed — call-outcome and
    turn-outcome are different vocabularies, and a token minted for a human to click is by
    construction a write that has not landed.
    """

    def test_a_confirm_token_result_committed_nothing(self):
        tc = {"tool": "plan_bootstrap_apply", "call_outcome": "done",
              "activity": {"summary": "Did plan_bootstrap_apply"},
              "result": {"book_id": "b", "proposal_id": "p", "confirm_token": "eyJ…",
                         "new_chapters_count": 4}}
        assert ss._committed_nothing(tc)

    def test_the_ENVELOPED_shape_is_caught_too(self):
        """The wire shape is {"ok": true, "result": {...}}; the stored chunk flattens it. Both
        reach this predicate, so both must be judged the same."""
        tc = {"tool": "plan_bootstrap_apply", "call_outcome": "done",
              "activity": {"summary": "Did it"},
              "result": {"ok": True, "result": {"confirm_token": "eyJ…"}}}
        assert ss._committed_nothing(tc)

    def test_the_brief_does_NOT_name_a_carded_write(self):
        """The end-to-end shape, at the function the author's sentence comes from."""
        history = [{"tool": "plan_bootstrap_apply", "call_outcome": "done",
                    "activity": {"summary": "Did plan_bootstrap_apply"},
                    "result": {"confirm_token": "eyJ…", "new_chapters_count": 4}}]
        assert ss._completed_in_this_turn(history) == "", (
            "the turn named a carded write as applied — the author is told their book changed "
            "while the card is still waiting for a click")

    def test_a_REAL_write_is_still_named(self):
        """The correction must not silence the mechanism it is correcting: a genuine landed
        write still has to be reported, or the original defect returns by the back door."""
        history = [{"tool": "kg_add_nodes", "call_outcome": "done",
                    "activity": {"summary": "Added 3 nodes"},
                    "result": {"added": 3}}]
        assert "kg_add_nodes" in ss._completed_in_this_turn(history)

    def test_a_propose_that_really_wrote_is_still_named(self):
        """A proposal row IS a write — plan_bootstrap_propose persisted a row in the same batch
        (plan_bootstrap_proposal 0 -> 1 rows). Only a confirm_token means 'not yet'."""
        history = [{"tool": "plan_bootstrap_propose", "call_outcome": "done",
                    "activity": {"summary": "Proposed"},
                    "result": {"status": "pending", "proposal_id": "01a0…"}}]
        assert "plan_bootstrap_propose" in ss._completed_in_this_turn(history)
