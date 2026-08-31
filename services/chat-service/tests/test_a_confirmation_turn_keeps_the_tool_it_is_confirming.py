"""A two-turn journey must not lose its tool on the turn the action is due.

    THE INVARIANT. When this turn's text answers NOTHING and the previous assistant turn left a
    concrete pending action, R1 also considers the earlier user request — additively.

OWNER RULING 2026-08-31, DQ-T68 (a): "R1 reconsiders the prior USER turn only when the current
turn's answerable set is EMPTY and the previous assistant turn left a CONCRETE pending action —
a minted card, or a surfaced-but-not-called tool. That is a structural signal, not a guess about
conversational topic drift."

🔴 THE TURN IS EMPTY-HANDED BY CONSTRUCTION. Run through the shipped matcher, "Yes, go ahead and
do it.", "Yes, please create them.", "ok", "Yes", "Go ahead", "Do it" and "Confirm" each return
ZERO answerable tools. Measured on plan_bootstrap_apply with its supplier and precondition BOTH
already fixed, so nothing else was in the way: surfaced 0/5, called 0/5 on the confirmation turn.

WHAT THE MEASUREMENT SAYS, including the part that does not flatter it — over 232
bare-affirmative turns in the live store, 192 empty-handed. THE SHIPPED VARIANT IS THE GATED ONE,
so its pair is the one to quote: recall 113/192 = 59%, precision 13/91 = 14%. The ungated form
would reach 82% recall at 13%, and an earlier version of this file quoted THAT 82% beside the
gated mechanism — the generous half of a trade-off whose strict side was already chosen.

The oracle is weak in a known direction, so 14% is a floor: `jobs_get` (a status poll) is 28% of
the miss mass, alongside ontology reads and standards lists — how the model DOES the work, not
the tool that IS the work. On the three instances this defect names, the look-back is 3 of 3.

R1 IS ADDITIVE, which is why 14% is not a veto: recovered tools go ON the wire beside the hot
set. Nothing is removed, no call is forced, and a miss costs context rather than correctness.
"""
from __future__ import annotations

import inspect

from app.services import stream_service as ss
from app.services.stream_service import prior_request_for_lookback as lookback

CARDED = [{"tool": "plan_bootstrap_apply", "call_outcome": "deferred"}]
DONE = [{"tool": "plan_bootstrap_propose", "call_outcome": "done"}]
MSGS = [{"role": "user", "content": "Create the chapters — make the plan real for this book."},
        {"role": "assistant", "content": "Here is the plan…"},
        {"role": "user", "content": "Yes, please create them."}]


class TestItFiresOnlyOnTheStructuralSignal:
    def test_a_pending_card_opens_the_lookback(self):
        assert "make the plan real" in lookback(MSGS, CARDED, [])

    def test_a_surfaced_but_uncalled_tool_opens_it(self):
        """🔴 THE REAL SHAPE, AND ASSUMING OTHERWISE BROKE EVERY TURN. `advertised_tools` is a
        list of PER-PASS OBJECTS — [{"pass": 1, "count": 58, "names": [...]}] — not a list of
        names. `set()` over it raised TypeError: unhashable type: 'dict' on every turn, and the
        batch meant to prove this fix returned 5 of 5 no_output_timeout. This test now feeds the
        shape the column actually holds."""
        adv = [{"pass": 1, "count": 2, "names": ["plan_bootstrap_propose", "plan_bootstrap_apply"]}]
        assert "make the plan real" in lookback(MSGS, DONE, adv)

    def test_the_per_pass_shape_does_not_raise(self):
        """The crash was a TypeError, not a wrong answer — so the guard asserts it RUNS."""
        adv = [{"pass": 1, "names": ["a"]}, {"pass": 2, "names": ["b"]}]
        assert isinstance(lookback(MSGS, DONE, adv), str)

    def test_a_flat_list_of_names_is_tolerated(self):
        """Should the column ever simplify, the gate must not silently stop opening."""
        assert "make the plan real" in lookback(MSGS, DONE, ["plan_bootstrap_apply"])

    def test_a_finished_turn_does_NOT(self):
        """Nothing pending — the affirmative is not confirming an action, and guessing that it
        is would be the topic-drift guess the ruling rules out."""
        adv = [{"pass": 1, "count": 1, "names": ["plan_bootstrap_propose"]}]
        assert lookback(MSGS, DONE, adv) == ""

    def test_no_prior_turn_at_all_is_inert(self):
        assert lookback([{"role": "user", "content": "Yes"}], CARDED, []) == ""
        assert lookback(None, CARDED, []) == ""
        assert lookback([], CARDED, []) == ""

    def test_it_returns_the_PREVIOUS_user_message_not_this_one(self):
        got = lookback(MSGS, CARDED, [])
        assert "Yes, please create them" not in got, (
            "it returned the confirmation itself — which answers nothing, so the look-back "
            "would be a no-op that looks like it fired")


