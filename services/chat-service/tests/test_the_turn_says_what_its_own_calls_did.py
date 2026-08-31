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

import inspect
import pathlib

from app.services import stream_service as ss


def _call(tool, outcome, error=None):
    r = {"tool": tool, "call_outcome": outcome}
    if error is not None:
        r["error"] = error
    return r


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
        text = ss._completed_in_this_turn([_call("glossary_propose_entities", "done"),
                                           _call("composition_arc_apply", "deferred")])
        assert "glossary_propose_entities" in text
        assert "composition_arc_apply" not in text, "a PENDING call was reported as completed"

    def test_nothing_is_claimed_when_nothing_completed(self):
        assert ss._completed_in_this_turn([_call("x", "deferred")]) == ""
        assert ss._completed_in_this_turn([]) == ""


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
        sentence registers in the same commit that ships it."""
        fe = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "toolloop" / "fe_runner.py"
        text = fe.read_text(encoding="utf-8")
        assert "Already completed in this turn:" in text
        assert "in this turn did not run:" in text