class TestTheChokepointConsultsItLast:
    def test_it_is_only_used_when_this_turn_answers_NOTHING(self):
        src = inspect.getsource(ss._advertise_discovery_tools)
        assert "if not _answerable and prior_request_text:" in src, (
            "the look-back is not gated on the current turn being empty-handed — it would "
            "override a request that already matched")

    def test_the_recovery_is_ADDITIVE_not_a_replacement_of_the_hot_set(self):
        """R1 puts tools ON the wire; it removes nothing. A look-back that dropped anything
        would trade a surfacing defect for a worse one."""
        src = inspect.getsource(ss._advertise_discovery_tools)
        i = src.index("_from_lookback")
        window = src[i:i + 800]
        assert "discard" not in window and "remove" not in window

    def test_it_is_logged(self):
        """R1's own history: the guarantee ran on every pass and logged nothing, and two
        measurements could not tell a rescue that declined from a stage that dropped it."""
        src = inspect.getsource(ss._advertise_discovery_tools)
        assert "R1 look-back" in src

    def test_the_caller_passes_it(self):
        """GUARD THE CALL SITE. A helper returning the right text is worth nothing if the turn
        never hands it over."""
        src = ss.pathlib.Path(ss.__file__).read_text(encoding="utf-8") \
            if hasattr(ss, "pathlib") else open(ss.__file__, encoding="utf-8").read()
        assert "prior_request_text=prior_request_for_lookback(" in src


class TestTheGateIsNarrowingNotPrecision:
    def test_the_measurement_is_recorded_beside_the_mechanism(self):
        """🔴 THE RULING'S GATE DOES NOT IMPROVE PRECISION and the code says so. It fires 113
        times instead of 157 at the SAME 14%, and the card-only form fires 10 and hits none. It
        is kept because it spends less context, not because it is more accurate — a later reader
        must not infer the stronger claim."""
        doc = lookback.__doc__ or ""
        assert "narrowing, not precision" in doc.lower() or "NARROWING, NOT PRECISION" in doc

    def test_the_docstring_quotes_the_recall_of_the_variant_THAT_SHIPS(self):
        """🔴 THE ERROR THIS GUARD EXISTS FOR, and it was mine. The docstring quoted 82% recall
        — the UNGATED figure — beside a mechanism that ships the gate, whose recall is 59%. A gate
        exists to fire less; pairing its precision with the ungated recall advertises a
        trade-off's generous half only. Whatever the numbers become, the recall quoted must be
        the SHIPPED variant's."""
        doc = lookback.__doc__ or ""
        assert "113/192 = 59%" in doc, (
            "the gated recall is not stated — a reader cannot tell what the shipped gate costs")
        i82 = doc.find("82%")
        assert i82 == -1 or "ungated" in doc[max(0, i82 - 200):i82].lower(), (
            "82% appears without being marked as the ungated variant, which is how the "
            "mis-attribution happened the first time")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
